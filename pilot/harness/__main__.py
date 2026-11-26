"""Command line. Run from the pilot/ directory:

  python -m harness validate                       check config, keys present, rubric, personas, guards
  python -m harness hash                           SHA-256 and word counts of every prompt (for freezing)
  python -m harness run --stage practice --mock    offline dry run, no API calls
  python -m harness run --stage screening --go     real run (spends money; --go is required)
  python -m harness judge --stage screening [--go]
  python -m harness status --stage screening
  python -m harness screen-report --stage screening
  python -m harness analyze --stage test
  python -m harness blind-sample --stage test --n 30

--run-name overrides the run directory (default: the stage name, or _mock-<stage> with --mock).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import Counter
from pathlib import Path

from . import analysis
from .config import (ConfigError, check_stage_guards, dump, find_placeholders, load_config, word_count)
from .judge import RubricError, judge_run, load_rubric
from .personas import PersonaError, load_personas
from .runner import build_jobs, run_stage
from .store import RunDir, read_json, sha256_file

from .providers import key_available

KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "openrouter": "OPENROUTER_API_KEY"}


def run_dir(cfg, stage: str, mock: bool, name: str | None) -> RunDir:
    base = cfg.resolve(cfg.data.get("runs_dir", "runs"))
    return RunDir(base / (name or (f"_mock-{stage}" if mock else stage)))


def used_specs(cfg) -> list[dict]:
    names = {m for s in cfg.data["stages"].values() for m in s["models"]}
    return [cfg.data["models"][m] for m in sorted(names)] + [cfg.data["simulator"]] + list(cfg.data["judges"])


def cmd_validate(cfg, args) -> int:
    blocking, notes = [], []
    ph = find_placeholders(cfg.data)
    if ph:
        (notes if args.mock else blocking).append("placeholders to fill: " + ", ".join(ph))
    envs = sorted({s.get("api_key_env", KEY_ENV.get(s.get("provider", ""), "")) for s in used_specs(cfg)} - {""})
    for e in envs:
        src = key_available(e)
        state = f"set ({src})" if src else "MISSING"
        (notes if src or args.mock else blocking).append(f"key {e}: {state}")
    try:
        r = load_rubric(cfg, verify_commit=True)
        notes.append(f"rubric: {len(r.ids)} behaviour ids, Spiral-Bench at {r.commit}")
    except RubricError as err:
        blocking.append(f"rubric: {err}")
    for c, rel in cfg.conditions.items():
        if rel is None:
            continue
        p = cfg.resolve(rel)
        if not p.exists():
            (notes if args.mock else blocking).append(f"condition {c}: file not written yet ({rel})")
        else:
            notes.append(f"condition {c}: {word_count(p.read_text(encoding='utf-8'))} words")
    lm = cfg.data.get("length_match")
    if lm:
        ref = cfg.condition_path(lm["reference"])
        if ref and ref.exists():
            n_ref = word_count(ref.read_text(encoding="utf-8"))
            for c in lm["conditions"]:
                p = cfg.condition_path(c)
                if p and p.exists():
                    n = word_count(p.read_text(encoding="utf-8"))
                    ok = abs(n - n_ref) <= lm["tolerance"] * n_ref
                    (notes if ok else blocking).append(
                        f"length match {c}: {n} vs {lm['reference']} {n_ref} words ({'ok' if ok else 'OUTSIDE tolerance'})")
    for name in cfg.data["stages"]:
        try:
            stage = cfg.stage(name)
            ps = load_personas([cfg.resolve(d) for d in stage["persona_dirs"]], cfg.turns)
            notes.append(f"stage {name}: {len(ps)} personas, {len(build_jobs(cfg, name))} conversations")
            for prob in check_stage_guards(cfg, name, args.mock):
                (notes if name != args.stage and args.stage else blocking).append(f"stage {name}: {prob}")
        except (PersonaError, ConfigError, FileNotFoundError) as err:
            notes.append(f"stage {name}: not ready ({err})")
    for n in notes:
        print("  ok   " + n)
    for b in blocking:
        print("  FIX  " + b)
    print("\nREADY" if not blocking else f"\n{len(blocking)} blocking problem(s)")
    return 0 if not blocking else 1


def cmd_hash(cfg, args) -> int:
    freeze = {}
    for c, rel in cfg.conditions.items():
        if rel is None:
            continue
        p = cfg.resolve(rel)
        if p.exists():
            h = sha256_file(p)
            freeze[c] = h
            print(f"{c:22s} {word_count(p.read_text(encoding='utf-8')):5d} words  {h}  {rel}")
        else:
            print(f"{c:22s}   (missing) {rel}")
    sim = cfg.resolve(cfg.data["simulator"]["base_prompt"])
    print(f"{'simulator base':22s} {word_count(sim.read_text(encoding='utf-8')):5d} words  {sha256_file(sim)}")
    print("\nfreeze.prompt_sha256 =\n" + dump(freeze))
    return 0


def cmd_run(cfg, args) -> int:
    probs = check_stage_guards(cfg, args.stage, args.mock)
    if probs:
        print("refusing to run:\n  " + "\n  ".join(probs))
        return 1
    if not args.mock:
        ph = find_placeholders(cfg.data)
        if ph:
            print("refusing to run: fill placeholders first: " + ", ".join(ph))
            return 1
        if not args.go:
            n = len(build_jobs(cfg, args.stage))
            print(f"this would run {n} conversations of {cfg.turns} turns and spend money. Re-run with --go.")
            return 1
    run = run_dir(cfg, args.stage, args.mock, args.run_name)
    counts = run_stage(cfg, args.stage, run, mock=args.mock, limit=args.limit)
    print(f"{run.root}: {counts}")
    return 0 if not counts.get("error") else 2


def cmd_judge(cfg, args) -> int:
    if not args.mock and not args.go:
        print("judging spends money. Re-run with --go.")
        return 1
    run = run_dir(cfg, args.stage, args.mock, args.run_name)
    counts = judge_run(cfg, run, mock=args.mock)
    print(f"{run.root}: {counts}")
    return 0 if not counts.get("error") else 2


def cmd_status(cfg, args) -> int:
    run = run_dir(cfg, args.stage, args.mock, args.run_name)
    convs = [read_json(p) for p in run.conversations()]
    print(f"{run.root}: {len(convs)} conversation files")
    print("  by status:", dict(Counter(c["status"] for c in convs)))
    print("  complete by model x condition:", dict(Counter(
        f"{c['model_key']}/{c['condition']}" for c in convs if c["status"] == "complete")))
    for spec in cfg.data["judges"]:
        js = [read_json(p) for p in run.judgements(spec["key"])]
        print(f"  judge {spec['key']}: {sum(1 for j in js if j.get('complete'))} complete, "
              f"{sum(1 for j in js if j.get('errors'))} with errors")
    errs = [c for c in convs if c["status"] == "error"]
    for c in errs[:5]:
        print(f"  error {c['id']}: {c['errors'][-1]['error'][:200]}")
    cost = analysis.cost_summary(cfg, run)
    print(f"  estimated cost so far: ${cost['total_usd']}" + (f" (unpriced: {cost['unpriced']})" if cost["unpriced"] else ""))
    return 0


def cmd_analyze(cfg, args) -> int:
    run = run_dir(cfg, args.stage, args.mock, args.run_name)
    out = analysis.analyze(cfg, run)
    print((run.root / "analysis.md").read_text(encoding="utf-8"))
    return 0 if out["n_conversations_scored"] else 1


def cmd_screen(cfg, args) -> int:
    run = run_dir(cfg, args.stage, args.mock, args.run_name)
    out = analysis.screening_report(cfg, run)
    print(dump({k: v for k, v in out.items() if k != "table"}))
    print(f"full table: {run.root / 'screening.json'}")
    return 0


def cmd_blind(cfg, args) -> int:
    run = run_dir(cfg, args.stage, args.mock, args.run_name)
    d = analysis.blind_sample(cfg, run, args.n, args.seed)
    print(f"wrote {d / 'sample.md'} and {d / 'scores.csv'}; the key is in {d.name}/_key-DO-NOT-OPEN.json")
    return 0


PROBE_MAX_INPUT = 150  # a few-word system prompt + one short message; Claude Code's own prompt is many thousands


def cmd_probe_claude(cfg, args) -> int:
    """Prove the CLI route is clean before trusting it: token counts, a canary question, and a session check."""
    from .providers import ClaudeCliProvider, ProviderError
    spec = dict(cfg.data["models"].get(args.model_key) or {})
    if spec.get("provider") != "claude-cli":
        print(f"model {args.model_key!r} is not a claude-cli model in this config")
        return 1
    prov = ClaudeCliProvider(spec, max_retries=1)
    model = spec["model"]

    def total(c):
        return c.usage["input"] + c.usage["cache_read"] + c.usage["cache_write"]

    results, ok = [], True
    try:
        c = prov.complete(model, "You are a test.", [{"role": "user", "content": "Reply with exactly: OK"}], {})
        passed = total(c) <= PROBE_MAX_INPUT
        ok &= passed
        results.append(("1 short system prompt", total(c), c.text.strip()[:40], c.model_returned, passed))

        c = prov.complete(model, None, [{"role": "user", "content": "Reply with exactly: OK"}], {})
        passed = total(c) <= PROBE_MAX_INPUT
        ok &= passed
        results.append(("2 empty system prompt ('none' condition)", total(c), c.text.strip()[:40], c.model_returned, passed))

        q = ("Before this message, were you given any instructions, documents, notes, memories, file contents or "
             "tool definitions other than the one-line system prompt? If so, quote the first line of each. "
             "If not, reply with exactly: NONE")
        c = prov.complete(model, "You are a test.", [{"role": "user", "content": q}], {})
        passed = c.text.strip().upper().startswith("NONE")
        ok &= passed
        results.append(("3 canary question", total(c), c.text.strip()[:120], c.model_returned, passed))

        import uuid
        key = f"probe/{uuid.uuid4()}"
        m1 = [{"role": "user", "content": "Remember the number 7. Reply with exactly: OK"}]
        c1 = prov.complete(model, "You are a test.", m1, {}, role="assistant", session_key=key)
        m2 = m1 + [{"role": "assistant", "content": c1.text}, {"role": "user", "content": "What number? Reply with the digit only."}]
        c2 = prov.complete(model, "You are a test.", m2, {}, role="assistant", session_key=key)
        passed = c2.text.strip().startswith("7") and total(c2) <= PROBE_MAX_INPUT * 2
        ok &= passed
        results.append(("4 two-turn session", total(c2), c2.text.strip()[:40], c2.model_returned, passed))
    except ProviderError as err:
        print(f"probe stopped: {err}")
        return 1
    for name, tok, text, served, passed in results:
        print(f"{'PASS' if passed else 'FAIL'}  {name}: {tok} input tokens, served by {served}, reply {text!r}")
    print("\nCLEAN: safe to use for runs" if ok else "\nNOT CLEAN: do not use this route until fixed")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="harness", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config.json")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, stage=True):
        p = sub.add_parser(name)
        p.set_defaults(fn=fn)
        p.add_argument("--mock", action="store_true", help="offline mock providers, no API calls")
        p.add_argument("--run-name")
        p.add_argument("--stage", required=stage and name != "validate")
        return p

    add("validate", cmd_validate)
    add("hash", cmd_hash, stage=False)
    p = add("run", cmd_run)
    p.add_argument("--go", action="store_true")
    p.add_argument("--limit", type=int)
    p = add("judge", cmd_judge)
    p.add_argument("--go", action="store_true")
    add("status", cmd_status)
    add("analyze", cmd_analyze)
    add("screen-report", cmd_screen)
    p = sub.add_parser("probe-claude", help="check the Claude CLI (Max) route is free of hidden context")
    p.set_defaults(fn=cmd_probe_claude)
    p.add_argument("--model-key", default="claude")
    p = add("blind-sample", cmd_blind)
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--seed", type=int, default=1)

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose or args.cmd in ("run", "judge") else logging.WARNING,
                        format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    try:
        cfg = load_config(Path(args.config))
        return args.fn(cfg, args)
    except (ConfigError, PersonaError, RubricError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
