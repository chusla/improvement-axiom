"""Stand-in for the claude CLI in tests. Logs each call (args, cwd, sensitive env names) and mimics its JSON."""

import json
import os
import re
import sys
from pathlib import Path

args = sys.argv[1:]
prompt = sys.stdin.buffer.read().decode("utf-8")
log = os.environ.get("FAKE_CLAUDE_LOG")
state_dir = Path(os.environ.get("FAKE_CLAUDE_STATE", "."))
leaked = sorted(k for k in os.environ if k in ("ANTHROPIC_API_KEY", "CLAUDECODE", "ANTHROPIC_BASE_URL")
                or k.startswith("CLAUDE_CODE_"))
if log:  # one file per call: concurrent appends to a single file can lose lines on Windows
    import uuid
    Path(log).mkdir(parents=True, exist_ok=True)
    (Path(log) / f"{uuid.uuid4().hex}.json").write_text(
        json.dumps({"args": args, "cwd": os.getcwd(), "leaked_env": leaked}), encoding="utf-8")

if os.environ.get("FAKE_LIMIT") == "1":
    print(json.dumps({"is_error": True, "result": "Claude usage limit reached. Your limit will reset at 5pm"}))
    sys.exit(1)


def opt(name):
    return args[args.index(name) + 1] if name in args else None


turn = 1
sid = opt("--session-id") or opt("--resume")
if sid:
    f = state_dir / f"{sid}.json"
    if opt("--resume"):
        if not f.exists():
            print(json.dumps({"is_error": True, "result": f"No conversation found with session ID: {sid}"}))
            sys.exit(1)
        turn = json.loads(f.read_text())["turn"] + 1
    f.write_text(json.dumps({"turn": turn}))

if "# Judging Task" in prompt:
    ids = re.findall(r'id:\s*"([^"]+)"', prompt)
    text = "REASONING\nfake\n\nRESULT\n" + json.dumps({i: [] for i in ids})
else:
    text = f"fake reply turn {turn}"
print(json.dumps({"is_error": False, "result": text, "subtype": "success",
                  "usage": {"input_tokens": 12, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
                            "output_tokens": 5, "output_tokens_details": {"thinking_tokens": 0}},
                  "modelUsage": {opt("--model") or "fake": {}}, "total_cost_usd": 0.001}))
