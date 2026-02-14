"""Pytest-parametrized scenario tests.

Discovers all YAML files in the ``scenarios/`` directory and runs each
through the ScenarioRunner.  Third parties can add their own YAML
scenarios and they'll be picked up automatically.

Usage:
    pytest tests/test_harness/test_scenarios.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from resonance_alignment.harness.loader import load_all_scenarios
from resonance_alignment.harness.runner import ScenarioRunner
from resonance_alignment.harness.reporter import (
    generate_markdown,
    generate_json,
    generate_aggregate,
)

# Path to the scenarios directory (relative to project root)
SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "scenarios"


def _discover_scenarios():
    """Discover all scenario YAML files for parametrisation."""
    if not SCENARIOS_DIR.is_dir():
        return []
    return load_all_scenarios(SCENARIOS_DIR)


# Parametrise: one test case per scenario file
_scenarios = _discover_scenarios()


@pytest.mark.parametrize(
    "scenario",
    _scenarios,
    ids=[s.name for s in _scenarios],
)
def test_scenario(scenario, tmp_path):
    """Run a scenario and verify all assertions pass."""
    runner = ScenarioRunner()
    report = runner.run(scenario)

    # Generate reports for inspection (write to tmp_path)
    md = generate_markdown(report)
    json_report = generate_json(report)

    report_dir = tmp_path / "reports"
    report_dir.mkdir(exist_ok=True)

    safe_name = scenario.name.lower().replace(" ", "_")
    (report_dir / f"{safe_name}.md").write_text(md, encoding="utf-8")
    (report_dir / f"{safe_name}.json").write_text(
        json.dumps(json_report, indent=2, default=str), encoding="utf-8"
    )

    # Collect failure messages for a readable assertion error
    failures: list[str] = []
    for sr in report.step_results:
        for ar in sr.failed_assertions:
            failures.append(
                f"  Step {sr.step_index} ({sr.action}): "
                f"{ar.assertion.label or ar.assertion.field} -- {ar.message}"
            )

    assert report.passed, (
        f"Scenario '{scenario.name}' failed "
        f"({report.failed_count}/{report.total_assertions} assertions):\n"
        + "\n".join(failures)
    )


def test_aggregate_report(tmp_path):
    """Generate an aggregate report across all scenarios."""
    if not _scenarios:
        pytest.skip("No scenarios found")

    runner = ScenarioRunner()
    reports = [runner.run(s) for s in _scenarios]

    aggregate_md = generate_aggregate(reports)

    report_path = tmp_path / "aggregate_report.md"
    report_path.write_text(aggregate_md, encoding="utf-8")

    # Verify the aggregate report is non-empty and has expected structure
    assert "Scenario Harness: Aggregate Report" in aggregate_md
    assert f"{len(reports)}" in aggregate_md


def test_assertion_engine_basics():
    """Unit test the assertion engine with synthetic data."""
    from resonance_alignment.harness.assertions import evaluate_assertion, _resolve_field
    from resonance_alignment.harness.models import Assertion
    from resonance_alignment.core.models import (
        AssessmentResult,
        Experience,
        IntentionSignal,
        UserTrajectory,
        VectorSnapshot,
    )

    # Build a synthetic result
    exp = Experience(
        provisional_intention=IntentionSignal.CREATIVE_INTENT,
        intention_confidence=0.6,
        quality_score=0.75,
    )
    traj = UserTrajectory(
        current_vector=VectorSnapshot(direction=0.4, magnitude=0.5, confidence=0.3),
    )
    result = AssessmentResult(experience=exp, trajectory=traj)

    # Test field resolution
    assert _resolve_field(result, "experience.intention_confidence") == 0.6
    assert _resolve_field(result, "trajectory.current_vector.direction") == 0.4
    assert _resolve_field(result, "experience.provisional_intention") == "creative"

    # Test operators
    a1 = Assertion(field="experience.intention_confidence", op=">", value=0.5, label="confidence > 0.5")
    r1 = evaluate_assertion(result, a1)
    assert r1.passed is True

    a2 = Assertion(field="trajectory.current_vector.direction", op="<", value=0.5, label="dir < 0.5")
    r2 = evaluate_assertion(result, a2)
    assert r2.passed is True

    a3 = Assertion(field="experience.provisional_intention", op="in", value=["creative", "mixed"])
    r3 = evaluate_assertion(result, a3)
    assert r3.passed is True

    a4 = Assertion(field="experience.quality_score", op="between", value=[0.5, 0.9])
    r4 = evaluate_assertion(result, a4)
    assert r4.passed is True

    # Test failure
    a5 = Assertion(field="experience.intention_confidence", op=">", value=0.9)
    r5 = evaluate_assertion(result, a5)
    assert r5.passed is False
