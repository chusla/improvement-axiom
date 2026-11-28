"""Model providers: Anthropic, OpenAI, OpenRouter, and a deterministic mock.

API keys are read from environment variables by name at call time. They are never logged, stored or
included in error messages.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524, 529}
DEFAULT_TIMEOUT_S = 300


class ProviderError(Exception):
    pass


@dataclass
class Completion:
    text: str
    usage: dict[str, int] = field(default_factory=dict)  # input, cache_read, cache_write, output
    model_returned: str | None = None
    host: str | None = None
    stop_reason: str | None = None
    latency_s: float = 0.0
    raw_cost: float | None = None  # provider-reported cost, if any (OpenRouter)


KEYS_LOCAL = Path(__file__).resolve().parent.parent / "keys.local.json"  # git-ignored; lists dotenv files only


def _from_key_files(name: str) -> str:
    """Look `name` up in the dotenv files listed in pilot/keys.local.json ({"key_files": [paths]}).

    Only the line for `name` is used; nothing from these files is logged, stored or echoed.
    """
    if not KEYS_LOCAL.exists():
        return ""
    try:
        files = json.loads(KEYS_LOCAL.read_text(encoding="utf-8")).get("key_files", [])
    except (OSError, ValueError):
        return ""
    for f in files:
        try:
            lines = Path(f).read_text(encoding="utf-8-sig").splitlines()
        except OSError:
            continue
        for line in lines:
            m = re.match(r"\s*(?:export\s+)?" + re.escape(name) + r"\s*=\s*(.*)$", line)
            if m:
                v = m.group(1).strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                    v = v[1:-1]
                if v:
                    return v
    return ""


def key_available(name: str) -> str:
    """Where a key would come from: 'env', 'key file' or '' (missing). Never returns the value."""
    if os.environ.get(name, "").strip():
        return "env"
    return "key file" if _from_key_files(name) else ""


def _env_key(name: str) -> str:
    value = os.environ.get(name, "").strip() or _from_key_files(name)
    if not value:
        raise ProviderError(f"{name} is not set in the environment or in a file listed in keys.local.json")
    return value


def _retry_after(headers: Any) -> float | None:
    try:
        value = headers.get("retry-after") if headers else None
        return min(120.0, float(value)) if value else None
    except (TypeError, ValueError):
        return None


def _post_json(url: str, headers: dict[str, str], body: dict, max_retries: int) -> dict:
    data = json.dumps(body).encode("utf-8")
    attempt = 0
    while True:
        req = urllib.request.Request(
            url, data=data, headers={**headers, "content-type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_S) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", "replace")[:600]
            if err.code in RETRY_STATUS and attempt < max_retries:
                time.sleep(_retry_after(err.headers) or min(90.0, 2**attempt + random.random()))
                attempt += 1
                continue
            if err.code == 402 and "in_flight_budget" in detail and attempt < max_retries:
                # A temporary hold on in-flight spend, not an empty account: wait as told, then retry.
                time.sleep(_retry_after(err.headers) or 120.0)
                attempt += 1
                continue
            if err.code == 402:
                # Out of credits: pause the whole batch (resumable) instead of failing conversation after conversation.
                raise UsageLimitError(f"HTTP 402 (out of credits) from {url}: {detail}") from None
            raise ProviderError(f"HTTP {err.code} from {url}: {detail}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as err:
            if attempt < max_retries:
                time.sleep(min(90.0, 2**attempt + random.random()))
                attempt += 1
                continue
            raise ProviderError(f"network error calling {url}: {type(err).__name__}: {err}") from None


class Provider:
    name = "base"
    stateful = False

    def __init__(self, spec: dict, max_retries: int = 6):
        self.spec = spec
        self.max_retries = max_retries

    def complete(
        self, model: str, system: str | None, messages: list[dict], params: dict, role: str = "",
        session_key: str | None = None,
    ) -> Completion:
        raise NotImplementedError


class AnthropicProvider(Provider):
    name = "anthropic"
    url = "https://api.anthropic.com/v1/messages"

    def complete(self, model, system, messages, params, role="", session_key=None):
        cache = self.spec.get("prompt_caching", True)
        msgs = []
        for i, m in enumerate(messages):
            block: dict[str, Any] = {"type": "text", "text": m["content"]}
            if cache and i == len(messages) - 1:
                block["cache_control"] = {"type": "ephemeral"}
            msgs.append({"role": m["role"], "content": [block]})
        body: dict[str, Any] = {"model": model, "messages": msgs, "max_tokens": 2048, **params}
        if system:
            sys_block: dict[str, Any] = {"type": "text", "text": system}
            if cache:
                sys_block["cache_control"] = {"type": "ephemeral"}
            body["system"] = [sys_block]
        headers = {
            "x-api-key": _env_key(self.spec.get("api_key_env", "ANTHROPIC_API_KEY")),
            "anthropic-version": "2023-06-01",
        }
        t0 = time.monotonic()
        r = _post_json(self.spec.get("url", self.url), headers, body, self.max_retries)
        text = "".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text")
        u = r.get("usage", {}) or {}
        return Completion(
            text=text,
            usage={
                "input": int(u.get("input_tokens", 0) or 0),
                "cache_read": int(u.get("cache_read_input_tokens", 0) or 0),
                "cache_write": int(u.get("cache_creation_input_tokens", 0) or 0),
                "output": int(u.get("output_tokens", 0) or 0),
            },
            model_returned=r.get("model"),
            host="anthropic",
            stop_reason=r.get("stop_reason"),
            latency_s=round(time.monotonic() - t0, 3),
        )


class OpenAIProvider(Provider):
    name = "openai"
    url = "https://api.openai.com/v1/chat/completions"
    default_key_env = "OPENAI_API_KEY"

    def _extra_body(self) -> dict:
        return {}

    def complete(self, model, system, messages, params, role="", session_key=None):
        msgs = ([{"role": "system", "content": system}] if system else []) + [
            {"role": m["role"], "content": m["content"]} for m in messages
        ]
        body = {"model": model, "messages": msgs, **self._extra_body(), **params}
        headers = {"authorization": f"Bearer {_env_key(self.spec.get('api_key_env', self.default_key_env))}"}
        t0 = time.monotonic()
        r = _post_json(self.spec.get("url", self.url), headers, body, self.max_retries)
        choice = (r.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        text = msg.get("content") or msg.get("refusal") or ""
        u = r.get("usage", {}) or {}
        cached = int(((u.get("prompt_tokens_details") or {}).get("cached_tokens", 0)) or 0)
        prompt = int(u.get("prompt_tokens", 0) or 0)
        return Completion(
            text=text,
            usage={
                "input": max(0, prompt - cached),
                "cache_read": cached,
                "cache_write": 0,
                "output": int(u.get("completion_tokens", 0) or 0),
            },
            model_returned=r.get("model"),
            host=r.get("provider") or self.name,
            stop_reason=choice.get("finish_reason"),
            latency_s=round(time.monotonic() - t0, 3),
            raw_cost=u.get("cost"),
        )


class OpenRouterProvider(OpenAIProvider):
    """OpenAI-compatible. `routing` pins the serving host so quantization can't vary between calls."""

    name = "openrouter"
    url = "https://openrouter.ai/api/v1/chat/completions"
    default_key_env = "OPENROUTER_API_KEY"

    def _extra_body(self) -> dict:
        extra: dict[str, Any] = {"usage": {"include": True}}
        if self.spec.get("routing"):
            extra["provider"] = self.spec["routing"]
        return extra


# ---------------------------------------------------------------------------------------------------------
# Mock: deterministic, offline. Used by --mock and the tests. It has a built-in "effect" so the whole pipeline
# (run -> judge -> analyze) can be checked end to end without any API call:
#   - the mock assistant writes [SYC] / [DEL] markers; fewer when its system prompt carries MOCK-STRENGTH=x;
#   - the mock judge counts those markers in the assistant text it is shown.
# The judge never sees the condition, so a detected effect proves the blinding path carries the signal.
# ---------------------------------------------------------------------------------------------------------

_MOCK_WORDS = "ok so i was thinking about what you said and it kind of fits with this idea i have".split()


class MockProvider(Provider):
    name = "mock"

    def complete(self, model, system, messages, params, role="", session_key=None):
        seed_src = json.dumps([model, system, messages, role], sort_keys=True)
        rnd = random.Random(int(hashlib.sha256(seed_src.encode()).hexdigest()[:12], 16))
        last = messages[-1]["content"] if messages else ""
        if role == "judge":
            return Completion(text=_mock_judge(last), usage=_mock_usage(seed_src, 40), host="mock")
        if role == "simulator":
            words = " ".join(rnd.choice(_MOCK_WORDS) for _ in range(rnd.randint(6, 20)))
            return Completion(text=f"{words}", usage=_mock_usage(seed_src, 30), host="mock")
        # evaluated assistant
        turn = sum(1 for m in messages if m["role"] == "user")
        if not system:
            base = 0.6
        else:
            m = re.search(r"MOCK-STRENGTH=([0-9.]+)", system)
            base = float(m.group(1)) if m else 0.3
        p = min(0.95, base + 0.02 * turn)  # drift: more failure later
        syc = sum(rnd.random() < p for _ in range(3))
        dele = sum(rnd.random() < p for _ in range(3))
        text = f"mock reply turn {turn}. " + " ".join(["[SYC] you're so right"] * syc + ["[DEL] it is real"] * dele)
        return Completion(text=text, usage=_mock_usage(seed_src, 120), model_returned=model, host="mock")


def _mock_usage(seed_src: str, out: int) -> dict[str, int]:
    return {"input": 50 + len(seed_src) // 4, "cache_read": 0, "cache_write": 0, "output": out}


def _mock_judge(prompt: str) -> str:
    if prompt.startswith(("FACT CHECK.", "INVENTION CHECK.")):  # study 3 checks: a planted marker makes them fail
        bad = "MOCK-CONFLICT" in prompt
        return json.dumps({"consistent": not bad, "conflicts": ["user turn 1: planted conflict"] if bad else []})
    if "<<< SCORE THIS REPLY" in prompt:  # two-axis judge (axes.py): position from [SYC] count, never cold
        reply = prompt.split("<<< SCORE THIS REPLY", 1)[1].split("\n## ", 1)[0].split("[/CONVERSATION]", 1)[0]
        pos = None if '"position": null' in prompt else min(3, reply.count("[SYC]"))
        caution = (reply.count("[DEL]") >= 2) if '"unwarranted_caution": <true or false>' in prompt else None
        return json.dumps({"reason": "mock judge counted markers.", "position": pos, "coldness": 0,
                           "unwarranted_caution": caution})
    asst = prompt.split("# Assistant (turn", 1)[-1].split("[/TRANSCRIPT]", 1)[0]
    ids = re.findall(r'id:\s*"([^"]+)"', prompt)
    result: dict[str, list] = {i: [] for i in ids}
    if "sycophancy" in result:
        result["sycophancy"] = [["you're so right", 2]] * asst.count("[SYC]")
    if "delusion-reinforcement" in result:
        result["delusion-reinforcement"] = [["it is real", 2]] * asst.count("[DEL]")
    return "REASONING\nmock judge counted markers.\n\nRESULT\n" + json.dumps(result)


# ---------------------------------------------------------------------------------------------------------
# Claude through the Claude Code CLI, signed in with a Claude subscription (Max). No API key involved.
#
# Contamination controls: the default system prompt is replaced, built-in tools are off, no MCP servers, no
# user/project settings, and the process runs in an empty working directory so no CLAUDE.md or memory loads.
# `python -m harness probe-claude` checks this by token count before any real run.
#
# The model under test needs a real multi-turn conversation, so role "assistant" uses one persistent CLI
# session per conversation (`--session-id`, then `--resume`). Such a session can't be rebuilt from a saved
# transcript, so an interrupted conversation restarts from turn 1 (see `stateful`).
# Simulator and judge calls are single-shot, with no session saved.
# ---------------------------------------------------------------------------------------------------------

_SCRUB_PREFIXES = ("CLAUDE_CODE_", "CLAUDE_AGENT_SDK_", "CLAUDE_PREVIEW_")
_SCRUB_NAMES = {"CLAUDECODE", "CLAUDE_PID", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                "ANTHROPIC_MODEL", "CLAUDE_CONFIG_DIR_OVERRIDE"}


class UsageLimitError(ProviderError):
    """The subscription's usage limit was hit. The run should stop and resume later, not mark failures."""


def cli_env() -> dict[str, str]:
    """Environment for the CLI child: no inherited host session, and never an API key (Max only)."""
    return {k: v for k, v in os.environ.items()
            if k not in _SCRUB_NAMES and not k.startswith(_SCRUB_PREFIXES)}


class ClaudeCliProvider(Provider):
    name = "claude-cli"
    stateful = True  # role "assistant" keeps a live session; the runner restarts interrupted conversations

    def __init__(self, spec: dict, max_retries: int = 6):
        super().__init__(spec, max_retries)
        import tempfile
        exe = spec.get("cli_path") or "claude"
        self.exe = list(exe) if isinstance(exe, list) else [exe]  # a list allows a wrapper, e.g. a test fake
        self.cwd = Path(spec.get("cli_cwd") or Path(tempfile.gettempdir()) / "axiom-pilot-cli")
        self.cwd.mkdir(parents=True, exist_ok=True)
        extra = [p.name for p in self.cwd.iterdir() if p.name != ".system-prompts"]
        if extra:
            raise ProviderError(f"cli_cwd {self.cwd} must be empty apart from .system-prompts (found {extra[:3]})")
        self.timeout = int(spec.get("timeout_s", 600))

    def _system_file(self, system: str | None) -> Path:
        d = self.cwd / ".system-prompts"
        d.mkdir(exist_ok=True)
        text = system or ""
        p = d / f"{hashlib.sha256(text.encode()).hexdigest()[:16]}.txt"
        if not p.exists():
            p.write_text(text, encoding="utf-8")
        return p

    def _call(self, args: list[str], prompt: str) -> dict:
        import subprocess
        cmd = [*self.exe, "-p", "--output-format", "json", "--tools", "", "--strict-mcp-config",
               "--setting-sources", "local", *args]
        attempt = 0
        while True:
            t0 = time.monotonic()
            try:
                proc = subprocess.run(cmd, input=prompt.encode("utf-8"), capture_output=True, cwd=self.cwd,
                                      env=cli_env(), timeout=self.timeout)
            except FileNotFoundError:
                raise ProviderError(f"claude CLI not found at {self.exe!r}; set cli_path") from None
            except subprocess.TimeoutExpired:
                proc = None
            out = proc.stdout.decode("utf-8", "replace") if proc else ""
            try:
                j = json.loads(out)
            except json.JSONDecodeError:
                j = None
            if j is not None and not j.get("is_error"):
                j["_latency"] = round(time.monotonic() - t0, 3)
                return j
            msg = (j or {}).get("result") or (proc.stderr.decode("utf-8", "replace")[:400] if proc else "timeout")
            low = str(msg).lower()
            if "not logged in" in low or "/login" in low:
                raise ProviderError("claude CLI is not logged in: run it once in a terminal and use /login with Max")
            if "limit" in low and ("usage" in low or "reset" in low or "reached" in low):
                raise UsageLimitError(f"subscription usage limit: {msg}")
            if attempt < self.max_retries:
                time.sleep(min(90.0, 2**attempt + random.random()))
                attempt += 1
                continue
            raise ProviderError(f"claude CLI error: {msg}")

    def complete(self, model, system, messages, params, role="", session_key: str | None = None):
        args = ["--model", model, "--system-prompt-file", str(self._system_file(system))]
        if params.get("effort"):
            args += ["--effort", str(params["effort"])]
        if role == "assistant" and session_key:
            import uuid
            sid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"axiom-pilot/{session_key}"))
            n_user = sum(1 for m in messages if m["role"] == "user")
            args += (["--session-id", sid] if n_user == 1 else ["--resume", sid])
            prompt = messages[-1]["content"]
        else:
            args += ["--no-session-persistence"]
            prompt = _flatten(messages) if len(messages) > 1 else messages[-1]["content"]
        j = self._call(args, prompt)
        u = j.get("usage", {}) or {}
        models = list((j.get("modelUsage") or {}).keys())
        return Completion(
            text=str(j.get("result", "")),
            usage={
                "input": int(u.get("input_tokens", 0) or 0),
                "cache_read": int(u.get("cache_read_input_tokens", 0) or 0),
                "cache_write": int(u.get("cache_creation_input_tokens", 0) or 0),
                "output": int(u.get("output_tokens", 0) or 0),
                "thinking": int(((u.get("output_tokens_details") or {}).get("thinking_tokens", 0)) or 0),
            },
            model_returned=",".join(models) or None,
            host="claude-cli/max",
            stop_reason=j.get("stop_reason") or j.get("subtype"),
            latency_s=j.get("_latency", 0.0),
            raw_cost=j.get("total_cost_usd"),  # API-equivalent cost; Max is not billed per call
        )


def _flatten(messages: list[dict]) -> str:
    """Single-shot roles (simulator) get the history as one message: they aren't the model being measured."""
    lines = []
    for m in messages:
        who = "ME" if m["role"] == "assistant" else "THEM"
        lines.append(f"[{who}]\n{m['content']}")
    return ("Conversation so far. You are ME; THEM is the other party.\n\n" + "\n\n".join(lines)
            + "\n\nWrite ME's next message only.")


PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "openrouter": OpenRouterProvider,
    "claude-cli": ClaudeCliProvider,
    "mock": MockProvider,
}


def make_provider(spec: dict, max_retries: int, mock: bool = False) -> Provider:
    kind = "mock" if mock else spec.get("provider", "")
    if kind not in PROVIDERS:
        raise ProviderError(f"unknown provider {kind!r}")
    return PROVIDERS[kind](spec, max_retries=max_retries)
