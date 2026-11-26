"""Per-turn grading with Spiral-Bench's rubric, loaded from a pinned local clone.

Blinding: the judge prompt is built only from the transcript (initial user message, the user turn, the
assistant turn). It never receives the condition, the system prompt, the model name or run metadata.
`build_judge_prompt` takes only those three strings, so this holds by construction.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from .config import Config
import threading

from .providers import ProviderError, UsageLimitError, make_provider
from .runner import now
from .store import RunDir, atomic_write_json, read_json

log = logging.getLogger("harness")


class RubricError(Exception):
    pass


@dataclass
class Rubric:
    template: str
    criteria: str
    ids: list[str]
    commit: str | None


def load_rubric(cfg: Config, verify_commit: bool = True) -> Rubric:
    sb = cfg.data["spiral_bench"]
    root = cfg.resolve(sb["path"])
    crit_path, tmpl_path = root / "data" / "rubric_criteria.txt", root / "data" / "rubric_prompt.txt"
    if not crit_path.exists() or not tmpl_path.exists():
        raise RubricError(
            f"Spiral-Bench rubric not found under {root}. Clone it: "
            f"git clone https://github.com/sam-paech/spiral-bench {root} && git -C {root} checkout {sb.get('commit')}"
        )
    commit = None
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True)
        commit = out.stdout.strip() if out.returncode == 0 else None
    except OSError:
        pass
    if verify_commit and sb.get("commit") and commit != sb["commit"]:
        raise RubricError(f"Spiral-Bench clone is at {commit}, config pins {sb['commit']}")
    criteria = crit_path.read_text(encoding="utf-8")
    ids = re.findall(r'^id:\s*"([^"]+)"', criteria, flags=re.M)
    if not ids:
        raise RubricError("no behaviour ids found in rubric_criteria.txt")
    return Rubric(tmpl_path.read_text(encoding="utf-8"), criteria, ids, commit)


def build_judge_prompt(rubric: Rubric, initial_user: str, user_turn: str, assistant_turn: str, turn_no: int) -> str:
    """Same layout as Spiral-Bench's judge_worker with chunk size 1."""
    block = "\n".join([
        "[TRANSCRIPT]",
        "# Initial User Message:",
        initial_user.strip(),
        f"\n# User (turn {turn_no})\n{user_turn.strip()}",
        f"\n# Assistant (turn {turn_no})\n{assistant_turn.strip()}",
        "[/TRANSCRIPT]\n",
    ])
    json_template = "{\n" + ",\n".join(
        f'  "{k}": [\n    ["<short assistant-only quote>", <int 1-3>]\n  ]' for k in rubric.ids
    ) + "\n}"
    return (rubric.template.replace("<TRANSCRIPT_BLOCK>", block)
            .replace("<CRITERIA_LIST>", rubric.criteria)
            .replace("<JSON_TEMPLATE>", json_template))


def _norm_key(k: str) -> str:
    return re.sub(r"[\s_]+", "-", k.strip().lower())


def parse_judgement(text: str, ids: list[str]) -> dict[str, list[list]]:
    seg = text.rsplit("RESULT", 1)[-1] if "RESULT" in text else text
    m = re.search(r"\{.*\}", seg, re.S)
    if not m:
        raise ValueError("no JSON object in judge output")
    raw = json.loads(m.group(0))
    if not isinstance(raw, dict):
        raise ValueError("judge JSON is not an object")
    by_key = {_norm_key(k): v for k, v in raw.items()}
    out: dict[str, list[list]] = {}
    for i in ids:
        items = by_key.get(i, [])
        norm = []
        if isinstance(items, list):
            for it in items:
                if isinstance(it, list) and len(it) == 2:
                    snip, s = it
                elif isinstance(it, dict):
                    snip, s = it.get("snippet", ""), it.get("strength", it.get("intensity", 1))
                else:
                    continue
                try:
                    s = int(s)
                except (TypeError, ValueError):
                    s = 1
                norm.append([str(snip)[:140], max(1, min(3, s))])
        out[i] = norm
    return out


def turn_pairs(conv: dict) -> list[tuple[int, str, str]]:
    users = {m["turn"]: m["content"] for m in conv["messages"] if m["role"] == "user"}
    assts = {m["turn"]: m["content"] for m in conv["messages"] if m["role"] == "assistant"}
    return [(t, users[t], assts[t]) for t in sorted(assts) if t in users]


class Judge:
    def __init__(self, cfg: Config, run: RunDir, judge_spec: dict, rubric: Rubric, mock: bool = False):
        self.cfg, self.run, self.spec, self.rubric = cfg, run, judge_spec, rubric
        self.key = judge_spec["key"]
        self.provider = make_provider(judge_spec, cfg.max_retries, mock)

    stop = threading.Event()  # shared by all judges in a run: set when the subscription limit is hit

    def judge_conversation(self, conv_path: Path) -> str:
        if self.stop.is_set():
            return "stopped"
        conv = read_json(conv_path)
        if conv.get("status") != "complete":
            return "not-ready"
        out_path = self.run.judgement(self.key, conv["id"])
        rec = read_json(out_path) if out_path.exists() else {
            "conv_id": conv["id"], "judge_key": self.key, "judge_model": self.spec["model"],
            "rubric_commit": self.rubric.commit, "turns": {}, "errors": [],
        }
        pairs = turn_pairs(conv)
        if not pairs:
            return "empty"
        initial_user = pairs[0][1]
        for t, u, a in pairs:
            if str(t) in rec["turns"]:
                continue
            prompt = build_judge_prompt(self.rubric, initial_user, u, a, t)
            result, last_err = None, None
            for _attempt in range(2):
                try:
                    c = self.provider.complete(self.spec["model"], None, [{"role": "user", "content": prompt}],
                                               self.spec.get("params", {}), role="judge")
                    result = {"behaviours": parse_judgement(c.text, self.rubric.ids), "raw": c.text,
                              "usage": c.usage, "model_returned": c.model_returned, "at": now()}
                    break
                except (ValueError, json.JSONDecodeError) as err:
                    last_err = f"parse: {err}"
                except UsageLimitError as err:
                    Judge.stop.set()
                    log.error("usage limit reached; stopping judging. Rerun later to resume. (%s)", err)
                    atomic_write_json(out_path, rec)
                    return "stopped"
                except ProviderError as err:
                    last_err = str(err)
                    break
            if result is None:
                rec["errors"].append({"turn": t, "error": last_err, "at": now()})
                atomic_write_json(out_path, rec)
                return "error"
            rec["turns"][str(t)] = result
            atomic_write_json(out_path, rec)
        rec["complete"] = len(rec["turns"]) == len(pairs)
        atomic_write_json(out_path, rec)
        return "complete"


def judge_run(cfg: Config, run: RunDir, mock: bool = False) -> dict:
    Judge.stop.clear()
    rubric = load_rubric(cfg, verify_commit=not mock)
    convs = run.conversations()
    counts: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=cfg.concurrency) as pool:
        futures = []
        for spec in cfg.data["judges"]:
            j = Judge(cfg, run, spec, rubric, mock)
            futures += [pool.submit(j.judge_conversation, p) for p in convs]
        for i, fut in enumerate(as_completed(futures), 1):
            try:
                r = fut.result()
            except Exception as err:  # keep judging the rest; reruns resume per turn
                log.error("judge task failed: %s: %s", type(err).__name__, err)
                r = "error"
            counts[r] = counts.get(r, 0) + 1
            if i % 20 == 0 or i == len(futures):
                log.info("judged %d/%d  %s", i, len(futures), counts)
    return counts
