"""Scenario runner -- the core executor for the harness.

Creates a fresh ResonanceAlignmentSystem per scenario, iterates
through steps, applies simulated time offsets, evaluates assertions
at each step, and collects a full evolution trace.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

from resonance_alignment.core.models import FollowUp, AssessmentResult
from resonance_alignment.harness.assertions import evaluate_assertion
from resonance_alignment.harness.models import (
    AssertionResult,
    Scenario,
    ScenarioReport,
    ScenarioStep,
    StepResult,
)
from resonance_alignment.storage.memory import InMemoryStorage
from resonance_alignment.system import ResonanceAlignmentSystem


class ScenarioRunner:
    """Runs a scenario through the Improvement Axiom framework.

    Each scenario gets a fresh system instance so they're fully
    isolated.  Time is simulated via ``delay_days`` on each step.

    Args:
        storage: Optional storage backend.  Defaults to InMemoryStorage.
        web_client: Optional web client for scenarios that need it.
    """

    def __init__(
        self,
        storage: Any | None = None,
        web_client: Any | None = None,
    ) -> None:
        self._storage_factory = storage
        self._web_client = web_client

    def run(self, scenario: Scenario) -> ScenarioReport:
        """Execute a full scenario and return a report."""
        wall_start = time.monotonic()

        # Fresh system per scenario
        storage = self._storage_factory or InMemoryStorage()
        system = ResonanceAlignmentSystem(
            web_client=self._web_client,
            storage=storage,
        )

        # Simulated clock starts at a fixed reference point for determinism
        sim_time = datetime(2025, 1, 1, tzinfo=timezone.utc)

        step_results: list[StepResult] = []
        evolution: list[dict[str, Any]] = []
        experience_id: str | None = None
        previous_result: Any | None = None

        for i, step in enumerate(scenario.steps):
            # Advance simulated clock
            sim_time += timedelta(days=step.delay_days)

            # Execute the step
            result = self._execute_step(
                system, scenario, step, sim_time, experience_id
            )

            # Track the experience ID from the first experience step
            if step.action == "experience" and result is not None:
                if isinstance(result, AssessmentResult):
                    experience_id = result.experience.id

            # Evaluate assertions
            passed_assertions: list[AssertionResult] = []
            failed_assertions: list[AssertionResult] = []

            for assertion in step.assertions:
                ar = evaluate_assertion(result, assertion, previous_result)
                if ar.passed:
                    passed_assertions.append(ar)
                else:
                    failed_assertions.append(ar)

            step_results.append(
                StepResult(
                    step_index=i,
                    action=step.action,
                    assessment_result=result,
                    passed_assertions=passed_assertions,
                    failed_assertions=failed_assertions,
                    simulated_time=sim_time,
                )
            )

            # Record evolution trace
            if isinstance(result, AssessmentResult):
                evolution.append(
                    self._snapshot_evolution(i, result, sim_time)
                )

            previous_result = result

        # Aggregate
        total = sum(
            len(sr.passed_assertions) + len(sr.failed_assertions)
            for sr in step_results
        )
        passed_count = sum(len(sr.passed_assertions) for sr in step_results)
        failed_count = sum(len(sr.failed_assertions) for sr in step_results)

        # Determine final arc
        final_arc = ""
        if step_results and isinstance(step_results[-1].assessment_result, AssessmentResult):
            final_arc = step_results[-1].assessment_result.arc_trend

        wall_elapsed = time.monotonic() - wall_start

        return ScenarioReport(
            scenario_name=scenario.name,
            scenario_description=scenario.description,
            step_results=step_results,
            passed=(failed_count == 0),
            total_assertions=total,
            passed_count=passed_count,
            failed_count=failed_count,
            duration_seconds=round(wall_elapsed, 3),
            final_arc=final_arc,
            evolution=evolution,
        )

    # ------------------------------------------------------------------
    # Step execution
    # ------------------------------------------------------------------

    @staticmethod
    def _execute_step(
        system: ResonanceAlignmentSystem,
        scenario: Scenario,
        step: ScenarioStep,
        sim_time: datetime,
        experience_id: str | None,
    ) -> Any:
        """Execute a single step and return the raw framework result."""
        if step.action == "experience":
            return system.process_experience(
                user_id=scenario.user_id,
                experience_description=step.params.get("description", ""),
                user_rating=float(step.params.get("user_rating", 0.5)),
                context=step.params.get("context", ""),
            )

        elif step.action == "follow_up":
            if experience_id is None:
                raise RuntimeError(
                    f"Step '{step.action}' requires a prior 'experience' step "
                    f"in scenario '{scenario.name}'."
                )
            follow_up = FollowUp(
                experience_id=experience_id,
                timestamp=sim_time,
                content=step.params.get("content", ""),
                created_something=bool(step.params.get("created_something", False)),
                creation_description=step.params.get("creation_description", ""),
                creation_magnitude=float(step.params.get("creation_magnitude", 0.0)),
                shared_or_taught=bool(step.params.get("shared_or_taught", False)),
                inspired_further_action=bool(
                    step.params.get("inspired_further_action", False)
                ),
            )
            return system.process_follow_up(
                user_id=scenario.user_id,
                experience_id=experience_id,
                follow_up=follow_up,
            )

        elif step.action == "artifact":
            if experience_id is None:
                raise RuntimeError(
                    f"Step '{step.action}' requires a prior 'experience' step "
                    f"in scenario '{scenario.name}'."
                )
            return system.submit_artifact(
                user_id=scenario.user_id,
                experience_id=experience_id,
                url=step.params.get("url", ""),
                user_claim=step.params.get("user_claim", ""),
                platform=step.params.get("platform", ""),
            )

        raise ValueError(f"Unknown action: {step.action}")

    @staticmethod
    def _snapshot_evolution(
        step_index: int,
        result: AssessmentResult,
        sim_time: datetime,
    ) -> dict[str, Any]:
        """Capture vector state at a step for the evolution trace."""
        vec = result.trajectory.current_vector if result.trajectory else None
        return {
            "step": step_index,
            "time": sim_time.isoformat(),
            "direction": round(vec.direction, 4) if vec else 0.0,
            "magnitude": round(vec.magnitude, 4) if vec else 0.0,
            "confidence": round(vec.confidence, 4) if vec else 0.0,
            "intention": result.experience.provisional_intention.value,
            "quality": round(result.experience.quality_score, 4),
            "matrix_position": result.experience.matrix_position,
        }
