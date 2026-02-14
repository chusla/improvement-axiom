"""Scenario harness for testing the Improvement Axiom framework.

Provides YAML-driven scenario testing so that:
- Core developers validate alignment properties
- Third parties run their own scenario suites
- CI detects regressions automatically

Usage:
    from resonance_alignment.harness import ScenarioRunner, load_scenario

    scenario = load_scenario("scenarios/gamer_to_developer.yaml")
    runner = ScenarioRunner()
    report = runner.run(scenario)
    print(report.passed)
"""

from resonance_alignment.harness.models import (
    Assertion,
    Scenario,
    ScenarioReport,
    ScenarioStep,
    StepResult,
)
from resonance_alignment.harness.assertions import evaluate_assertion
from resonance_alignment.harness.loader import load_scenario, load_all_scenarios
from resonance_alignment.harness.runner import ScenarioRunner
from resonance_alignment.harness.reporter import generate_markdown, generate_json, generate_aggregate

__all__ = [
    "Assertion",
    "Scenario",
    "ScenarioReport",
    "ScenarioStep",
    "StepResult",
    "evaluate_assertion",
    "load_scenario",
    "load_all_scenarios",
    "ScenarioRunner",
    "generate_markdown",
    "generate_json",
    "generate_aggregate",
]
