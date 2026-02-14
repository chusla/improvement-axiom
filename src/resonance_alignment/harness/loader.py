"""YAML scenario loader with validation.

Loads scenario definitions from YAML files and converts them into
the harness data models.  Provides clear error messages when a
YAML file is malformed or missing required fields.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml  # PyYAML (stdlib-adjacent, shipped with most Python installs)

from resonance_alignment.harness.models import Assertion, Scenario, ScenarioStep


def load_scenario(path: str | Path) -> Scenario:
    """Load a single scenario from a YAML file.

    Raises:
        FileNotFoundError: If the path does not exist.
        ValueError: If the YAML is malformed or missing required fields.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {path}")

    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict):
        raise ValueError(f"Scenario file must be a YAML mapping, got {type(raw).__name__}: {path}")

    return _parse_scenario(raw, source=str(path))


def load_all_scenarios(directory: str | Path) -> list[Scenario]:
    """Load all ``*.yaml`` / ``*.yml`` scenario files from a directory.

    Returns scenarios sorted by filename for deterministic ordering.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")

    files = sorted(
        p for p in directory.iterdir()
        if p.suffix in (".yaml", ".yml") and p.is_file()
    )

    scenarios: list[Scenario] = []
    for f in files:
        result = load_scenario(f)
        if result is not None:
            scenarios.append(result)
    return scenarios


# ------------------------------------------------------------------
# Internal parsing helpers
# ------------------------------------------------------------------

def _parse_scenario(raw: dict[str, Any], source: str = "") -> Scenario:
    """Parse a raw YAML dict into a Scenario."""
    name = raw.get("name", "")
    if not name:
        raise ValueError(f"Scenario missing required 'name' field ({source})")

    steps_raw = raw.get("steps", [])
    if not isinstance(steps_raw, list) or len(steps_raw) == 0:
        # Adversarial scenarios use 'turns' format for a different runner;
        # skip them gracefully rather than raising an error.
        if raw.get("turns"):
            return None
        raise ValueError(f"Scenario '{name}' must have at least one step ({source})")

    steps = [_parse_step(s, i, name, source) for i, s in enumerate(steps_raw)]

    return Scenario(
        name=name,
        description=raw.get("description", ""),
        user_id=raw.get("user_id", "test_user"),
        steps=steps,
        expected_final_arc=raw.get("expected_final_arc", ""),
        tags=raw.get("tags", []),
    )


def _parse_step(
    raw: dict[str, Any], index: int, scenario_name: str, source: str
) -> ScenarioStep:
    """Parse a raw YAML dict into a ScenarioStep."""
    if not isinstance(raw, dict):
        raise ValueError(
            f"Step {index} in '{scenario_name}' must be a mapping ({source})"
        )

    action = raw.get("action", "")
    if action not in ("experience", "follow_up", "artifact"):
        raise ValueError(
            f"Step {index} in '{scenario_name}': action must be "
            f"'experience', 'follow_up', or 'artifact', got '{action}' ({source})"
        )

    params = raw.get("params", {})
    if not isinstance(params, dict):
        raise ValueError(
            f"Step {index} in '{scenario_name}': params must be a mapping ({source})"
        )

    delay_days = float(raw.get("delay_days", 0))

    assertions_raw = raw.get("assertions", [])
    assertions = [
        _parse_assertion(a, i, index, scenario_name, source)
        for i, a in enumerate(assertions_raw)
    ]

    return ScenarioStep(
        action=action,
        params=params,
        delay_days=delay_days,
        assertions=assertions,
    )


def _parse_assertion(
    raw: dict[str, Any],
    assertion_index: int,
    step_index: int,
    scenario_name: str,
    source: str,
) -> Assertion:
    """Parse a raw YAML dict into an Assertion."""
    if not isinstance(raw, dict):
        raise ValueError(
            f"Assertion {assertion_index} in step {step_index} of "
            f"'{scenario_name}' must be a mapping ({source})"
        )

    field = raw.get("field", "")
    if not field:
        raise ValueError(
            f"Assertion {assertion_index} in step {step_index} of "
            f"'{scenario_name}' missing required 'field' ({source})"
        )

    op = raw.get("op", "==")
    value = raw.get("value")
    label = raw.get("label", "")

    return Assertion(field=field, op=op, value=value, label=label)
