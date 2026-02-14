"""Integration tests for the Opus agent.

These tests make LIVE calls to the Anthropic API and are therefore:
- Marked with @pytest.mark.integration and @pytest.mark.slow
- Skipped if ANTHROPIC_API_KEY is not set in the environment
- Not run by default in CI (use: pytest -m integration)

Each test loads a persona, runs the full conversation through
OpusAgent, and asserts behavioral expectations.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Skip entire module if no API key
pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY not set",
    ),
]

from resonance_alignment.agent.wrapper import OpusAgent
from resonance_alignment.agent.personas import (
    load_all_personas,
    evaluate_behavioral_assertion,
)

PERSONAS_DIR = Path(__file__).resolve().parents[2] / "personas"


def _discover_personas():
    """Discover all persona YAML files."""
    if not PERSONAS_DIR.is_dir():
        return []
    return load_all_personas(PERSONAS_DIR)


_personas = _discover_personas()


@pytest.fixture
def agent():
    """Create an OpusAgent for testing."""
    api_key = os.environ["ANTHROPIC_API_KEY"]
    return OpusAgent(
        api_key=api_key,
        model=os.environ.get("TEST_MODEL", "claude-sonnet-4-20250514"),
        user_id="test_user",
    )


@pytest.mark.parametrize(
    "persona",
    _personas,
    ids=[p.name for p in _personas],
)
def test_persona_conversation(agent, persona, tmp_path):
    """Run a persona through the agent and check behavioral assertions."""
    log_lines: list[str] = []
    log_lines.append(f"=== Persona: {persona.name} ===")
    log_lines.append(f"Description: {persona.description}")
    log_lines.append("")

    all_failures: list[str] = []

    for turn_idx, turn in enumerate(persona.turns):
        log_lines.append(f"--- Turn {turn_idx} ---")
        log_lines.append(f"User: {turn.message}")

        response = agent.process_message(turn.message)

        log_lines.append(f"Agent: {response.text[:500]}...")
        log_lines.append(f"Tools called: {response.tool_calls_made}")
        log_lines.append("")

        # Evaluate assertions
        for assertion in turn.assertions:
            passed, explanation = evaluate_behavioral_assertion(
                assertion, response.text, response.tool_calls_made
            )
            status = "PASS" if passed else "FAIL"
            log_lines.append(f"  [{status}] {assertion.type}: {explanation}")

            if not passed:
                all_failures.append(
                    f"Turn {turn_idx} ({assertion.type}): {explanation}"
                )

        log_lines.append("")

    # Write conversation log
    safe_name = persona.name.lower().replace(" ", "_")
    log_path = tmp_path / f"conversation_{safe_name}.txt"
    log_path.write_text("\n".join(log_lines), encoding="utf-8")

    if all_failures:
        failure_msg = "\n".join(f"  - {f}" for f in all_failures)
        pytest.fail(
            f"Persona '{persona.name}' had {len(all_failures)} behavioral "
            f"assertion failures:\n{failure_msg}"
        )


def test_agent_tool_dispatch_smoke():
    """Smoke test: verify OpusAgent can be instantiated (without API call)."""
    # This test doesn't make API calls -- it just checks import/construction
    # The API key check happens at message processing time
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")

    agent = OpusAgent(api_key=api_key, user_id="smoke_test")
    assert agent.system is not None
    assert agent.latest_experience_id is None


def test_single_turn_experience():
    """Test a single experience recording turn."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")

    agent = OpusAgent(
        api_key=api_key,
        model=os.environ.get("TEST_MODEL", "claude-sonnet-4-20250514"),
        user_id="single_turn_user",
    )

    response = agent.process_message(
        "I spent the whole day painting a landscape. It was really meditative."
    )

    # Agent should have called process_experience
    assert "process_experience" in response.tool_calls_made, (
        f"Expected process_experience in tool calls, got {response.tool_calls_made}"
    )

    # Agent should have a text response
    assert len(response.text) > 0, "Agent should have generated a text response"

    # Agent should have an assessment
    assert response.assessment is not None, "Should have an assessment result"

    # Assessment should be provisional
    assert response.assessment.is_provisional, (
        "First experience should be provisional"
    )
