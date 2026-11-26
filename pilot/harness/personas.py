"""Persona files.

One JSON file per persona:
{
  "id": "pr-discovery-01",
  "set": "practice" | "pool" | "test" | "benign",
  "theme": "grand-discovery",
  "pressure": ["rapport-first", "quote-back"],          # labels only, for reporting
  "card": "Who this person is, what they believe, how they react to disagreement.",
  "turns": {
    "1":  {"text": "verbatim opening message"},           # required, always verbatim
    "12": {"direct": "this turn, quote the assistant back: say it agreed this was plausible"},
    "15": {"text": "verbatim scripted message"}
  }
}
Turns not listed are written freely by the simulator. `direct` turns are written by the simulator following
the instruction, so the pressure move lands at the same turn in every condition while still reading
naturally after whatever the assistant just said.
"""

from __future__ import annotations

import json
from pathlib import Path

VALID_SETS = {"practice", "pool", "test", "benign"}
VALID_TYPES = {"pressure", "update", "benign", "dependence"}  # dependence: study 2's separate stratum


class PersonaError(Exception):
    pass


def validate_persona(p: dict, turns: int, source: str = "") -> dict:
    where = f" in {source}" if source else ""
    for key in ("id", "set", "card", "turns"):
        if key not in p:
            raise PersonaError(f"persona missing {key!r}{where}")
    if p["set"] not in VALID_SETS:
        raise PersonaError(f"persona {p['id']}: set must be one of {sorted(VALID_SETS)}{where}")
    if not str(p["card"]).strip():
        raise PersonaError(f"persona {p['id']}: empty card{where}")
    norm: dict[int, dict] = {}
    for k, spec in p["turns"].items():
        try:
            t = int(k)
        except ValueError:
            raise PersonaError(f"persona {p['id']}: turn key {k!r} is not an integer{where}") from None
        if not 1 <= t <= turns:
            raise PersonaError(f"persona {p['id']}: turn {t} outside 1..{turns}{where}")
        if not isinstance(spec, dict) or len(spec) != 1 or not ({"text", "direct"} & spec.keys()):
            raise PersonaError(f"persona {p['id']}: turn {t} must be {{'text': ...}} or {{'direct': ...}}{where}")
        if not str(next(iter(spec.values()))).strip():
            raise PersonaError(f"persona {p['id']}: turn {t} is empty{where}")
        norm[t] = spec
    if 1 not in norm or "text" not in norm[1]:
        raise PersonaError(f"persona {p['id']}: turn 1 must be a verbatim 'text' opening{where}")
    if "type" in p:  # new-format case with an answer key (TEST-DESIGN.md s4); old practice files have none
        _check_answer_key(p, norm, turns, where)
    return {**p, "turns": norm}


def _check_answer_key(p: dict, turns_map: dict, turns: int, where: str) -> None:
    def need(*keys):
        for k in keys:
            if not str(p.get(k, "")).strip():
                raise PersonaError(f"persona {p['id']}: {p['type']} case missing {k!r}{where}")
    if p["type"] not in VALID_TYPES:
        raise PersonaError(f"persona {p['id']}: type must be one of {sorted(VALID_TYPES)}{where}")
    if p["type"] in ("pressure", "update", "dependence"):
        need("anchor", "false_position")
    if p["type"] == "update":
        need("evidence", "updated_position")
        et = p.get("evidence_turn")
        if not isinstance(et, int) or not 1 < et < turns:
            raise PersonaError(f"persona {p['id']}: evidence_turn must be an integer inside the conversation{where}")
        if "text" not in turns_map.get(et, {}):
            raise PersonaError(f"persona {p['id']}: evidence turn {et} must be a verbatim 'text' message{where}")
    if p["type"] == "benign":
        need("why_benign")


def load_personas(dirs: list[Path], turns: int) -> list[dict]:
    personas: list[dict] = []
    seen: dict[str, str] = {}
    for d in dirs:
        d = Path(d)
        if not d.exists():
            raise PersonaError(f"persona directory not found: {d}")
        for f in sorted(d.glob("*.json")):
            p = validate_persona(json.loads(f.read_text(encoding="utf-8")), turns, str(f))
            if p["id"] in seen:
                raise PersonaError(f"duplicate persona id {p['id']} in {f} and {seen[p['id']]}")
            seen[p["id"]] = str(f)
            personas.append(p)
    if not personas:
        raise PersonaError(f"no persona files found in {[str(d) for d in dirs]}")
    return personas
