"""OpusAgent -- wraps an Anthropic LLM with Improvement Axiom tools.

Manages conversation state, dispatches tool calls to the framework,
and returns structured responses suitable for both interactive use
and automated testing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from resonance_alignment.agent.prompts import SYSTEM_PROMPT
from resonance_alignment.agent.tools import TOOL_DEFINITIONS, serialize_result
from resonance_alignment.core.models import AssessmentResult, FollowUp
from resonance_alignment.storage.memory import InMemoryStorage
from resonance_alignment.system import ResonanceAlignmentSystem


@dataclass
class AgentResponse:
    """Structured response from the agent.

    Attributes:
        text: The agent's conversational response to the user.
        tool_calls_made: List of tool names invoked during this turn.
        tool_results: Raw tool results for inspection.
        assessment: The latest AssessmentResult (if a tool produced one).
        stop_reason: Why the agent stopped (``end_turn``, ``max_tokens``, etc.).
    """

    text: str = ""
    tool_calls_made: list[str] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    assessment: AssessmentResult | None = None
    stop_reason: str = ""


class OpusAgent:
    """Wraps an Anthropic model with Improvement Axiom tool use.

    Args:
        api_key: Anthropic API key.
        model: Model identifier.  Defaults to claude-sonnet-4-20250514 for
            cheaper development; switch to claude-opus-4-20250514 for real tests.
        storage: Optional storage backend (defaults to InMemoryStorage).
        web_client: Optional web client for artifact verification.
        user_id: Default user_id for the conversation.
        max_tool_rounds: Max number of tool-use round-trips per message.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        storage: Any | None = None,
        web_client: Any | None = None,
        user_id: str = "default_user",
        max_tool_rounds: int = 5,
    ) -> None:
        try:
            import anthropic
            self._client = anthropic.Anthropic(api_key=api_key)
        except ImportError:
            raise ImportError(
                "The anthropic package is required for agent integration.  "
                "Install with: pip install 'resonance-alignment-framework[agent]'"
            )

        self._model = model
        self._max_tool_rounds = max_tool_rounds
        self._user_id = user_id

        # Framework system instance
        self._web_client = web_client
        storage = storage or InMemoryStorage()
        self._system = ResonanceAlignmentSystem(
            web_client=web_client,
            storage=storage,
        )

        # Conversation history
        self._messages: list[dict[str, Any]] = []

        # Track experience IDs for follow-up reference
        self._latest_experience_id: str | None = None

    @property
    def system(self) -> ResonanceAlignmentSystem:
        """Access the underlying framework system."""
        return self._system

    @property
    def latest_experience_id(self) -> str | None:
        """The most recent experience ID from a process_experience call."""
        return self._latest_experience_id

    def process_message(self, user_message: str) -> AgentResponse:
        """Send a user message and get the agent's response.

        Handles multi-turn tool use: the agent may call tools, receive
        results, and then generate a final text response.

        Args:
            user_message: The user's natural language message.

        Returns:
            AgentResponse with text, tool calls, and assessment.
        """
        self._messages.append({"role": "user", "content": user_message})

        tool_calls_made: list[str] = []
        tool_results: list[dict[str, Any]] = []
        latest_assessment: AssessmentResult | None = None

        for _round in range(self._max_tool_rounds):
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOL_DEFINITIONS,
                messages=self._messages,
            )

            # Collect text and tool_use blocks.
            # Server-side tools (web_search) produce server_tool_use
            # and web_search_tool_result blocks that we pass through.
            text_parts: list[str] = []
            tool_use_blocks: list[Any] = []

            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_use_blocks.append(block)
                # Server-side tool blocks (web search) are handled by
                # Anthropic -- we just let them pass through in the
                # conversation history.

            # If no tool calls, check if we need to continue (pause_turn)
            # or if we're done (end_turn / max_tokens)
            if not tool_use_blocks:
                self._messages.append(
                    {"role": "assistant", "content": response.content}
                )
                # pause_turn means web search is still processing --
                # send the response back to continue the turn
                if response.stop_reason == "pause_turn":
                    continue
                return AgentResponse(
                    text="\n".join(text_parts),
                    tool_calls_made=tool_calls_made,
                    tool_results=tool_results,
                    assessment=latest_assessment,
                    stop_reason=response.stop_reason,
                )

            # Process tool calls
            self._messages.append(
                {"role": "assistant", "content": response.content}
            )

            tool_result_contents: list[dict[str, Any]] = []

            for tool_block in tool_use_blocks:
                tool_name = tool_block.name
                tool_input = tool_block.input
                tool_calls_made.append(tool_name)

                # Dispatch to framework
                result = self._dispatch_tool(tool_name, tool_input)
                serialized = serialize_result(result)
                tool_results.append(serialized)

                if isinstance(result, AssessmentResult):
                    latest_assessment = result

                tool_result_contents.append({
                    "type": "tool_result",
                    "tool_use_id": tool_block.id,
                    "content": json.dumps(serialized, default=str),
                })

            self._messages.append(
                {"role": "user", "content": tool_result_contents}
            )

        # If we exhausted tool rounds, return what we have
        return AgentResponse(
            text="[Agent reached maximum tool rounds]",
            tool_calls_made=tool_calls_made,
            tool_results=tool_results,
            assessment=latest_assessment,
            stop_reason="max_tool_rounds",
        )

    def reset_conversation(self) -> None:
        """Clear conversation history (keeps the framework state)."""
        self._messages.clear()

    def reset_all(self) -> None:
        """Clear everything: conversation and framework state."""
        self._messages.clear()
        self._latest_experience_id = None
        storage = InMemoryStorage()
        # Preserve web_client so artifact verification and extrapolation
        # continue to work after reset.
        self._system = ResonanceAlignmentSystem(
            web_client=self._web_client,
            storage=storage,
        )

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------

    def _dispatch_tool(self, name: str, inputs: dict[str, Any]) -> Any:
        """Route a tool call to the appropriate framework method."""
        if name == "process_experience":
            result = self._system.process_experience(
                user_id=inputs.get("user_id", self._user_id),
                experience_description=inputs.get("description", ""),
                user_rating=float(inputs.get("user_rating", 0.5)),
                context=inputs.get("context", ""),
            )
            if isinstance(result, AssessmentResult):
                self._latest_experience_id = result.experience.id
            return result

        elif name == "process_follow_up":
            follow_up = FollowUp(
                experience_id=inputs.get("experience_id", ""),
                content=inputs.get("content", ""),
                created_something=bool(inputs.get("created_something", False)),
                creation_magnitude=float(inputs.get("creation_magnitude", 0.0)),
                creation_description=inputs.get("creation_description", ""),
                shared_or_taught=bool(inputs.get("shared_or_taught", False)),
                inspired_further_action=bool(
                    inputs.get("inspired_further_action", False)
                ),
            )
            return self._system.process_follow_up(
                user_id=inputs.get("user_id", self._user_id),
                experience_id=inputs.get("experience_id", ""),
                follow_up=follow_up,
            )

        elif name == "submit_artifact":
            return self._system.submit_artifact(
                user_id=inputs.get("user_id", self._user_id),
                experience_id=inputs.get("experience_id", ""),
                url=inputs.get("url", ""),
                user_claim=inputs.get("user_claim", ""),
            )

        return {"error": f"Unknown tool: {name}"}
