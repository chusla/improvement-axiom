"""The Claude-subscription (CLI) route, tested offline against a fake `claude` executable."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from harness.judge import judge_run
from harness.runner import ConversationRunner, build_jobs, run_stage
from harness.store import RunDir, read_json
from harness.tests.test_harness import Sandbox

FAKE = str(Path(__file__).with_name("fake_claude.py"))


class CliRouteTests(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(n_personas=2)
        self.tmp = Path(tempfile.mkdtemp(prefix="fake-cli-"))
        self.cli_cwd = self.tmp / "cwd"
        self.log = self.tmp / "calls"
        (self.tmp / "state").mkdir()
        spec = {"provider": "claude-cli", "cli_path": [sys.executable, FAKE], "cli_cwd": str(self.cli_cwd)}
        d = self.sb.cfg_data
        d["models"] = {"c": {**spec, "model": "claude-x"}}
        d["simulator"] = {**spec, "model": "claude-sim", "base_prompt": "sim.md"}
        d["judges"] = [{**spec, "key": "jc", "model": "claude-judge"}]
        d["stages"]["practice"] = {"persona_dirs": ["personas/practice"], "conditions": ["none", "axiom"],
                                   "models": ["c"], "runs": 1}
        self.sb.save()
        self.env_backup = dict(os.environ)
        os.environ.update({"FAKE_CLAUDE_LOG": str(self.log), "FAKE_CLAUDE_STATE": str(self.tmp / "state"),
                           "ANTHROPIC_API_KEY": "sk-should-never-reach-child", "CLAUDECODE": "1",
                           "CLAUDE_CODE_SESSION_ID": "host-session"})
        os.environ.pop("FAKE_LIMIT", None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.env_backup)
        self.sb.cleanup()

    def calls(self):
        return [json.loads(p.read_text(encoding="utf-8")) for p in self.log.glob("*.json")]

    def test_lockdown_flags_env_and_sessions(self):
        cfg = self.sb.cfg()
        run = RunDir(self.sb.root / "runs" / "cli")
        counts = run_stage(cfg, "practice", run)
        self.assertEqual(counts["complete"], 4, counts)
        self.assertEqual(judge_run(cfg, run, mock=False)["complete"], 4)

        calls = self.calls()
        self.assertTrue(calls)
        for c in calls:
            a = c["args"]
            self.assertEqual(c["leaked_env"], [], "host session or API key leaked into the CLI child")
            self.assertEqual(a[a.index("--tools") + 1], "")
            self.assertIn("--strict-mcp-config", a)
            self.assertEqual(a[a.index("--setting-sources") + 1], "local")
            self.assertIn("--system-prompt-file", a)
            self.assertEqual(Path(c["cwd"]).resolve(), self.cli_cwd.resolve())

        # model under test: one session per conversation, created once then resumed
        by_sid: dict[str, list[str]] = {}
        for c in calls:
            a = c["args"]
            if "--session-id" in a:
                by_sid.setdefault(a[a.index("--session-id") + 1], []).append("new")
            elif "--resume" in a:
                by_sid.setdefault(a[a.index("--resume") + 1], []).append("resume")
            else:
                self.assertIn("--no-session-persistence", a)  # simulator and judge
        self.assertEqual(len(by_sid), 4)
        for seq in by_sid.values():  # log files are unordered; the fake itself rejects a resume before a new
            self.assertEqual(sorted(seq), ["new"] + ["resume"] * 5)  # 6 turns

        conv = read_json(run.conversations()[0])
        self.assertEqual(conv["messages"][-1]["content"], "fake reply turn 6")
        self.assertEqual(conv["calls"][0]["host"], "claude-cli/max")

        # the 'none' condition still replaces Claude Code's default prompt, with an empty file
        none_files = {c["args"][c["args"].index("--system-prompt-file") + 1] for c in calls}
        self.assertTrue(any(Path(f).read_text(encoding="utf-8") == "" for f in none_files))

    def test_usage_limit_pauses_and_resume_restarts(self):
        cfg = self.sb.cfg()
        run = RunDir(self.sb.root / "runs" / "lim")
        os.environ["FAKE_LIMIT"] = "1"
        counts = run_stage(cfg, "practice", run)
        self.assertEqual(counts["error"], 0, counts)
        self.assertGreaterEqual(counts["stopped"], 1)
        paused = [read_json(p) for p in run.conversations()]
        self.assertTrue(all(c["status"] == "paused" for c in paused))

        os.environ["FAKE_LIMIT"] = "0"
        counts = run_stage(cfg, "practice", run)
        self.assertEqual(counts["complete"], 4, counts)

    def test_interrupted_conversation_restarts_from_turn_one(self):
        cfg = self.sb.cfg()
        run = RunDir(self.sb.root / "runs" / "rs")
        runner = ConversationRunner(cfg, "practice", run)
        job = build_jobs(cfg, "practice")[0]
        runner.run_job(job)
        rec = read_json(run.conversation(job.conv_id))
        rec["status"] = "error"
        rec["messages"] = rec["messages"][:5]
        run.conversation(job.conv_id).write_text(json.dumps(rec), encoding="utf-8")
        self.assertEqual(runner.run_job(job), "complete")
        rec = read_json(run.conversation(job.conv_id))
        self.assertEqual(len(rec["restarts"]), 1)
        self.assertEqual(sum(m["role"] == "assistant" for m in rec["messages"]), 6)
        self.assertEqual(rec["messages"][1]["content"], "fake reply turn 1")  # fresh session

    def test_cli_cwd_must_be_empty(self):
        from harness.providers import ClaudeCliProvider, ProviderError
        self.cli_cwd.mkdir(parents=True, exist_ok=True)
        (self.cli_cwd / "CLAUDE.md").write_text("leak", encoding="utf-8")
        with self.assertRaises(ProviderError):
            ClaudeCliProvider({"cli_cwd": str(self.cli_cwd)})


if __name__ == "__main__":
    unittest.main()
