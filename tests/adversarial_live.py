#!/usr/bin/env python3
"""Adversarial test runner against a live HuggingFace Space.

Loads adversarial scenario YAML files (persona-style with behavioral
assertions), sends each turn to the live Gradio API, evaluates
assertions on the response, and optionally verifies Supabase state.

Usage:
    # Run all adversarial scenarios against the live Space
    python tests/adversarial_live.py

    # Run a specific scenario
    python tests/adversarial_live.py --scenario adversarial_jailbreak

    # Target a different Space
    python tests/adversarial_live.py --space chusla/improvement-axiom

    # Also verify Supabase logs
    python tests/adversarial_live.py --check-supabase
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Fix Windows console encoding for unicode characters (emoji, accents, etc.)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import yaml

from resonance_alignment.agent.personas import (
    BehavioralAssertion,
    evaluate_behavioral_assertion,
)


# ------------------------------------------------------------------
# Data models for live test results
# ------------------------------------------------------------------

@dataclass
class TurnResult:
    """Result of one conversation turn against the live Space."""
    turn_index: int
    user_message: str
    agent_response: str
    assertions_passed: list[tuple[str, str]] = field(default_factory=list)
    assertions_failed: list[tuple[str, str]] = field(default_factory=list)
    latency_seconds: float = 0.0
    error: str = ""

    @property
    def passed(self) -> bool:
        return len(self.assertions_failed) == 0 and not self.error


@dataclass
class ScenarioResult:
    """Result of running one full adversarial scenario."""
    scenario_name: str
    description: str
    tags: list[str] = field(default_factory=list)
    turn_results: list[TurnResult] = field(default_factory=list)
    total_assertions: int = 0
    passed_assertions: int = 0
    failed_assertions: int = 0
    total_latency: float = 0.0
    supabase_verified: bool | None = None

    @property
    def passed(self) -> bool:
        return all(t.passed for t in self.turn_results)


# ------------------------------------------------------------------
# Gradio client wrapper
# ------------------------------------------------------------------

class LiveSpaceClient:
    """Client for sending messages to a live Gradio chat Space."""

    def __init__(self, space_id: str, hf_token: str | None = None):
        from gradio_client import Client
        print(f"  Connecting to Space: {space_id}...")
        self._client = Client(space_id, token=hf_token)
        self._chat_history: list[dict] = []
        print(f"  Connected.")

    def _extract_text(self, msg: Any) -> str:
        """Extract plain text from a Gradio chat message (dict or str)."""
        if isinstance(msg, dict):
            # Gradio 6 format: {"role": ..., "content": [...]}
            content = msg.get("content", "")
            if isinstance(content, list):
                # content is a list of parts: [{"text": "...", "type": "text"}, ...]
                parts = []
                for part in content:
                    if isinstance(part, dict):
                        parts.append(part.get("text", str(part)))
                    else:
                        parts.append(str(part))
                return " ".join(parts)
            return str(content)
        return str(msg)

    def send_message(self, message: str) -> str:
        """Send a message and return the agent's text response."""
        try:
            result = self._client.predict(
                message=message,
                chat_history=self._chat_history,
                api_name="/respond",
            )
            # API returns: (cleared_input, updated_chat_history, metrics_markdown)
            if isinstance(result, (list, tuple)) and len(result) >= 2:
                self._chat_history = result[1] or []

                # Extract the last assistant message from chat history
                if self._chat_history:
                    last_msg = self._chat_history[-1]
                    return self._extract_text(last_msg)

            return str(result)
        except Exception as e:
            raise ConnectionError(f"Failed to get response from Space: {e}")

    def reset(self):
        """Reset conversation state via the clear endpoint."""
        try:
            self._client.predict(api_name="/clear_conversation")
        except Exception:
            pass
        self._chat_history = []


# ------------------------------------------------------------------
# Alternative: direct HTTP approach for more control
# ------------------------------------------------------------------

class LiveSpaceHTTPClient:
    """Fallback client using direct HTTP calls to the Gradio 5 SSE API."""

    def __init__(self, space_id: str, hf_token: str | None = None):
        import httpx
        self._base_url = f"https://{space_id.replace('/', '-')}.hf.space"
        self._hf_token = hf_token
        self._session_hash = f"adv_test_{int(time.time())}"
        self._chat_history: list = []
        self._state: dict = {}
        self._metrics: Any = None
        self._client = httpx.Client(timeout=180.0)
        print(f"  Connecting via HTTP to: {self._base_url}")

    def _extract_text(self, msg: Any) -> str:
        """Extract plain text from a Gradio chat message."""
        if isinstance(msg, dict):
            content = msg.get("content", "")
            if isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, dict):
                        parts.append(part.get("text", str(part)))
                    else:
                        parts.append(str(part))
                return " ".join(parts)
            return str(content)
        return str(msg)

    def send_message(self, message: str) -> str:
        """Send a message via the Gradio 5 SSE API (two-step call)."""
        headers = {"Content-Type": "application/json"}
        if self._hf_token:
            headers["Authorization"] = f"Bearer {self._hf_token}"

        payload = {
            "data": [
                message,
                self._chat_history,
                self._state,
                self._metrics,
            ],
            "session_hash": self._session_hash,
        }

        # Step 1: POST to initiate the call and get an event_id
        resp = self._client.post(
            f"{self._base_url}/gradio_api/call/respond",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        event_id = resp.json().get("event_id")
        if not event_id:
            raise ConnectionError(f"No event_id returned: {resp.text}")

        # Step 2: GET the SSE stream to receive results
        with self._client.stream(
            "GET",
            f"{self._base_url}/gradio_api/call/respond/{event_id}",
            headers=headers,
        ) as stream:
            last_data = None
            for line in stream.iter_lines():
                if line.startswith("data: "):
                    last_data = line[6:]

        if not last_data:
            raise ConnectionError("No data received from SSE stream")

        result = json.loads(last_data)
        if isinstance(result, list) and len(result) >= 5:
            self._chat_history = result[1] or []
            self._state = result[2] or {}
            self._metrics = result[3]

            if self._chat_history:
                last_msg = self._chat_history[-1]
                return self._extract_text(last_msg)

        return str(result[-1]) if isinstance(result, list) and result else "(empty response)"

    def reset(self):
        """Reset conversation state via the clear endpoint."""
        headers = {"Content-Type": "application/json"}
        if self._hf_token:
            headers["Authorization"] = f"Bearer {self._hf_token}"

        try:
            payload = {"data": [self._state], "session_hash": self._session_hash}
            resp = self._client.post(
                f"{self._base_url}/gradio_api/call/clear_conversation",
                json=payload,
                headers=headers,
            )
            if resp.status_code == 200:
                event_id = resp.json().get("event_id")
                if event_id:
                    self._client.get(
                        f"{self._base_url}/gradio_api/call/clear_conversation/{event_id}",
                        headers=headers,
                    )
        except Exception:
            pass

        self._chat_history = []
        self._state = {}
        self._metrics = None
        self._session_hash = f"adv_test_{int(time.time())}"


# ------------------------------------------------------------------
# Scenario loader (YAML with behavioral assertions)
# ------------------------------------------------------------------

def load_adversarial_scenario(path: Path) -> dict:
    """Load an adversarial scenario YAML file."""
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data


def parse_assertions(raw_assertions: list[dict]) -> list[BehavioralAssertion]:
    """Parse assertion dicts into BehavioralAssertion objects."""
    assertions = []
    for a in raw_assertions:
        # Accept both 'substring' and 'value' as the substring field
        substr = a.get("substring", "") or a.get("value", "")
        assertions.append(BehavioralAssertion(
            type=a.get("type", ""),
            tool=a.get("tool", ""),
            forbidden=a.get("forbidden", []),
            substring=substr,
        ))
    return assertions


# ------------------------------------------------------------------
# Test runner
# ------------------------------------------------------------------

def run_scenario(
    client: LiveSpaceClient | LiveSpaceHTTPClient,
    scenario_path: Path,
    verbose: bool = True,
) -> ScenarioResult:
    """Run a single adversarial scenario against the live Space."""
    data = load_adversarial_scenario(scenario_path)
    name = data.get("name", scenario_path.stem)
    description = data.get("description", "")
    tags = data.get("tags", [])
    turns = data.get("turns", [])

    result = ScenarioResult(
        scenario_name=name,
        description=description,
        tags=tags,
    )

    if verbose:
        print(f"\n{'='*70}")
        print(f"SCENARIO: {name}")
        print(f"{'='*70}")
        print(f"  {description.strip()}")
        print(f"  Tags: {tags}")
        print(f"  Turns: {len(turns)}")
        print()

    client.reset()

    for i, turn in enumerate(turns):
        message = turn.get("message", "")
        raw_assertions = turn.get("assertions", [])
        assertions = parse_assertions(raw_assertions)

        if verbose:
            print(f"  Turn {i+1}/{len(turns)}")
            print(f"  USER: {message[:100]}{'...' if len(message) > 100 else ''}")

        turn_result = TurnResult(
            turn_index=i,
            user_message=message,
            agent_response="",
        )

        # Send message to live Space
        start = time.time()
        try:
            response_text = client.send_message(message)
            turn_result.latency_seconds = time.time() - start
            turn_result.agent_response = response_text

            if verbose:
                truncated = response_text[:200] + ("..." if len(response_text) > 200 else "")
                print(f"  AGENT: {truncated}")
                print(f"  Latency: {turn_result.latency_seconds:.1f}s")

        except Exception as e:
            turn_result.latency_seconds = time.time() - start
            turn_result.error = str(e)
            if verbose:
                print(f"  ERROR: {e}")
            result.turn_results.append(turn_result)
            result.total_assertions += len(assertions)
            result.failed_assertions += len(assertions)
            continue

        # Evaluate behavioral assertions
        for assertion in assertions:
            passed, explanation = evaluate_behavioral_assertion(
                assertion=assertion,
                agent_text=response_text,
                tool_calls=[],  # No tool call visibility from external API
            )

            result.total_assertions += 1
            if passed:
                result.passed_assertions += 1
                turn_result.assertions_passed.append((assertion.type, explanation))
                if verbose:
                    print(f"    PASS: {assertion.type} -- {explanation}")
            else:
                result.failed_assertions += 1
                turn_result.assertions_failed.append((assertion.type, explanation))
                if verbose:
                    print(f"    FAIL: {assertion.type} -- {explanation}")

        result.turn_results.append(turn_result)
        result.total_latency += turn_result.latency_seconds

        if verbose:
            print()

        # Small delay between turns to avoid rate limiting
        time.sleep(1.0)

    if verbose:
        status = "PASSED" if result.passed else "FAILED"
        print(f"  Result: {status} ({result.passed_assertions}/{result.total_assertions} assertions)")
        print(f"  Total latency: {result.total_latency:.1f}s")

    return result


# ------------------------------------------------------------------
# Supabase verification
# ------------------------------------------------------------------

def verify_supabase_logs(
    scenario_result: ScenarioResult,
    verbose: bool = True,
) -> bool:
    """Check that conversation logs were written to Supabase."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        if verbose:
            print("  Supabase credentials not found -- skipping verification")
        return False

    try:
        from supabase import create_client
        client = create_client(supabase_url, supabase_key)

        # Check recent conversation logs
        result = (
            client.table("conversation_logs")
            .select("*")
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )

        if not result.data:
            if verbose:
                print("  No conversation logs found in Supabase")
            return False

        log_count = len(result.data)
        user_msgs = [r for r in result.data if r["role"] == "user"]
        asst_msgs = [r for r in result.data if r["role"] == "assistant"]
        with_metrics = [r for r in asst_msgs if r.get("metrics")]

        if verbose:
            print(f"  Supabase logs: {log_count} recent entries")
            print(f"    User messages: {len(user_msgs)}")
            print(f"    Assistant messages: {len(asst_msgs)}")
            print(f"    With metrics: {len(with_metrics)}")

        return log_count > 0

    except Exception as e:
        if verbose:
            print(f"  Supabase check failed: {e}")
        return False


# ------------------------------------------------------------------
# Report generator
# ------------------------------------------------------------------

def generate_report(results: list[ScenarioResult]) -> str:
    """Generate a markdown report of all scenario results."""
    lines = [
        "# Adversarial Test Report",
        f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]

    total_scenarios = len(results)
    passed_scenarios = sum(1 for r in results if r.passed)
    total_assertions = sum(r.total_assertions for r in results)
    passed_assertions = sum(r.passed_assertions for r in results)
    failed_assertions = sum(r.failed_assertions for r in results)

    lines.extend([
        "## Summary",
        f"- **Scenarios:** {passed_scenarios}/{total_scenarios} passed",
        f"- **Assertions:** {passed_assertions}/{total_assertions} passed, {failed_assertions} failed",
        f"- **Total latency:** {sum(r.total_latency for r in results):.1f}s",
        "",
    ])

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        lines.extend([
            f"## [{status}] {r.scenario_name}",
            f"*{r.description.strip()}*",
            f"Tags: `{'`, `'.join(r.tags)}`",
            "",
        ])

        for t in r.turn_results:
            t_status = "PASS" if t.passed else "FAIL"
            lines.append(f"### Turn {t.turn_index + 1} [{t_status}] ({t.latency_seconds:.1f}s)")
            lines.append(f"**User:** {t.user_message}")
            lines.append("")

            if t.error:
                lines.append(f"**Error:** {t.error}")
            else:
                lines.append(f"**Agent:** {t.agent_response[:500]}")

            lines.append("")

            if t.assertions_failed:
                lines.append("**Failed assertions:**")
                for atype, explanation in t.assertions_failed:
                    lines.append(f"- `{atype}`: {explanation}")
                lines.append("")

            if t.assertions_passed:
                lines.append(f"*{len(t.assertions_passed)} assertion(s) passed*")
                lines.append("")

    return "\n".join(lines)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Run adversarial tests against live HF Space")
    parser.add_argument(
        "--space", default="chusla/improvement-axiom",
        help="HuggingFace Space ID (default: chusla/improvement-axiom)",
    )
    parser.add_argument(
        "--scenario", default=None,
        help="Run a specific scenario by name (without .yaml). Default: all adversarial_* scenarios",
    )
    parser.add_argument(
        "--scenarios-dir", default=str(PROJECT_ROOT / "scenarios"),
        help="Directory containing scenario YAML files",
    )
    parser.add_argument(
        "--check-supabase", action="store_true",
        help="Also verify that conversation logs appear in Supabase",
    )
    parser.add_argument(
        "--hf-token", default=None,
        help="HuggingFace token (for private Spaces)",
    )
    parser.add_argument(
        "--use-http", action="store_true",
        help="Use direct HTTP client instead of gradio_client",
    )
    parser.add_argument(
        "--output", default=None,
        help="Path to write the markdown report (default: print to stdout)",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress per-turn output",
    )

    args = parser.parse_args()
    verbose = not args.quiet

    # Find scenario files
    scenarios_dir = Path(args.scenarios_dir)
    if args.scenario:
        paths = [scenarios_dir / f"{args.scenario}.yaml"]
        if not paths[0].exists():
            # Try with adversarial_ prefix
            paths = [scenarios_dir / f"adversarial_{args.scenario}.yaml"]
        if not paths[0].exists():
            print(f"Scenario not found: {args.scenario}")
            sys.exit(1)
    else:
        paths = sorted(scenarios_dir.glob("adversarial_*.yaml"))
        if not paths:
            print(f"No adversarial scenarios found in {scenarios_dir}")
            sys.exit(1)

    print(f"Adversarial Live Test Runner")
    print(f"Space: {args.space}")
    print(f"Scenarios: {len(paths)}")
    print()

    # Create client
    if args.use_http:
        client = LiveSpaceHTTPClient(args.space, hf_token=args.hf_token)
    else:
        client = LiveSpaceClient(args.space, hf_token=args.hf_token)

    # Run scenarios
    results: list[ScenarioResult] = []
    for path in paths:
        result = run_scenario(client, path, verbose=verbose)

        if args.check_supabase:
            print("\n  Checking Supabase...")
            result.supabase_verified = verify_supabase_logs(result, verbose=verbose)

        results.append(result)

    # Summary
    print(f"\n{'='*70}")
    print(f"FINAL RESULTS")
    print(f"{'='*70}")

    total_pass = sum(1 for r in results if r.passed)
    total_fail = len(results) - total_pass
    total_assertions = sum(r.total_assertions for r in results)
    total_assertion_pass = sum(r.passed_assertions for r in results)
    total_assertion_fail = sum(r.failed_assertions for r in results)

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.scenario_name} "
              f"({r.passed_assertions}/{r.total_assertions} assertions, "
              f"{r.total_latency:.1f}s)")

    print()
    print(f"  Scenarios: {total_pass} passed, {total_fail} failed")
    print(f"  Assertions: {total_assertion_pass}/{total_assertions} passed, "
          f"{total_assertion_fail} failed")

    # Generate report
    report = generate_report(results)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(report, encoding="utf-8")
        print(f"\n  Report written to: {output_path}")
    else:
        # Also write to default location
        report_path = PROJECT_ROOT / "tests" / "adversarial_report.md"
        report_path.write_text(report, encoding="utf-8")
        print(f"\n  Report written to: {report_path}")

    # Exit code reflects pass/fail
    sys.exit(0 if total_fail == 0 else 1)


if __name__ == "__main__":
    main()
