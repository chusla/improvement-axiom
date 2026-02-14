"""Assertion engine for the scenario harness.

Resolves dot-path field references on AssessmentResult (and its nested
objects) and evaluates comparison operators.

Supported operators:
    <, >, <=, >=     -- numeric comparisons
    ==, !=           -- equality (works for strings, numbers, enums)
    in               -- value membership in a list
    contains         -- substring or item containment
    between          -- range check: value is [low, high]
    changed          -- field differs from the previous step's value
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from resonance_alignment.harness.models import Assertion, AssertionResult


def _resolve_field(obj: Any, dot_path: str) -> Any:
    """Walk a dot-separated path to extract a nested value.

    Examples:
        _resolve_field(result, "experience.intention_confidence")
        _resolve_field(result, "trajectory.current_vector.direction")
        _resolve_field(result, "experience.provisional_intention")
    """
    current = obj
    for part in dot_path.split("."):
        if current is None:
            raise AttributeError(
                f"Cannot resolve '{dot_path}': hit None at '{part}'"
            )
        # Support dict-like access (explanation dict, quality_dimensions, etc.)
        if isinstance(current, dict):
            if part not in current:
                raise KeyError(
                    f"Cannot resolve '{dot_path}': key '{part}' not in dict"
                )
            current = current[part]
        else:
            if not hasattr(current, part):
                raise AttributeError(
                    f"Cannot resolve '{dot_path}': '{type(current).__name__}' "
                    f"has no attribute '{part}'"
                )
            current = getattr(current, part)

    # Unwrap enums to their value for comparison
    if isinstance(current, Enum):
        current = current.value

    return current


def evaluate_assertion(
    result: Any,
    assertion: Assertion,
    previous_result: Any | None = None,
) -> AssertionResult:
    """Evaluate a single assertion against a framework result.

    Args:
        result: The AssessmentResult (or ArtifactVerification) to check.
        assertion: The assertion to evaluate.
        previous_result: The result from the prior step (for ``changed`` op).

    Returns:
        AssertionResult with pass/fail and explanation.
    """
    try:
        actual = _resolve_field(result, assertion.field)
    except (AttributeError, KeyError) as exc:
        return AssertionResult(
            assertion=assertion,
            passed=False,
            actual_value=None,
            message=f"Field resolution error: {exc}",
        )

    op = assertion.op
    expected = assertion.value
    passed = False
    message = ""

    try:
        if op == "<":
            passed = float(actual) < float(expected)
        elif op == ">":
            passed = float(actual) > float(expected)
        elif op == "<=":
            passed = float(actual) <= float(expected)
        elif op == ">=":
            passed = float(actual) >= float(expected)
        elif op == "==":
            passed = _eq(actual, expected)
        elif op == "!=":
            passed = not _eq(actual, expected)
        elif op == "in":
            # actual should be in the expected list
            if isinstance(expected, list):
                # Compare as strings for enum-like fields
                passed = str(actual) in [str(v) for v in expected]
            else:
                passed = actual in expected
        elif op == "contains":
            passed = str(expected) in str(actual)
        elif op == "between":
            low, high = expected
            passed = float(low) <= float(actual) <= float(high)
        elif op == "changed":
            if previous_result is None:
                passed = False
                message = "No previous step to compare against for 'changed' op"
            else:
                try:
                    prev_actual = _resolve_field(previous_result, assertion.field)
                    passed = actual != prev_actual
                    message = f"previous={prev_actual}, current={actual}"
                except (AttributeError, KeyError):
                    passed = True  # field didn't exist before → it changed
                    message = "Field did not exist in previous step"
        else:
            message = f"Unknown operator: {op}"
            return AssertionResult(
                assertion=assertion,
                passed=False,
                actual_value=actual,
                message=message,
            )

        if not message:
            status = "PASS" if passed else "FAIL"
            message = (
                f"[{status}] {assertion.label or assertion.field}: "
                f"actual={actual!r} {op} expected={expected!r}"
            )

    except (TypeError, ValueError) as exc:
        return AssertionResult(
            assertion=assertion,
            passed=False,
            actual_value=actual,
            message=f"Comparison error: {exc} (actual={actual!r}, expected={expected!r})",
        )

    return AssertionResult(
        assertion=assertion,
        passed=passed,
        actual_value=actual,
        message=message,
    )


def _eq(a: Any, b: Any) -> bool:
    """Flexible equality: handles enums, strings, numbers."""
    if isinstance(a, Enum):
        a = a.value
    if isinstance(b, Enum):
        b = b.value
    # Try numeric comparison
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        pass
    return str(a) == str(b)
