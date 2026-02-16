"""Report generation for the scenario harness.

Produces both human-readable Markdown and machine-readable JSON
from ScenarioReport objects.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from resonance_alignment.harness.models import ScenarioReport, StepResult


# ------------------------------------------------------------------
# Markdown
# ------------------------------------------------------------------

def generate_markdown(report: ScenarioReport) -> str:
    """Generate a human-readable Markdown report for a single scenario."""
    status = "PASS" if report.passed else "FAIL"
    lines: list[str] = [
        f"# Scenario: {report.scenario_name}",
        "",
        f"**Status:** {status}  ",
        f"**Description:** {report.scenario_description}  ",
        f"**Assertions:** {report.passed_count}/{report.total_assertions} passed  ",
        f"**Duration:** {report.duration_seconds:.3f}s  ",
        f"**Final arc:** {report.final_arc or 'N/A'}  ",
        "",
    ]

    # Evolution table
    if report.evolution:
        lines.append("## Vector Evolution")
        lines.append("")
        lines.append(
            "| Step | Direction | Magnitude | Confidence | Intention | Quality | Matrix Position |"
        )
        lines.append(
            "|------|-----------|-----------|------------|-----------|---------|-----------------|"
        )
        for ev in report.evolution:
            lines.append(
                f"| {ev['step']} "
                f"| {ev['direction']:+.4f} "
                f"| {ev['magnitude']:.4f} "
                f"| {ev['confidence']:.4f} "
                f"| {ev['intention']} "
                f"| {ev['quality']:.4f} "
                f"| {ev['matrix_position']} |"
            )
        lines.append("")

    # Per-step detail
    lines.append("## Step Details")
    lines.append("")

    for sr in report.step_results:
        step_status = "PASS" if sr.all_passed else "FAIL"
        lines.append(f"### Step {sr.step_index} ({sr.action}) [{step_status}]")
        lines.append("")
        lines.append(f"Simulated time: {sr.simulated_time.isoformat()}")
        lines.append("")

        if sr.passed_assertions:
            for ar in sr.passed_assertions:
                label = ar.assertion.label or ar.assertion.field
                lines.append(f"- [x] {label}: {ar.message}")
        if sr.failed_assertions:
            for ar in sr.failed_assertions:
                label = ar.assertion.label or ar.assertion.field
                lines.append(f"- [ ] **{label}**: {ar.message}")
        lines.append("")

    return "\n".join(lines)


# ------------------------------------------------------------------
# JSON
# ------------------------------------------------------------------

def generate_json(report: ScenarioReport) -> dict[str, Any]:
    """Generate a machine-readable JSON-compatible dict for a scenario."""
    return {
        "scenario_name": report.scenario_name,
        "scenario_description": report.scenario_description,
        "passed": report.passed,
        "total_assertions": report.total_assertions,
        "passed_count": report.passed_count,
        "failed_count": report.failed_count,
        "duration_seconds": report.duration_seconds,
        "final_arc": report.final_arc,
        "evolution": report.evolution,
        "steps": [
            {
                "step_index": sr.step_index,
                "action": sr.action,
                "simulated_time": sr.simulated_time.isoformat(),
                "all_passed": sr.all_passed,
                "passed_assertions": [
                    _assertion_result_to_dict(ar) for ar in sr.passed_assertions
                ],
                "failed_assertions": [
                    _assertion_result_to_dict(ar) for ar in sr.failed_assertions
                ],
            }
            for sr in report.step_results
        ],
    }


def _assertion_result_to_dict(ar: Any) -> dict[str, Any]:
    """Convert an AssertionResult to a JSON-serialisable dict."""
    return {
        "field": ar.assertion.field,
        "op": ar.assertion.op,
        "expected": _safe_serialize(ar.assertion.value),
        "actual": _safe_serialize(ar.actual_value),
        "passed": ar.passed,
        "label": ar.assertion.label,
        "message": ar.message,
    }


def _safe_serialize(val: Any) -> Any:
    """Make a value JSON-serialisable."""
    if isinstance(val, datetime):
        return val.isoformat()
    if hasattr(val, "value"):  # Enum
        return val.value
    if isinstance(val, (list, tuple)):
        return [_safe_serialize(v) for v in val]
    if isinstance(val, dict):
        return {k: _safe_serialize(v) for k, v in val.items()}
    return val


# ------------------------------------------------------------------
# Aggregate
# ------------------------------------------------------------------

def generate_aggregate(reports: list[ScenarioReport]) -> str:
    """Generate a summary Markdown report across multiple scenarios."""
    total_scenarios = len(reports)
    passed_scenarios = sum(1 for r in reports if r.passed)
    total_assertions = sum(r.total_assertions for r in reports)
    passed_assertions = sum(r.passed_count for r in reports)
    total_time = sum(r.duration_seconds for r in reports)

    lines: list[str] = [
        "# Scenario Harness: Aggregate Report",
        "",
        f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"**Scenarios:** {passed_scenarios}/{total_scenarios} passed  ",
        f"**Assertions:** {passed_assertions}/{total_assertions} passed  ",
        f"**Total duration:** {total_time:.3f}s  ",
        "",
        "## Results",
        "",
        "| Scenario | Status | Assertions | Duration | Final Arc |",
        "|----------|--------|------------|----------|-----------|",
    ]

    for r in reports:
        status = "PASS" if r.passed else "**FAIL**"
        lines.append(
            f"| {r.scenario_name} "
            f"| {status} "
            f"| {r.passed_count}/{r.total_assertions} "
            f"| {r.duration_seconds:.3f}s "
            f"| {r.final_arc or 'N/A'} |"
        )

    lines.append("")

    # List failures
    failed_reports = [r for r in reports if not r.passed]
    if failed_reports:
        lines.append("## Failures")
        lines.append("")
        for r in failed_reports:
            lines.append(f"### {r.scenario_name}")
            lines.append("")
            for sr in r.step_results:
                for ar in sr.failed_assertions:
                    label = ar.assertion.label or ar.assertion.field
                    lines.append(f"- Step {sr.step_index}: **{label}** -- {ar.message}")
            lines.append("")

    return "\n".join(lines)
