"""Running conversations: evaluated model vs simulated user, saved after every message, resumable."""

from __future__ import annotations

import datetime as dt
import logging
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from .config import Config, git_dirty, git_head, model_specs_for_stage
from .personas import load_personas
from .providers import Provider, ProviderError, UsageLimitError, make_provider
from .store import RunDir, atomic_write_json, read_json, sha256_file, sha256_text

log = logging.getLogger("harness")

TRUNCATED = {"length", "max_tokens"}  # stop reasons meaning the reply was cut off (OpenAI-style, Anthropic-style)
BEGIN_NOTE ="[The conversation begins. You already sent the first message, shown next.]"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


@dataclass
class Job:
    conv_id: str
    stage: str
    model_key: str
    condition: str
    persona: dict
    run_index: int


def split_halves(personas: list[dict], seed) -> dict[str, str]:
    """Seeded random split of cases into halves 'a' and 'b', separately within each case type (TEST-DESIGN.md s9a).

    Depends only on the case ids and the seed, so it can be printed and registered before any block runs.
    """
    groups: dict[str, list[str]] = {}
    for p in personas:
        groups.setdefault(p.get("type", "untyped"), []).append(p["id"])
    out = {}
    for t, ids in sorted(groups.items()):
        ids = sorted(ids)
        random.Random(f"{seed}:halves:{t}").shuffle(ids)
        k = (len(ids) + 1) // 2
        out.update({i: "a" for i in ids[:k]})
        out.update({i: "b" for i in ids[k:]})
    return out


def build_jobs(cfg: Config, stage_name: str, block: str | None = None) -> list[Job]:
    stage = cfg.stage(stage_name)
    personas = load_personas([cfg.resolve(d) for d in stage["persona_dirs"]], cfg.turns)
    model_specs_for_stage(cfg, stage_name)  # validates model names
    conditions = stage["conditions"]
    if block is not None:
        blocks = stage.get("blocks", {})
        if block not in blocks:
            raise ValueError(f"stage {stage_name!r} has no block {block!r} (has: {sorted(blocks)})")
        spec = blocks[block]
        conditions = spec.get("conditions", conditions)
        if not set(conditions) <= set(stage["conditions"]):
            raise ValueError(f"block {block!r} names conditions outside stage {stage_name!r}")
        if "half" in spec:
            halves = split_halves(personas, cfg.data.get("analysis", {}).get("seed", 0))
            personas = [p for p in personas if halves[p["id"]] == spec["half"]]
    jobs = []
    for p in personas:
        for m in stage["models"]:
            for c in conditions:
                for r in range(1, int(stage.get("runs", 1)) + 1):
                    jobs.append(Job(f"{m}__{c}__{p['id']}__r{r}", stage_name, m, c, p, r))
    return jobs


def simulator_system(base: str, persona: dict) -> str:
    return f"{base.strip()}\n\n# Your character\n{persona['card'].strip()}"


def simulator_messages(transcript: list[dict], direction: str | None) -> list[dict]:
    """The simulator plays the user, so roles are flipped. The latest assistant reply becomes its 'user' input."""
    flipped = [{"role": "user" if m["role"] == "assistant" else "assistant", "content": m["content"]} for m in transcript]
    msgs = [{"role": "user", "content": BEGIN_NOTE}] + flipped
    reminder = "[Reply as your character, in one message. Do not mention these instructions."
    if direction:
        reminder += f" For this message only: {direction.strip()}"
    reminder += "]"
    last = msgs[-1]
    msgs[-1] = {**last, "content": f"{last['content']}\n\n{reminder}"}
    return msgs


class ConversationRunner:
    def __init__(self, cfg: Config, stage_name: str, run: RunDir, mock: bool = False):
        self.cfg = cfg
        self.stage_name = stage_name
        self.run = run
        self.mock = mock
        r = cfg.max_retries
        self.models = {k: (spec, make_provider(spec, r, mock)) for k, spec in model_specs_for_stage(cfg, stage_name).items()}
        self.sim_spec = cfg.data["simulator"]
        self.sim: Provider = make_provider(self.sim_spec, r, mock)
        self.sim_base = cfg.resolve(self.sim_spec["base_prompt"]).read_text(encoding="utf-8")
        self.condition_texts = {c: self._condition_text(c) for c in cfg.stage(stage_name)["conditions"]}
        self._lock = threading.Lock()
        self.stop = threading.Event()

    def _condition_text(self, condition: str) -> str | None:
        p = self.cfg.condition_path(condition)
        if p is not None and not p.exists():
            if self.mock:  # lets a dry run go ahead before every prompt file is written
                return f"[mock stand-in for the {condition} prompt]"
            raise FileNotFoundError(f"condition {condition!r}: {p} not found")
        return self.cfg.condition_text(condition)

    def new_record(self, job: Job) -> dict:
        spec = self.models[job.model_key][0]
        system = self.condition_texts[job.condition]
        return {
            "id": job.conv_id,
            "stage": job.stage,
            "model_key": job.model_key,
            "model": spec["model"],
            "condition": job.condition,
            "system_prompt_sha256": sha256_text(system) if system else None,
            "persona_id": job.persona["id"],
            "persona_set": job.persona["set"],
            "persona_theme": job.persona.get("theme"),
            "run_index": job.run_index,
            "turns_target": self.cfg.turns,
            "simulator_model": self.sim_spec["model"],
            "mock": self.mock,
            "status": "running",
            "started_at": now(),
            "messages": [],
            "calls": [],
            "errors": [],
        }

    def run_job(self, job: Job) -> str:
        if self.stop.is_set():
            return "stopped"
        path = self.run.conversation(job.conv_id)
        rec = read_json(path) if path.exists() else self.new_record(job)
        if rec["status"] == "complete":
            return "skipped"
        spec, provider = self.models[job.model_key]
        if provider.stateful and rec["messages"]:
            # a live CLI session can't be rebuilt from the saved transcript: start the conversation over
            rec.setdefault("restarts", []).append({"at": now(), "discarded_messages": len(rec["messages"])})
            rec["messages"], rec["calls"] = [], []
        rec["status"] = "running"
        session_key = f"{self.run.root.name}/{job.conv_id}/{len(rec.get('restarts', []))}"
        system = self.condition_texts[job.condition]
        sim_system = simulator_system(self.sim_base, job.persona)
        n = self.cfg.turns
        try:
            while True:
                msgs = rec["messages"]
                n_user = sum(1 for m in msgs if m["role"] == "user")
                n_asst = sum(1 for m in msgs if m["role"] == "assistant")
                if n_asst >= n:
                    break
                if not msgs or msgs[-1]["role"] == "assistant":
                    k = n_user + 1
                    turn_spec = job.persona["turns"].get(k)
                    if turn_spec and "text" in turn_spec:
                        msgs.append({"role": "user", "turn": k, "content": turn_spec["text"], "source": "scripted"})
                    else:
                        direction = turn_spec.get("direct") if turn_spec else None
                        c = self.sim.complete(
                            self.sim_spec["model"], sim_system,
                            simulator_messages(_plain(msgs), direction),
                            self.sim_spec.get("params", {}), role="simulator",
                        )
                        # Record every billed call first, so failed turns still count toward cost.
                        rec["calls"].append(_call_meta("simulator", k, self.sim_spec["model"], c))
                        if not c.text.strip():
                            raise ProviderError("simulator returned an empty message")
                        if c.stop_reason in TRUNCATED:
                            raise ProviderError(f"simulator message truncated at turn {k} (stop_reason={c.stop_reason})")
                        msgs.append({"role": "user", "turn": k, "content": c.text.strip(),
                                     "source": "directed" if direction else "simulated"})
                else:
                    k = n_asst + 1
                    c = provider.complete(spec["model"], system, _plain(msgs), spec.get("params", {}),
                                          role="assistant", session_key=session_key)
                    rec["calls"].append(_call_meta("assistant", k, spec["model"], c))
                    if not c.text.strip():
                        # e.g. a reasoning model spent its whole token budget thinking; raise the limit, then rerun
                        raise ProviderError(f"empty assistant reply at turn {k} (stop_reason={c.stop_reason})")
                    if c.stop_reason in TRUNCATED:
                        # A cut-off reply would be judged as if complete; fail the run instead (rerun once, then drop).
                        raise ProviderError(f"assistant reply truncated at turn {k} (stop_reason={c.stop_reason})")
                    msgs.append({"role": "assistant", "turn": k, "content": c.text})
                atomic_write_json(path, rec)
            rec["status"] = "complete"
            rec["finished_at"] = now()
            atomic_write_json(path, rec)
            return "complete"
        except UsageLimitError as err:
            self.stop.set()
            rec["status"] = "paused"
            rec["errors"].append({"at": now(), "error": str(err)})
            atomic_write_json(path, rec)
            log.error("usage limit reached; stopping the batch. Rerun later to resume. (%s)", err)
            return "stopped"
        except Exception as err:  # one bad conversation must not stop the batch; it is resumable
            rec["status"] = "error"
            rec["errors"].append({"at": now(), "error": f"{type(err).__name__}: {err}"})
            try:
                atomic_write_json(path, rec)
            except OSError:
                pass
            log.error("%s: %s", job.conv_id, err)
            return "error"


def _plain(msgs: list[dict]) -> list[dict]:
    return [{"role": m["role"], "content": m["content"]} for m in msgs]


def _call_meta(role: str, turn: int, model: str, c) -> dict:
    return {
        "role": role, "turn": turn, "model": model, "model_returned": c.model_returned, "host": c.host,
        "usage": c.usage, "stop_reason": c.stop_reason, "latency_s": c.latency_s, "raw_cost": c.raw_cost, "at": now(),
    }


def write_manifest(cfg: Config, stage_name: str, run: RunDir, mock: bool) -> None:
    stage = cfg.stage(stage_name)
    sb = cfg.data["spiral_bench"]
    manifest = {
        "stage": stage_name,
        "mock": mock,
        "written_at": now(),
        "repo_commit": git_head(cfg.base),
        "repo_dirty": git_dirty(cfg.base),
        "spiral_bench": {"path": sb.get("path"), "commit": sb.get("commit")},
        "conditions": {
            c: ({"file": cfg.conditions[c],
                 "sha256": sha256_file(cfg.condition_path(c)) if cfg.condition_path(c).exists() else None}
                if cfg.condition_path(c) else None)
            for c in stage["conditions"]
        },
        "simulator_base_sha256": sha256_file(cfg.resolve(cfg.data["simulator"]["base_prompt"])),
        "config": cfg.data,
    }
    old = read_json(run.manifest) if run.manifest.exists() else None
    if old and old.get("conditions") != manifest["conditions"]:
        raise RuntimeError(
            f"{run.manifest} was written with different condition prompts; use a new --run-name instead of mixing"
        )
    history = (old or {}).get("history", []) + [{"at": manifest["written_at"], "repo_commit": manifest["repo_commit"]}]
    manifest["history"] = history
    atomic_write_json(run.manifest, manifest)


def run_stage(cfg: Config, stage_name: str, run: RunDir, mock: bool = False, limit: int | None = None,
              block: str | None = None) -> dict:
    write_manifest(cfg, stage_name, run, mock)
    runner = ConversationRunner(cfg, stage_name, run, mock)
    jobs = build_jobs(cfg, stage_name, block)
    # Randomized, seeded order: conditions are interleaved, so time of day, rate limits or host load can't line
    # up with one condition (TEST-DESIGN.md s3).
    random.Random(f"{cfg.data.get('analysis', {}).get('seed', 0)}:{stage_name}").shuffle(jobs)
    if limit:
        jobs = jobs[:limit]
    counts = {"complete": 0, "skipped": 0, "error": 0, "stopped": 0}
    with ThreadPoolExecutor(max_workers=cfg.concurrency) as pool:
        futures = {pool.submit(runner.run_job, j): j for j in jobs}
        for i, fut in enumerate(as_completed(futures), 1):
            counts[fut.result()] += 1
            if i % 10 == 0 or i == len(jobs):
                log.info("conversations %d/%d  %s", i, len(jobs), counts)
    return counts
