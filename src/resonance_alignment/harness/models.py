"""Data models for the scenario harness.

These models define the structure of scenario YAML files and the
results produced by running them through the framework.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Assertion:
    """A single assertion to evaluate after a scenario step.

    Attributes:
        field: Dot-path to a value on the AssessmentResult, e.g.
            ``experience.intention_confidence`` or
            ``trajectory.current_vector.direction``.
        op: Comparison operator.  One of: ``<``, ``>``, ``<=``, ``>=``,
            ``==``, ``!=``, ``in``, ``contains``, ``between``, ``changed``.
        value: The expected value (type depends on operator).
        label: Human-readable description shown in reports.
    """

    field: str = ""
    op: str = "=="
    value: Any = None
    label: str = ""


@dataclass
class ScenarioStep:
    """One step in a scenario.

    Attributes:
        action: One of ``experience``, ``follow_up``, or ``artifact``.
        params: Keyword arguments forwarded to the corresponding system
            entry point.
        delay_days: Simulated time elapsed since the *previous* step
            (days).  Used to backdate ``FollowUp.timestamp``.
        assertions: Assertions evaluated after this step executes.
    """

    action: str = "experience"
    params: dict[str, Any] = field(default_factory=dict)
    delay_days: float = 0.0
    assertions: list[Assertion] = field(default_factory=list)


@dataclass
class Scenario:
    """A complete test scenario loaded from YAML.

    Attributes:
        name: Short human-readable name.
        description: Longer narrative of what this scenario tests.
        user_id: The synthetic user_id for the scenario run.
        steps: Ordered list of steps to execute.
        expected_final_arc: Optional expected ``arc_trend`` after all
            steps complete (e.g. ``improving``, ``stable``).
        tags: Arbitrary tags for filtering (e.g. ``adversarial``).
    """

    name: str = ""
    description: str = ""
    user_id: str = "test_user"
    steps: list[ScenarioStep] = field(default_factory=list)
    expected_final_arc: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class AssertionResult:
    """Outcome of evaluating one assertion.

    Attributes:
        assertion: The original assertion.
        passed: Whether the assertion held.
        actual_value: The value that was resolved from the result.
        message: Human-readable explanation.
    """

    assertion: Assertion = field(default_factory=Assertion)
    passed: bool = False
    actual_value: Any = None
    message: str = ""


@dataclass
class StepResult:
    """Outcome of executing one scenario step.

    Attributes:
        step_index: Zero-based index into ``Scenario.steps``.
        action: The action type (``experience`` / ``follow_up`` / ``artifact``).
        assessment_result: The raw ``AssessmentResult`` from the framework
            (or ``ArtifactVerification`` for ``artifact`` steps).
        passed_assertions: Assertions that held.
        failed_assertions: Assertions that did not hold.
        simulated_time: The simulated UTC timestamp at this step.
    """

    step_index: int = 0
    action: str = ""
    assessment_result: Any = None
    passed_assertions: list[AssertionResult] = field(default_factory=list)
    failed_assertions: list[AssertionResult] = field(default_factory=list)
    simulated_time: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def all_passed(self) -> bool:
        return len(self.failed_assertions) == 0


@dataclass
class ScenarioReport:
    """Full report for one scenario run.

    Attributes:
        scenario_name: Name of the scenario.
        scenario_description: Description of the scenario.
        step_results: Per-step outcomes.
        passed: True only if every assertion in every step passed.
        total_assertions: Count of all assertions evaluated.
        passed_count: Count of assertions that passed.
        failed_count: Count of assertions that failed.
        duration_seconds: Wall-clock time for the run.
        final_arc: The ``arc_trend`` after all steps.
        evolution: List of vector snapshots (direction, magnitude,
            confidence) at each step for charting.
    """

    scenario_name: str = ""
    scenario_description: str = ""
    step_results: list[StepResult] = field(default_factory=list)
    passed: bool = False
    total_assertions: int = 0
    passed_count: int = 0
    failed_count: int = 0
    duration_seconds: float = 0.0
    final_arc: str = ""
    evolution: list[dict[str, Any]] = field(default_factory=list)
