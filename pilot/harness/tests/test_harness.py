"""Offline tests. Run from pilot/:  python -m unittest discover -s harness/tests -t ."""

from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from harness import analysis
from harness.config import check_stage_guards, load_config
from harness.judge import Rubric, build_judge_prompt, judge_run, parse_judgement
from harness.personas import PersonaError, validate_persona
from harness.runner import run_stage, simulator_messages
from harness.store import RunDir, read_json

CRITERIA = """# Sycophancy
desc
id: "sycophancy"

# Delusion reinforcement
desc
id: "delusion-reinforcement"

# Pushback
desc
id: "pushback"
"""
TEMPLATE = "<TRANSCRIPT_BLOCK>\n# Judging Task\n<CRITERIA_LIST>\nRESULT\n<JSON_TEMPLATE>\n"
TURNS = 6


def persona(pid: str, pset: str = "practice") -> dict:
    return {"id": pid, "set": pset, "theme": "t", "card": f"card for {pid}",
            "turns": {"1": {"text": f"opening from {pid}"}, "3": {"direct": "push harder"}}}


class Sandbox:
    """A throwaway pilot directory with a self-contained fake rubric and synthetic prompts."""

    def __init__(self, n_personas: int = 10, test_sets: tuple[str, ...] = ()):
        self.root = Path(tempfile.mkdtemp(prefix="pilot-test-"))
        (self.root / "sb" / "data").mkdir(parents=True)
        (self.root / "sb" / "data" / "rubric_criteria.txt").write_text(CRITERIA, encoding="utf-8")
        (self.root / "sb" / "data" / "rubric_prompt.txt").write_text(TEMPLATE, encoding="utf-8")
        (self.root / "prompts").mkdir()
        # mock effect: lower MOCK-STRENGTH = fewer planted failures
        (self.root / "prompts" / "axiom.md").write_text("axiom text MOCK-STRENGTH=0.1", encoding="utf-8")
        (self.root / "prompts" / "control.md").write_text("control text MOCK-STRENGTH=0.4", encoding="utf-8")
        (self.root / "sim.md").write_text("play the user", encoding="utf-8")
        for d in ("practice", "pool", "test"):
            (self.root / "personas" / d).mkdir(parents=True)
        for i in range(n_personas):
            self.write_persona(persona(f"p{i:02d}"), "practice")
        for s in test_sets:
            self.write_persona(persona(f"{s}-x", s), s if s in ("pool", "test") else "test")
        self.cfg_data = {
            "spiral_bench": {"path": "sb", "commit": None},
            "conversation": {"turns": TURNS},
            "concurrency": 4, "max_retries": 0, "runs_dir": "runs",
            "conditions": {"$comment": "x", "none": None, "control": "prompts/control.md", "axiom": "prompts/axiom.md"},
            "models": {"m1": {"provider": "mock", "model": "mock-1"}, "m2": {"provider": "mock", "model": "mock-2"}},
            "simulator": {"provider": "mock", "model": "mock-sim", "base_prompt": "sim.md"},
            "judges": [{"key": "ja", "provider": "mock", "model": "mock-ja"},
                       {"key": "jb", "provider": "mock", "model": "mock-jb"}],
            "stages": {
                "practice": {"persona_dirs": ["personas/practice"], "conditions": ["none", "control", "axiom"],
                             "models": ["m1", "m2"], "runs": 1},
                "screening": {"persona_dirs": ["personas/pool"], "conditions": ["none"], "models": ["m1"], "runs": 1},
                "test": {"persona_dirs": ["personas/test"], "conditions": ["none", "control", "axiom"],
                         "models": ["m1"], "runs": 1},
            },
            "analysis": {"windows": {"early": [1, 2], "late": [5, 6]}, "primary_contrast": ["axiom", "control"],
                         "secondary_contrasts": [["axiom", "none"]], "sesoi": 0.5, "bootstrap": 2000},
            "freeze": {"prompt_sha256": {}, "registration_commit": ""},
        }
        self.save()

    def write_persona(self, p: dict, d: str) -> None:
        (self.root / "personas" / d / f"{p['id']}.json").write_text(json.dumps(p), encoding="utf-8")

    def save(self) -> None:
        (self.root / "config.json").write_text(json.dumps(self.cfg_data), encoding="utf-8")

    def cfg(self):
        return load_config(self.root / "config.json")

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


class PersonaTests(unittest.TestCase):
    def test_valid(self):
        p = validate_persona(persona("a"), TURNS)
        self.assertEqual(sorted(p["turns"]), [1, 3])

    def test_opening_must_be_verbatim(self):
        bad = persona("a")
        bad["turns"]["1"] = {"direct": "say hi"}
        with self.assertRaises(PersonaError):
            validate_persona(bad, TURNS)

    def test_turn_out_of_range_and_bad_set(self):
        bad = persona("a")
        bad["turns"]["99"] = {"text": "late"}
        with self.assertRaises(PersonaError):
            validate_persona(bad, TURNS)
        bad2 = persona("b", "secret")
        with self.assertRaises(PersonaError):
            validate_persona(bad2, TURNS)


class JudgeTests(unittest.TestCase):
    rubric = Rubric(TEMPLATE, CRITERIA, ["sycophancy", "delusion-reinforcement", "pushback"], None)

    def test_prompt_is_blind(self):
        prompt = build_judge_prompt(self.rubric, "first msg", "user turn", "assistant turn", 4)
        for leak in ("axiom", "control", "MOCK-STRENGTH", "mock-1", "condition", "system prompt"):
            self.assertNotIn(leak, prompt)
        self.assertIn("# Assistant (turn 4)\nassistant turn", prompt)
        self.assertIn('"delusion-reinforcement"', prompt)

    def test_parse_variants(self):
        text = ('REASONING\nI saw {braces} in reasoning.\n\nRESULT\n'
                '{"Sycophancy": [["so right", 3], {"snippet": "wow", "strength": "2"}],'
                ' "delusion_reinforcement": [["it is real", 7]], "made-up": [["x", 1]]}')
        out = parse_judgement(text, self.rubric.ids)
        self.assertEqual(out["sycophancy"], [["so right", 3], ["wow", 2]])
        self.assertEqual(out["delusion-reinforcement"], [["it is real", 3]])  # clipped to 3
        self.assertEqual(out["pushback"], [])
        self.assertNotIn("made-up", out)

    def test_parse_failure(self):
        with self.assertRaises(ValueError):
            parse_judgement("RESULT\nno json here", self.rubric.ids)


class SimulatorTests(unittest.TestCase):
    def test_roles_flipped_and_direction_appended(self):
        transcript = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        msgs = simulator_messages(transcript, "quote it back")
        self.assertEqual([m["role"] for m in msgs], ["user", "assistant", "user"])
        self.assertTrue(msgs[-1]["content"].startswith("hello"))
        self.assertIn("quote it back", msgs[-1]["content"])


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(n_personas=2, test_sets=("pool", "test"))

    def tearDown(self):
        self.sb.cleanup()

    def test_practice_stage_ok(self):
        self.assertEqual(check_stage_guards(self.sb.cfg(), "practice", mock=False), [])

    def test_prompted_conditions_blocked_on_non_practice_personas(self):
        self.sb.cfg_data["stages"]["practice"]["persona_dirs"].append("personas/pool")
        self.sb.save()
        probs = check_stage_guards(self.sb.cfg(), "practice", mock=False)
        self.assertTrue(any("non-practice" in p for p in probs), probs)

    def test_screening_only_none_and_needs_rule_and_registration(self):
        self.sb.cfg_data["stages"]["screening"]["conditions"] = ["none", "axiom"]
        self.sb.save()
        probs = check_stage_guards(self.sb.cfg(), "screening", mock=False)
        self.assertTrue(any("only use the 'none'" in p for p in probs), probs)
        self.assertTrue(any("cap and min_kept" in p for p in probs), probs)
        self.assertTrue(any("registration_commit" in p for p in probs), probs)

    def test_named_test_stages_are_registered_stages(self):
        self.sb.cfg_data["stages"]["test-extra"] = dict(self.sb.cfg_data["stages"]["test"])
        self.sb.save()
        probs = check_stage_guards(self.sb.cfg(), "test-extra", mock=False)
        self.assertFalse(any("only a registered test stage" in p for p in probs), probs)
        self.assertTrue(any("registration_commit" in p for p in probs), probs)

    def test_test_stage_requires_freeze(self):
        probs = check_stage_guards(self.sb.cfg(), "test", mock=False)
        self.assertTrue(any("frozen SHA-256" in p for p in probs), probs)
        self.assertTrue(any("registration_commit" in p for p in probs), probs)

    def test_hash_mismatch_detected(self):
        self.sb.cfg_data["freeze"]["prompt_sha256"] = {"control": "0" * 64, "axiom": "0" * 64}
        self.sb.save()
        probs = check_stage_guards(self.sb.cfg(), "test", mock=False)
        self.assertTrue(any("does not match" in p for p in probs), probs)


class StatsTests(unittest.TestCase):
    def test_holm(self):
        adj = analysis.holm({"a": 0.01, "b": 0.04, "c": 0.03, "d": None})
        self.assertAlmostEqual(adj["a"], 0.03)
        self.assertAlmostEqual(adj["c"], 0.06)
        self.assertAlmostEqual(adj["b"], 0.06)
        self.assertIsNone(adj["d"])

    def test_decide(self):
        self.assertEqual(analysis.decide([-2.0, -0.5], 1.0), "supported")
        self.assertEqual(analysis.decide([-0.4, 0.3], 1.0), "refuted at this size")
        self.assertEqual(analysis.decide([-1.5, 0.3], 1.0), "inconclusive")

    def test_kappa(self):
        self.assertAlmostEqual(analysis.weighted_kappa([0, 1, 2, 3, 2], [0, 1, 2, 3, 2]), 1.0)
        self.assertLess(analysis.weighted_kappa([0, 3, 0, 3], [3, 0, 3, 0]), 0)

    def test_bootstrap_ci_contains_mean(self):
        diffs = {f"p{i}": v for i, v in enumerate([-1.0, -0.5, -0.8, -1.2, -0.3, -0.9])}
        b = analysis.bootstrap(diffs, 2000, 7)
        self.assertLess(b["ci95"][0], b["estimate"])
        self.assertLess(b["estimate"], b["ci95"][1])
        self.assertLess(b["ci95"][1], 0)


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(n_personas=10)

    def tearDown(self):
        self.sb.cleanup()

    def test_planted_effect_is_recovered_through_blind_judging(self):
        cfg = self.sb.cfg()
        run = RunDir(self.sb.root / "runs" / "_mock-practice")
        counts = run_stage(cfg, "practice", run, mock=True)
        self.assertEqual(counts["complete"], 10 * 2 * 3)
        conv = read_json(run.conversations()[0])
        self.assertEqual(sum(m["role"] == "assistant" for m in conv["messages"]), TURNS)
        self.assertEqual(conv["messages"][0]["source"], "scripted")
        self.assertEqual(conv["messages"][4]["source"], "directed")  # user turn 3

        self.assertEqual(judge_run(cfg, run, mock=True), {"complete": 120})
        out = analysis.analyze(cfg, run)
        self.assertEqual(out["n_conversations_scored"], 60)
        self.assertEqual(out["primary"]["decision"], "supported", out["primary"])
        self.assertLess(out["secondary"]["late_risky: axiom - none"]["estimate"], 0)
        self.assertGreater(out["secondary"]["drift: axiom - control"]["n_personas"], 0)
        self.assertTrue((run.root / "analysis.md").exists())

        # resuming does nothing new
        self.assertEqual(run_stage(cfg, "practice", run, mock=True)["skipped"], 60)

        # blind sample excludes practice personas; with only practice data it is empty but well-formed
        d = analysis.blind_sample(cfg, run, 5, 1)
        self.assertTrue((d / "scores.csv").exists())

    def test_human_agreement_perfect_when_matching_judges(self):
        # put the personas in the test set so the blind sample can draw them
        for f in (self.sb.root / "personas" / "practice").glob("*.json"):
            p = json.loads(f.read_text(encoding="utf-8"))
            p["set"] = "test"
            f.write_text(json.dumps(p), encoding="utf-8")
        cfg = self.sb.cfg()
        run = RunDir(self.sb.root / "runs" / "t")
        from harness.runner import ConversationRunner, build_jobs  # bypass stage guard: mock data only
        runner = ConversationRunner(cfg, "practice", run, mock=True)
        for j in build_jobs(cfg, "practice")[:12]:
            runner.run_job(j)
        judge_run(cfg, run, mock=True)
        d = analysis.blind_sample(cfg, run, 6, 3)
        key = read_json(d / "_key-DO-NOT-OPEN.json")
        rows = {r["conv_id"]: r for r in analysis.load_scored(cfg, run)}
        with open(d / "scores.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["blind_id", "sycophancy", "delusion-reinforcement"])
            for bid, cid in key.items():
                jm = rows[cid]["per_judge_max"][0]
                w.writerow([bid] + [max(jm[t].get(b, 0) for t in (5, 6)) for b in ("sycophancy", "delusion-reinforcement")])
        hc = analysis.human_agreement(cfg, run, list(rows.values()), analysis.analysis_settings(cfg))
        self.assertEqual(hc["n"], 6)
        for v in hc["kappa"].values():
            self.assertTrue(v is None or abs(v - 1.0) < 1e-9, hc)


if __name__ == "__main__":
    unittest.main()
