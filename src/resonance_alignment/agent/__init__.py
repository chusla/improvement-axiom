"""Agent integration harness for LLM-driven testing.

Provides the OpusAgent wrapper that connects an Anthropic LLM
(e.g. Opus 4.6, Sonnet) to the Improvement Axiom framework via
tool use, and persona-driven test infrastructure.

Usage:
    from resonance_alignment.agent import OpusAgent

    agent = OpusAgent(api_key="sk-...")
    response = agent.process_message("I played Minecraft all weekend")
    print(response.text)
"""

from resonance_alignment.agent.tools import TOOL_DEFINITIONS, serialize_result
from resonance_alignment.agent.prompts import SYSTEM_PROMPT
from resonance_alignment.agent.wrapper import OpusAgent, AgentResponse
from resonance_alignment.agent.personas import (
    BehavioralAssertion,
    PersonaTurn,
    Persona,
    load_persona,
    load_all_personas,
)

__all__ = [
    "TOOL_DEFINITIONS",
    "serialize_result",
    "SYSTEM_PROMPT",
    "OpusAgent",
    "AgentResponse",
    "BehavioralAssertion",
    "PersonaTurn",
    "Persona",
    "load_persona",
    "load_all_personas",
]
