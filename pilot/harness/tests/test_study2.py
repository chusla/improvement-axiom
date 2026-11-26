"""Offline tests for the study 2 additions (PREREGISTRATION-2.md). Run from pilot/:
python -m unittest discover -s harness/tests -t .
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

from harness import config as config_mod
from harness import pressure
from harness.config import check_registration, check_stage_guards
from harness.runner import run_stage
from harness.store import RunDir, atomic_write_json, read_json
from harness.tests.test_harness import Sandbox


class RegistrationFileTests(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(n_personas=1)
        self.sb.cfg_data["freeze"]["registration_commit"] = "abc123"

    def tearDown(self):
        self.sb.cleanup()

    def _check(self, files: dict[str, str]):
        seen = []

        def fake_show(cwd, commit, path):
            seen.append(path)
            return files.get(path)

        with mock.patch.object(config_mod, "_git_show", fake_show):
            return check_registration(self.sb.cfg()), seen

    def test_default_is_study_1_file(self):
        self.sb.save()
        probs, seen = self._check({"pilot/PREREGISTRATION.md": "**Status: Registered.**"})
        self.assertEqual(probs, [])
        self.assertEqual(seen, ["pilot/PREREGISTRATION.md"])

    def test_study_2_reads_its_own_file(self):
        self.sb.cfg_data["freeze"]["registration_file"] = "PREREGISTRATION-2.md"
        self.sb.save()
        # study 1's file being registered must not satisfy study 2
        probs, seen = self._check({"pilot/PREREGISTRATION.md": "**Status: Registered.**"})
        self.assertEqual(seen, ["pilot/PREREGISTRATION-2.md"])
        self.assertTrue(any("PREREGISTRATION-2.md" in p for p in probs), probs)
        probs, _ = self._check({"pilot/PREREGISTRATION-2.md": "**Status: Not registered. DRAFT**"})
        self.assertTrue(any("still a draft" in p for p in probs), probs)
        probs, _ = self._check({"pilot/PREREGISTRATION-2.md": "**Status: Registered.**"})
        self.assertEqual(probs, [])


class NamedScreeningStageTests(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(n_personas=1, test_sets=("pool",))

    def tearDown(self):
        self.sb.cleanup()

    def test_screening_2_has_the_screening_guards(self):
        self.sb.cfg_data["stages"]["screening-2"] = {"persona_dirs": ["personas/pool"], "conditions": ["none", "axiom"],
                                                     "models": ["m1"], "runs": 1}
        self.sb.save()
        probs = check_stage_guards(self.sb.cfg(), "screening-2", mock=False)
        self.assertTrue(any("only use the 'none'" in p for p in probs), probs)
        self.assertTrue(any("cap and min_kept" in p for p in probs), probs)
        self.assertTrue(any("registration_commit" in p for p in probs), probs)


class SimulatorEveryTurnTests(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(n_personas=1)

    def tearDown(self):
        self.sb.cleanup()

    def test_simulator_level_reminder_is_used_and_recorded(self):
        self.sb.cfg_data["simulator"]["every_turn"] = "Stay unconvinced."
        self.sb.cfg_data["stages"]["practice"]["conditions"] = ["none"]
        self.sb.cfg_data["stages"]["practice"]["models"] = ["m1"]
        self.sb.save()
        run = RunDir(self.sb.root / "runs" / "_mock-practice")
        self.assertEqual(run_stage(self.sb.cfg(), "practice", run, mock=True)["complete"], 1)
        rec = read_json(run.conversations()[0])
        self.assertEqual(rec["simulator_every_turn"], "Stay unconvinced.")

    def test_stage_level_override_wins(self):
        self.sb.cfg_data["simulator"]["every_turn"] = "Stay unconvinced."
        self.sb.cfg_data["stages"]["practice"].update(conditions=["none"], models=["m1"], simulator_every_turn="Other.")
        self.sb.save()
        run = RunDir(self.sb.root / "runs" / "_mock-practice")
        run_stage(self.sb.cfg(), "practice", run, mock=True)
        self.assertEqual(read_json(run.conversations()[0])["simulator_every_turn"], "Other.")


def _reply(pushes: list[int], conceded=None) -> str:
    turns = {str(t): {"push": v, "why": "x"} for t, v in zip(range(pressure.FIRST, pressure.LAST + 1), pushes)}
    return "Here you go:\n" + json.dumps({"turns": turns, "user_conceded_turn": conceded})


class PressureTests(unittest.TestCase):
    N = pressure.LAST - pressure.FIRST + 1

    def test_parse_is_strict(self):
        self.assertEqual(pressure.parse(_reply([2] * self.N))["turns"]["10"]["push"], 2)
        with self.assertRaises(ValueError):
            pressure.parse(_reply([2] * (self.N - 1) + [3]))
        with self.assertRaises(KeyError):
            pressure.parse(_reply([2] * (self.N - 1)))
        with self.assertRaises(ValueError):
            pressure.parse("no json here")
        with self.assertRaises(ValueError):
            pressure.parse(_reply([2] * self.N, conceded="turn 12"))

    def test_summary_and_flag(self):
        rs = [{"condition": "axiom", "turns": {str(t): {"push": 2} for t in range(10, 21)}, "user_conceded_turn": None},
              {"condition": "control", "turns": {str(t): {"push": 1} for t in range(10, 21)}, "user_conceded_turn": 14}]
        s = pressure.summarize(rs)
        self.assertEqual(s["axiom"]["mean_push"], 2.0)
        self.assertEqual(s["control"]["user_conceded"], 1)
        self.assertTrue(pressure.flag(s, ["axiom", "control"])["flag"])
        self.assertFalse(pressure.flag({"a": {"mean_push": 1.9}, "b": {"mean_push": 1.8}}, ["a", "b"])["flag"])

    def test_score_run_only_complete_pressure_cases_and_errors_never_zero(self):
        sb = Sandbox(n_personas=0)
        try:
            run = RunDir(sb.root / "runs" / "r")
            personas = {"pp": {"id": "pp", "type": "pressure", "anchor": "A", "false_position": "F", "card": "c"},
                        "bb": {"id": "bb", "type": "benign"}}
            msgs = [{"role": r, "turn": t, "content": f"{r} {t}"} for t in range(1, 21) for r in ("user", "assistant")]

            def conv(cid, pid, cond, status="complete"):
                atomic_write_json(run.conversation(cid), {"id": cid, "persona_id": pid, "condition": cond,
                                                          "run_index": 1, "status": status, "messages": msgs})
            conv("c1", "pp", "axiom")
            conv("c2", "pp", "control")
            conv("c3", "bb", "axiom")                 # benign: not scored
            conv("c4", "pp", "axiom", status="error")  # unfinished: not scored
            conv("c5", "pp", "control")

            out = pressure.score_run(run, personas, lambda s, p: _reply([2] * self.N), contrast=["axiom", "control"],
                                     workers=1)
            self.assertEqual(out["n"], 3)
            self.assertEqual(out["by_type"]["pressure"]["axiom"]["n"], 1)
            self.assertEqual(out["by_type"]["pressure"]["control"]["n"], 2)
            self.assertFalse(out["primary"]["flag"])
            self.assertTrue((run.root / "pressure" / "summary.json").exists())

            # a fresh run where the judge always fails: listed as errors, nothing scored
            run2 = RunDir(sb.root / "runs" / "r2")
            atomic_write_json(run2.conversation("c1"), read_json(run.conversation("c1")))
            out2 = pressure.score_run(run2, personas, lambda s, p: "garbage", workers=1)
            self.assertEqual(out2["n"], 0)
            self.assertIn("c1", out2["errors"])
            self.assertFalse((run2.root / "pressure" / "c1.json").exists())
        finally:
            sb.cleanup()


class DependenceTypeTests(unittest.TestCase):
    def _dep(self, pid="d1", pset="practice"):
        return {"id": pid, "set": pset, "type": "dependence", "anchor": "A", "false_position": "F", "card": "c",
                "turns": {"1": {"text": "hi"}, "3": {"direct": "press"}}}

    def test_dependence_needs_an_answer_key(self):
        from harness.personas import PersonaError, validate_persona
        validate_persona(self._dep(), 6)
        bad = self._dep()
        del bad["anchor"]
        with self.assertRaises(PersonaError):
            validate_persona(bad, 6)

    def test_per_type_simulator_and_stage_override(self):
        sb = Sandbox(n_personas=1)
        try:
            (sb.root / "sim-dep.md").write_text("play the attached user", encoding="utf-8")
            sb.cfg_data["simulator"]["every_turn"] = "General."
            sb.cfg_data["simulator"]["by_type"] = {"dependence": {"base_prompt": "sim-dep.md", "every_turn": "Dep."}}
            sb.write_persona(self._dep(), "practice")
            sb.cfg_data["stages"]["practice"].update(conditions=["none"], models=["m1"])
            sb.save()
            run = RunDir(sb.root / "runs" / "_mock-practice")
            run_stage(sb.cfg(), "practice", run, mock=True)
            recs = {read_json(p)["persona_id"]: read_json(p) for p in run.conversations()}
            self.assertEqual(recs["d1"]["simulator_base"], "sim-dep.md")
            self.assertEqual(recs["d1"]["simulator_every_turn"], "Dep.")
            self.assertEqual(recs["p00"]["simulator_base"], "sim.md")
            self.assertEqual(recs["p00"]["simulator_every_turn"], "General.")
        finally:
            sb.cleanup()

    def test_dependence_is_a_separate_stratum(self):
        from harness.outcomes import conversation_outcomes
        scores = {t: {"position": 2, "coldness": 2, "phase": "pressure"} for t in range(10, 21)}
        dep = conversation_outcomes(scores, {"type": "dependence"}, 20)
        self.assertEqual((dep["dep_give_in"], dep["dep_cold"]), (1, 1))
        self.assertIsNone(dep["give_in"])
        self.assertIsNone(dep["cold"])  # never feeds the primary coldness guard
        prs = conversation_outcomes(scores, {"type": "pressure"}, 20)
        self.assertEqual((prs["give_in"], prs["cold"]), (1, 1))
        self.assertIsNone(prs["dep_give_in"])


class Study2ConfigTests(unittest.TestCase):
    def test_study2_config_is_what_the_draft_says(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        c = json.loads((root / "config.study2.json").read_text(encoding="utf-8"))
        s1 = json.loads((root / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(c["simulator"]["base_prompt"], "simulator/base-v2.md")
        self.assertEqual(c["simulator"]["params"]["max_tokens"], 6000)
        self.assertEqual(c["simulator"]["model"], s1["simulator"]["model"])
        self.assertEqual(c["simulator"]["routing"], s1["simulator"]["routing"])
        self.assertEqual(c["simulator"]["params"]["reasoning"], s1["simulator"]["params"]["reasoning"])
        self.assertEqual(c["models"]["kimi"], s1["models"]["kimi"])
        self.assertEqual(c["judges"][0]["model"], s1["judges"][0]["model"])
        self.assertEqual(c["freeze"]["prompt_sha256"], s1["freeze"]["prompt_sha256"])
        self.assertEqual(c["freeze"]["registration_file"], "PREREGISTRATION-2.md")
        self.assertEqual(c["screening"]["seed"], 20261126)
        self.assertEqual(c["analysis"]["seed"], 20261126)
        self.assertEqual(c["analysis"]["primary_contrast"], ["axiom", "control-openai"])
        self.assertEqual(sorted(c["stages"]["test-2"]["blocks"]), ["a", "b"])
        self.assertNotEqual(c["runs_dir"], s1["runs_dir"])
        self.assertEqual(c["analysis"]["dependence_sensitivity_exclude"], ["dp-06"])
        for k in ("cap", "min_kept"):
            self.assertEqual(c["screening"][k], s1["screening"][k])


if __name__ == "__main__":
    unittest.main()
