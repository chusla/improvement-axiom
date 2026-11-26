"""Config loading, validation, and the rigor guards.

Guards enforced in code, not just in the docs:
- the screening stage may only use the `none` condition;
- outside the `test` stage, prompted conditions may only run on practice personas
  (pool, test and benign personas are never seen by a prompted condition before registration);
- the `test` stage refuses to run unless every condition file matches its frozen SHA-256 and the
  registration commit exists and holds a completed PREREGISTRATION.md.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .personas import load_personas
from .store import read_json, sha256_file

PLACEHOLDER = "FILL_ME"
PRACTICE_SET = "practice"


class ConfigError(Exception):
    pass


@dataclass
class Config:
    data: dict
    path: Path

    @property
    def base(self) -> Path:
        return self.path.parent

    def resolve(self, rel: str) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else (self.base / p).resolve()

    @property
    def turns(self) -> int:
        return int(self.data["conversation"]["turns"])

    @property
    def max_retries(self) -> int:
        return int(self.data.get("max_retries", 6))

    @property
    def concurrency(self) -> int:
        return int(self.data.get("concurrency", 4))

    def stage(self, name: str) -> dict:
        stages = self.data.get("stages", {})
        if name not in stages:
            raise ConfigError(f"unknown stage {name!r}; known: {', '.join(stages)}")
        return stages[name]

    @property
    def conditions(self) -> dict[str, str | None]:
        """Condition name -> prompt file (None = no system prompt). `$`-prefixed keys are comments."""
        return {k: v for k, v in self.data["conditions"].items() if not k.startswith("$")}

    def condition_text(self, condition: str) -> str | None:
        rel = self.conditions.get(condition)
        if condition not in self.conditions:
            raise ConfigError(f"unknown condition {condition!r}")
        if rel is None:
            return None
        return self.resolve(rel).read_text(encoding="utf-8").strip()

    def condition_path(self, condition: str) -> Path | None:
        rel = self.conditions.get(condition)
        return self.resolve(rel) if rel else None


def load_config(path: str | Path) -> Config:
    path = Path(path).resolve()
    if not path.exists():
        raise ConfigError(f"config not found: {path}")
    data = read_json(path)
    for key in ("conversation", "conditions", "models", "simulator", "judges", "stages", "spiral_bench"):
        if key not in data:
            raise ConfigError(f"config is missing {key!r}")
    return Config(data=data, path=path)


def find_placeholders(obj: Any, trail: str = "") -> list[str]:
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not str(k).startswith("$"):
                hits += find_placeholders(v, f"{trail}.{k}" if trail else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits += find_placeholders(v, f"{trail}[{i}]")
    elif isinstance(obj, str) and PLACEHOLDER in obj:
        hits.append(trail)
    return hits


def word_count(text: str) -> int:
    return len(text.split())


def check_stage_guards(cfg: Config, stage_name: str, mock: bool) -> list[str]:
    """Return a list of blocking problems for running this stage. Empty means OK."""
    stage = cfg.stage(stage_name)
    problems: list[str] = []
    conditions = stage["conditions"]
    unknown = [c for c in conditions if c not in cfg.conditions]
    if unknown:
        problems.append(f"stage {stage_name!r} names unknown conditions {unknown}")
    prompted = [c for c in conditions if cfg.conditions.get(c) is not None]

    is_test = stage_name == "test" or stage_name.startswith("test-")
    if stage_name == "screening" and conditions != ["none"]:
        problems.append("screening may only use the 'none' condition")
    if stage_name == "screening" and not mock:
        sc = cfg.data.get("screening", {})
        if sc.get("cap") is None or sc.get("min_kept") is None:
            problems.append("set config.screening.cap and min_kept before screening (the rule is fixed in advance)")
        problems += check_registration(cfg)  # the screening rule is part of the registration (TEST-DESIGN s9a)

    personas = load_personas([cfg.resolve(d) for d in stage["persona_dirs"]], cfg.turns)
    non_practice = sorted({p["set"] for p in personas if p["set"] != PRACTICE_SET})
    if not is_test and prompted and non_practice:
        problems.append(
            f"stage {stage_name!r} runs prompted conditions {prompted} on non-practice persona sets "
            f"{non_practice}; only a registered test stage may do that"
        )

    if (stage.get("simulator_base") or stage.get("simulator_every_turn")) and non_practice and not is_test:
        problems.append(f"stage {stage_name!r} swaps the simulator instructions on non-practice persona sets "
                        f"{non_practice}; simulator tuning is practice-only")

    if is_test and not mock:
        problems += check_freeze(cfg, conditions)
    return problems


def check_registration(cfg: Config) -> list[str]:
    commit = cfg.data.get("freeze", {}).get("registration_commit", "")
    if not commit or PLACEHOLDER in commit:
        return ["config.freeze.registration_commit is not set"]
    prereg = _git_show(cfg.base, commit, "pilot/PREREGISTRATION.md")
    if prereg is None:
        return [f"registration commit {commit} not found, or it has no pilot/PREREGISTRATION.md"]
    if "Not registered" in prereg or "DRAFT SKELETON" in prereg:
        return [f"PREREGISTRATION.md at {commit} is still the draft skeleton"]
    return []


def check_freeze(cfg: Config, conditions: list[str]) -> list[str]:
    problems: list[str] = []
    freeze = cfg.data.get("freeze", {})
    hashes = freeze.get("prompt_sha256", {})
    for c in conditions:
        p = cfg.condition_path(c)
        if p is None:
            continue
        want = hashes.get(c, "")
        if not want or PLACEHOLDER in want:
            problems.append(f"condition {c!r} has no frozen SHA-256 in config.freeze.prompt_sha256")
        elif sha256_file(p) != want:
            problems.append(f"condition {c!r}: {p.name} does not match its frozen SHA-256")
    return problems + check_registration(cfg)


def _git_show(cwd: Path, commit: str, path: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "show", f"{commit}:{path}"], cwd=cwd, capture_output=True, text=True, encoding="utf-8"
        )
    except OSError:
        return None
    return out.stdout if out.returncode == 0 else None


def git_head(cwd: Path) -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True)
    except OSError:
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def git_dirty(cwd: Path) -> bool | None:
    try:
        out = subprocess.run(["git", "status", "--porcelain"], cwd=cwd, capture_output=True, text=True)
    except OSError:
        return None
    return bool(out.stdout.strip()) if out.returncode == 0 else None


def model_specs_for_stage(cfg: Config, stage_name: str) -> dict[str, dict]:
    stage = cfg.stage(stage_name)
    missing = [m for m in stage["models"] if m not in cfg.data["models"]]
    if missing:
        raise ConfigError(f"stage {stage_name!r} names unknown models {missing}")
    return {m: cfg.data["models"][m] for m in stage["models"]}


def dump(obj: Any) -> str:
    return json.dumps(obj, indent=1, ensure_ascii=False)
