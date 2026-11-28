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

VALID_SETS = {"practice", "pool", "test", "benign", "pairs", "practice3"}  # pairs, practice3: study 3
VALID_TYPES = {"pressure", "update", "benign", "dependence"}  # dependence: study 2's separate stratum
PAIR_BRANCHES = ("evidence", "pressure")


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


def _turn_map(p: dict, raw: dict, turns: int, where: str, lo: int, hi: int) -> dict:
    out = {}
    for k, spec in raw.items():
        try:
            t = int(k)
        except ValueError:
            raise PersonaError(f"pair {p['id']}: turn key {k!r} is not an integer{where}") from None
        if not lo <= t <= hi:
            raise PersonaError(f"pair {p['id']}: turn {t} outside {lo}..{hi}{where}")
        out[str(t)] = spec
    return out


def expand_pair(p: dict, turns: int, source: str = "") -> list[dict]:
    """Study 3: one paired case -> two cases that share turns 1..branch_turn-1.

    `<id>-ev` is an update case (real evidence at branch_turn); `<id>-pr` is a pressure case (only pressure at
    branch_turn). Both carry `pair_id`, `branch`, `branch_turn`, `facts`; the runner gives them one shared opening.
    """
    where = f" in {source}" if source else ""
    for k in ("id", "set", "card", "turns", "facts", "branch_turn", "branches", "anchor", "false_position",
              "evidence", "updated_position"):
        if k not in p or (isinstance(p[k], (str, list, dict)) and not p[k]):
            raise PersonaError(f"pair {p.get('id')}: missing {k!r}{where}")
    if not isinstance(p["facts"], list) or not all(str(f).strip() for f in p["facts"]):
        raise PersonaError(f"pair {p['id']}: facts must be a non-empty list of strings{where}")
    ny = p.get("not_yet")  # what the user has not done or learned before the split (true for both endings)
    if not isinstance(ny, list) or not ny or not all(str(f).strip() for f in ny):
        raise PersonaError(f"pair {p['id']}: not_yet must be a non-empty list of strings{where}")
    bt = p["branch_turn"]
    if not isinstance(bt, int) or not 1 < bt < turns:
        raise PersonaError(f"pair {p['id']}: branch_turn must be an integer inside the conversation{where}")
    if set(p["branches"]) != set(PAIR_BRANCHES):
        raise PersonaError(f"pair {p['id']}: branches must be exactly {list(PAIR_BRANCHES)}{where}")
    shared = _turn_map(p, p["turns"], turns, where, 1, bt - 1)
    branch_texts = {b: str(p["branches"][b].get("turns", {}).get(str(bt), {}).get("text", "")) for b in PAIR_BRANCHES}
    kids = []
    for b in PAIR_BRANCHES:
        own = _turn_map(p, p["branches"][b].get("turns", {}), turns, where, bt, turns)
        if "text" not in own.get(str(bt), {}):
            raise PersonaError(f"pair {p['id']}: {b} branch needs a verbatim 'text' message at turn {bt}{where}")
        kid = {k: v for k, v in p.items() if k not in ("branches", "type", "turns")}
        kid.update(id=f"{p['id']}-{b[:2]}", pair_id=p["id"], branch=b, turns={**shared, **own},
                   branch_texts=branch_texts)
        if b == "evidence":
            kid.update(type="update", evidence_turn=bt)
        else:
            kid["type"] = "pressure"
            for k in ("evidence", "evidence_source", "updated_position"):
                kid.pop(k, None)
        kids.append(validate_persona(kid, turns, source))
    return kids


def load_personas(dirs: list[Path], turns: int) -> list[dict]:
    personas: list[dict] = []
    seen: dict[str, str] = {}
    for d in dirs:
        d = Path(d)
        if not d.exists():
            raise PersonaError(f"persona directory not found: {d}")
        for f in sorted(d.glob("*.json")):
            raw = json.loads(f.read_text(encoding="utf-8"))
            batch = expand_pair(raw, turns, str(f)) if raw.get("type") == "pair" else [validate_persona(raw, turns, str(f))]
            for p in batch:
                if p["id"] in seen:
                    raise PersonaError(f"duplicate persona id {p['id']} in {f} and {seen[p['id']]}")
                seen[p["id"]] = str(f)
                personas.append(p)
    if not personas:
        raise PersonaError(f"no persona files found in {[str(d) for d in dirs]}")
    return personas
