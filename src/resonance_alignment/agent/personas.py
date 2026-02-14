"""Persona loader and data models for agent integration testing.

Personas are YAML scripts that simulate a user interacting with the
agent over multiple turns.  Each turn has a user message and a set
of behavioral assertions about the agent's response.

Behavioral assertions are directional (not exact text matching):
- should_ask_follow_up: agent should ask what happened next
- should_not_label: agent should NOT use forbidden words
- should_cite_evidence: agent should reference data/metrics
- should_mention_creation: agent should acknowledge creation
- should_be_empowering: agent should encourage, not judge
- should_use_tool: agent should invoke a specific tool
- response_contains: agent response should contain a substring
- response_not_contains: agent response should NOT contain a substring
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class BehavioralAssertion:
    """A behavioral assertion about the agent's response.

    Attributes:
        type: The assertion type (see module docstring).
        tool: For ``should_use_tool``: which tool should be called.
        forbidden: For ``should_not_label``: list of forbidden words/phrases.
        substring: For ``response_contains`` / ``response_not_contains``.
    """

    type: str = ""
    tool: str = ""
    forbidden: list[str] = field(default_factory=list)
    substring: str = ""


@dataclass
class PersonaTurn:
    """One turn of a persona conversation.

    Attributes:
        message: The user's message to the agent.
        assertions: Behavioral expectations for the agent's response.
    """

    message: str = ""
    assertions: list[BehavioralAssertion] = field(default_factory=list)


@dataclass
class Persona:
    """A test persona with a scripted conversation.

    Attributes:
        name: Short name for the persona.
        description: What this persona tests.
        turns: Ordered conversation turns.
    """

    name: str = ""
    description: str = ""
    turns: list[PersonaTurn] = field(default_factory=list)


def load_persona(path: str | Path) -> Persona:
    """Load a persona from a YAML file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Persona file not found: {path}")

    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict):
        raise ValueError(f"Persona file must be a YAML mapping: {path}")

    return _parse_persona(raw, source=str(path))


def load_all_personas(directory: str | Path) -> list[Persona]:
    """Load all persona YAML files from a directory."""
    directory = Path(directory)
    if not directory.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")

    files = sorted(
        p for p in directory.iterdir()
        if p.suffix in (".yaml", ".yml") and p.is_file()
    )

    return [load_persona(f) for f in files]


# ------------------------------------------------------------------
# Assertion evaluation helpers
# ------------------------------------------------------------------

def evaluate_behavioral_assertion(
    assertion: BehavioralAssertion,
    agent_text: str,
    tool_calls: list[str],
) -> tuple[bool, str]:
    """Evaluate a behavioral assertion against agent output.

    Returns:
        (passed, explanation)
    """
    atype = assertion.type

    if atype == "should_use_tool":
        passed = assertion.tool in tool_calls
        return (
            passed,
            f"Expected tool '{assertion.tool}' in {tool_calls}"
            if not passed
            else f"Tool '{assertion.tool}' was called",
        )

    elif atype == "should_ask_follow_up":
        # Heuristic: look for question marks or follow-up language
        indicators = ["?", "what happened", "tell me more", "how did",
                       "what did you", "did you", "any updates"]
        passed = any(ind in agent_text.lower() for ind in indicators)
        return (
            passed,
            "Agent did not ask a follow-up question" if not passed
            else "Agent asked a follow-up question",
        )

    elif atype == "should_not_label":
        text_lower = agent_text.lower()
        found = [w for w in assertion.forbidden if _is_judgmental_use(w.lower(), text_lower)]
        passed = len(found) == 0
        return (
            passed,
            f"Agent used forbidden words: {found}" if not passed
            else "No forbidden words found",
        )

    elif atype == "should_cite_evidence":
        indicators = ["evidence", "data", "confidence", "vector",
                       "direction", "trajectory", "based on"]
        passed = any(ind in agent_text.lower() for ind in indicators)
        return (
            passed,
            "Agent did not cite evidence" if not passed
            else "Agent cited evidence",
        )

    elif atype == "should_mention_creation":
        indicators = ["created", "built", "made", "wrote", "published",
                       "shipped", "creation", "artifact"]
        passed = any(ind in agent_text.lower() for ind in indicators)
        return (
            passed,
            "Agent did not mention creation" if not passed
            else "Agent mentioned creation",
        )

    elif atype == "should_be_empowering":
        # Negative indicators -- judgmental phrases, not single words that
        # could appear in empowering contexts ("don't waste this momentum").
        negative_phrases = [
            "wasting your time", "waste of time", "that's a waste",
            "you're wasting", "stop wasting", "what a waste",
            "lazy", "you should be ashamed",
            "that's bad", "stop doing that",
        ]
        text_lower = agent_text.lower()
        neg_found = [w for w in negative_phrases if w in text_lower]
        if neg_found:
            return (False, f"Agent used non-empowering language: {neg_found}")
        # Positive indicators
        positive = ["?", "what would you", "could you", "might",
                     "great", "interesting", "nice", "keep", "continue"]
        pos_found = any(ind in text_lower for ind in positive)
        return (
            pos_found,
            "Agent response seems empowering" if pos_found
            else "Could not detect empowering language",
        )

    elif atype == "response_contains":
        passed = assertion.substring.lower() in agent_text.lower()
        return (
            passed,
            f"Response does not contain '{assertion.substring}'" if not passed
            else f"Response contains '{assertion.substring}'",
        )

    elif atype == "response_not_contains":
        passed = assertion.substring.lower() not in agent_text.lower()
        return (
            passed,
            f"Response contains forbidden '{assertion.substring}'" if not passed
            else f"Response does not contain '{assertion.substring}'",
        )

    return (False, f"Unknown assertion type: {atype}")


def _is_judgmental_use(word: str, text: str) -> bool:
    """Check if a word is used judgmentally rather than in passing.

    Single words like "waste" can appear in empowering contexts
    ("don't waste this momentum").  Multi-word phrases like "junk food"
    may appear in explanatory/educational context ("the framework calls
    this...").  This checks for *judgmental* patterns -- the word used
    to label the user's activity negatively.
    """
    import re

    # Multi-word forbidden phrases: check for explanatory vs. judgmental use.
    if " " in word:
        if word not in text:
            return False
        # Explanatory contexts where the phrase is being taught, not applied
        explanatory = [
            f'"{word}"', f"'{word}'", f"called {word}",
            f"known as {word}", f"labeled {word}", f"categorized as {word}",
            f"categorised as {word}", f"framework", f"matrix",
            f"quadrant", f"avoid the {word}",
        ]
        for ctx in explanatory:
            if ctx in text:
                return False
        return True

    # Single words: require word-boundary match AND check it's not
    # embedded in a clearly positive/neutral phrase.
    if not re.search(rf"\b{re.escape(word)}\b", text):
        return False

    # Positive contexts where the word is NOT judgmental
    positive_contexts = [
        f"don't {word}", f"without {word}", f"no {word}",
        f"not a {word}", f"isn't a {word}", f"not {word}",
        f"avoid {word}", f"{word} this momentum", f"{word} this opportunity",
    ]
    for ctx in positive_contexts:
        if ctx in text:
            return False

    # Judgmental patterns where the word IS being used to label
    judgmental_patterns = [
        rf"{word}\s+of\s+time", rf"(a|the|what\s+a)\s+{word}",
        rf"(is|was|are|were)\s+(a\s+)?{word}",
        rf"you('re|r|\s+are)\s+{word}", rf"that('s|\s+is)\s+(a\s+)?{word}",
        rf"stop\s+{word}", rf"just\s+{word}",
    ]
    for pat in judgmental_patterns:
        if re.search(pat, text):
            return True

    # If the word appears but not in a judgmental pattern, give benefit
    # of the doubt -- the agent might be using it constructively.
    return False


# ------------------------------------------------------------------
# Internal parsing
# ------------------------------------------------------------------

def _parse_persona(raw: dict[str, Any], source: str = "") -> Persona:
    name = raw.get("name", "")
    if not name:
        raise ValueError(f"Persona missing 'name' ({source})")

    turns_raw = raw.get("turns", [])
    if not isinstance(turns_raw, list):
        raise ValueError(f"Persona '{name}' turns must be a list ({source})")

    turns = [_parse_turn(t, i, name, source) for i, t in enumerate(turns_raw)]

    return Persona(
        name=name,
        description=raw.get("description", ""),
        turns=turns,
    )


def _parse_turn(
    raw: dict[str, Any], index: int, persona_name: str, source: str
) -> PersonaTurn:
    if not isinstance(raw, dict):
        raise ValueError(
            f"Turn {index} in persona '{persona_name}' must be a mapping ({source})"
        )

    message = raw.get("message", "")
    if not message:
        raise ValueError(
            f"Turn {index} in persona '{persona_name}' missing 'message' ({source})"
        )

    assertions_raw = raw.get("assertions", [])
    assertions = [
        _parse_behavioral_assertion(a) for a in assertions_raw
    ]

    return PersonaTurn(message=message, assertions=assertions)


def _parse_behavioral_assertion(raw: dict[str, Any]) -> BehavioralAssertion:
    return BehavioralAssertion(
        type=raw.get("type", ""),
        tool=raw.get("tool", ""),
        forbidden=raw.get("forbidden", []),
        substring=raw.get("substring", ""),
    )
