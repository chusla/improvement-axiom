"""Gradio chat interface for the Improvement Axiom framework.

Provides a conversational UI where users interact with an AI mentor
powered by the Improvement Axiom.  The mentor uses the OpusAgent
wrapper which calls the framework's three entry points via tool use.

A sidebar shows live framework metrics: vector direction, confidence,
quality score, and trajectory history -- so users can see the
"machinery" behind the conversation.

Deployable to HuggingFace Spaces (app.py launches this) or run locally.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

try:
    import gradio as gr
except ImportError:
    gr = None

from resonance_alignment.system import ResonanceAlignmentSystem
from resonance_alignment.core.models import AssessmentResult
from resonance_alignment.config import get_storage


# ------------------------------------------------------------------
# Direct framework chat (no Anthropic dependency required)
# ------------------------------------------------------------------

def _build_framework_response(
    system: ResonanceAlignmentSystem,
    user_id: str,
    message: str,
    state: dict[str, Any],
) -> tuple[str, dict[str, Any] | None]:
    """Process a user message through the framework and build a response.

    This is a lightweight alternative to the full OpusAgent that
    doesn't require an Anthropic API key.  It parses the message
    for intent and calls the appropriate framework method directly.

    Returns:
        (response_text, latest_assessment_dict_or_None)
    """
    msg_lower = message.lower().strip()

    # Check if this looks like a follow-up to a previous experience
    exp_id = state.get("latest_experience_id")
    has_experience = exp_id is not None

    # Heuristic: if user mentions creating/building/making something,
    # or shares a URL, or says what happened next -- treat as follow-up
    creation_keywords = [
        "built", "made", "created", "wrote", "published", "shipped",
        "started", "designed", "coded", "painted", "drew", "composed",
        "recorded", "filmed", "taught", "shared", "posted", "uploaded",
    ]
    follow_up_keywords = [
        "then", "after that", "since then", "next", "later",
        "happened", "update", "follow up", "followed up",
        "still", "again", "same thing", "more of the same",
    ]
    sharing_keywords = [
        "shared", "taught", "showed", "posted", "published",
        "uploaded", "sent", "told them about",
    ]
    url_in_message = "http://" in msg_lower or "https://" in msg_lower

    created_something = any(k in msg_lower for k in creation_keywords)
    is_follow_up = has_experience and (
        any(k in msg_lower for k in follow_up_keywords)
        or created_something
        or "nah" in msg_lower or "no " in msg_lower[:10]
        or "same" in msg_lower or "still just" in msg_lower
    )
    shared_or_taught = any(k in msg_lower for k in sharing_keywords)

    # Route: artifact submission
    if url_in_message and has_experience:
        import re
        urls = re.findall(r'https?://\S+', message)
        if urls:
            verification = system.submit_artifact(
                user_id=user_id,
                experience_id=exp_id,
                url=urls[0],
                user_claim=message,
            )
            status = getattr(verification, "status", "unknown")
            if status == "verified":
                text = (
                    f"I checked that link and it looks substantive -- "
                    f"verified! This is real evidence of creation, and "
                    f"it strengthens your trajectory. What inspired you "
                    f"to create this?"
                )
            elif status == "inaccessible":
                text = (
                    f"I wasn't able to access that URL right now.  "
                    f"Could you double-check the link?  No worries if "
                    f"it's behind a login -- the important thing is that "
                    f"you created something."
                )
            else:
                text = (
                    f"I could access the link but couldn't fully verify it "
                    f"yet (status: {status}).  That's okay -- the evidence "
                    f"picture builds over time.  Tell me more about what "
                    f"you made."
                )
            return text, None

    # Route: follow-up
    if is_follow_up and has_experience:
        from resonance_alignment.core.models import FollowUp
        magnitude = 0.0
        if created_something:
            # Rough magnitude heuristic
            if any(w in msg_lower for w in ["published", "shipped", "uploaded", "posted"]):
                magnitude = 1.0
            elif any(w in msg_lower for w in ["built", "made", "finished", "completed"]):
                magnitude = 0.75
            elif any(w in msg_lower for w in ["started", "began", "trying", "tried"]):
                magnitude = 0.4
            else:
                magnitude = 0.5

        follow_up = FollowUp(
            experience_id=exp_id,
            content=message,
            created_something=created_something,
            creation_magnitude=magnitude,
            creation_description=message if created_something else "",
            shared_or_taught=shared_or_taught,
            inspired_further_action=created_something or shared_or_taught,
            timestamp=datetime.now(timezone.utc),
        )
        result = system.process_follow_up(
            user_id=user_id,
            experience_id=exp_id,
            follow_up=follow_up,
        )
        if isinstance(result, AssessmentResult):
            state["latest_assessment"] = result
            text = _format_assessment_response(result, is_follow_up=True)
            return text, _assessment_to_metrics(result)
        return "Thanks for the update -- I've recorded that.", None

    # Route: new experience (default)
    # Infer user_rating from enthusiasm
    if any(w in msg_lower for w in ["awesome", "amazing", "loved", "incredible", "fantastic"]):
        rating = 0.9
    elif any(w in msg_lower for w in ["great", "cool", "nice", "fun", "enjoyed", "good"]):
        rating = 0.75
    elif any(w in msg_lower for w in ["ok", "fine", "alright", "meh", "whatever"]):
        rating = 0.4
    elif any(w in msg_lower for w in ["boring", "bad", "terrible", "hated", "awful"]):
        rating = 0.15
    else:
        rating = 0.5

    result = system.process_experience(
        user_id=user_id,
        experience_description=message,
        user_rating=rating,
        context="",
    )

    if isinstance(result, AssessmentResult):
        state["latest_experience_id"] = result.experience.id
        state["latest_assessment"] = result
        text = _format_assessment_response(result, is_follow_up=False)
        return text, _assessment_to_metrics(result)

    return "I've noted that.  Tell me more about what happened.", None


def _format_assessment_response(result: AssessmentResult, is_follow_up: bool) -> str:
    """Format an assessment result into natural conversational text."""
    exp = result.experience
    conf = exp.intention_confidence
    direction = "creative" if exp.provisional_intention.value == "creative" else (
        "input-focused" if exp.provisional_intention.value == "consumptive" else "forming"
    )

    parts: list[str] = []

    if is_follow_up:
        # Acknowledge the follow-up
        if exp.intention_confidence > 0.5:
            if direction == "creative":
                parts.append(
                    "That's great -- this is real evidence of creation! "
                    "Your trajectory is clearly shifting in a creative direction."
                )
            elif direction == "input-focused":
                parts.append(
                    "Thanks for the update.  The evidence so far leans "
                    "toward input-focused activity.  That's not a judgment -- "
                    "the picture is still forming."
                )
            else:
                parts.append(
                    "Noted!  The vector is still forming -- I need more "
                    "data points to see the direction clearly."
                )
        else:
            parts.append(
                "Got it -- I've recorded that.  The picture is still "
                "emerging."
            )
    else:
        # New experience -- be provisional
        parts.append(
            "Thanks for sharing that!  I've recorded it, but the "
            "assessment is still very early."
        )

    # Confidence info
    if conf < 0.3:
        parts.append(
            f"Confidence is low right now ({conf:.0%}).  "
            "This is normal at this stage -- the trajectory needs "
            "time and follow-ups to reveal itself."
        )
    elif conf < 0.6:
        parts.append(
            f"Confidence is moderate ({conf:.0%}).  "
            "The direction is starting to show but more evidence "
            "would strengthen the picture."
        )
    else:
        parts.append(
            f"Confidence is getting solid ({conf:.0%}).  "
            f"The evidence points toward a {direction} trajectory."
        )

    # Quality info
    qs = exp.quality_score
    if qs > 0.6:
        parts.append("Quality signals are strong.")
    elif qs > 0.35:
        parts.append("Quality signals are moderate -- still building.")

    # Empowering close
    if not is_follow_up:
        parts.append(
            "What happened after this?  Did it inspire you to "
            "do anything, create something, or share it with anyone?"
        )
    elif direction != "creative" and conf > 0.3:
        parts.append(
            "What could shift this toward creation?  Even small "
            "creative acts -- sketching, writing, teaching -- move the vector."
        )
    else:
        parts.append("What happened next?")

    return "  ".join(parts)


def _assessment_to_metrics(result: AssessmentResult) -> dict[str, Any]:
    """Extract display metrics from an AssessmentResult."""
    exp = result.experience
    traj = result.trajectory
    vec = traj.current_vector if traj else None

    metrics: dict[str, Any] = {
        "intention": exp.provisional_intention.value,
        "confidence": round(exp.intention_confidence, 3),
        "quality_score": round(exp.quality_score, 3),
        "resonance_score": round(exp.resonance_score, 3),
        "matrix_position": exp.matrix_position or "Pending",
        "is_provisional": result.is_provisional,
        "arc_trend": result.arc_trend or "insufficient_data",
    }

    if vec:
        metrics["vector_direction"] = round(vec.direction, 3)
        metrics["vector_magnitude"] = round(vec.magnitude, 3)
        metrics["vector_confidence"] = round(vec.confidence, 3)

    if traj:
        metrics["experience_count"] = traj.experience_count
        metrics["creation_rate"] = round(traj.creation_rate, 3)
        metrics["compounding_direction"] = round(traj.compounding_direction, 3)

    return metrics


def _format_metrics_display(metrics: dict[str, Any] | None) -> str:
    """Format metrics dict into readable markdown for the sidebar."""
    if not metrics:
        return "*No assessment yet.  Tell the mentor about an experience to begin.*"

    direction_val = metrics.get("vector_direction", 0)
    if direction_val > 0.2:
        direction_emoji = "→ Creative"
        direction_color = "🟢"
    elif direction_val < -0.2:
        direction_emoji = "→ Input-focused"
        direction_color = "🟡"
    else:
        direction_emoji = "→ Neutral / forming"
        direction_color = "⚪"

    conf = metrics.get("confidence", 0)
    conf_bar = "█" * int(conf * 10) + "░" * (10 - int(conf * 10))

    lines = [
        f"### Vector {direction_color}",
        f"**Direction:** {direction_emoji} ({metrics.get('vector_direction', '—')})",
        f"**Confidence:** `{conf_bar}` {conf:.0%}",
        f"**Quality:** {metrics.get('quality_score', '—')}",
        f"**Resonance:** {metrics.get('resonance_score', '—')}",
        "",
        f"### Trajectory",
        f"**Position:** {metrics.get('matrix_position', 'Pending')}",
        f"**Arc trend:** {metrics.get('arc_trend', '—')}",
        f"**Experiences:** {metrics.get('experience_count', 0)}",
        f"**Creation rate:** {metrics.get('creation_rate', 0):.0%}",
        f"**Compounding:** {metrics.get('compounding_direction', 0):+.3f}",
        "",
        f"*{'⚠️ Provisional' if metrics.get('is_provisional') else '✓ Evidence-based'}*",
    ]
    return "\n".join(lines)


# ------------------------------------------------------------------
# Gradio app builder
# ------------------------------------------------------------------

def create_interface():
    """Create and return the Gradio Blocks interface.

    Raises:
        ImportError: If gradio is not installed.
    """
    if gr is None:
        raise ImportError(
            "gradio is required for the UI.  "
            "Install with: pip install gradio>=4.0.0"
        )

    # Check if Anthropic agent is available
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    has_agent = bool(anthropic_key)

    with gr.Blocks(
        title="Improvement Axiom",
    ) as demo:

        # State
        chat_state = gr.State({
            "user_id": f"user_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
            "latest_experience_id": None,
            "latest_assessment": None,
            "system": None,
            "agent": None,
        })
        latest_metrics = gr.State(None)

        # Header
        gr.Markdown(
            """
            # Improvement Axiom
            ### An AI alignment framework grounded in natural law observation

            Talk to the mentor about your experiences, hobbies, and activities.
            The framework tracks your creative/consumptive trajectory over time --
            not through labels, but through **observable evidence** of what
            activities lead to.

            *Try describing something you did recently, then tell the mentor
            what happened next.*
            """
        )

        with gr.Row():
            # Main chat area (wider)
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(
                    label="Conversation",
                    height=520,
                )
                with gr.Row():
                    msg_input = gr.Textbox(
                        label="Your message",
                        placeholder="Describe an experience or what happened next...",
                        scale=5,
                        lines=1,
                    )
                    send_btn = gr.Button("Send", variant="primary", scale=1)

                with gr.Row():
                    clear_btn = gr.Button("New conversation", variant="secondary", size="sm")
                    mode_label = gr.Markdown(
                        f"*Mode: {'🤖 AI Agent (Anthropic)' if has_agent else '📊 Direct Framework'}*",
                    )

            # Sidebar: live metrics
            with gr.Column(scale=1, elem_classes="metrics-panel"):
                gr.Markdown("## Framework Metrics")
                metrics_display = gr.Markdown(
                    "*No assessment yet.  Tell the mentor about an "
                    "experience to begin.*"
                )

                gr.Markdown("---")
                gr.Markdown(
                    """
                    ### How it works

                    1. **Describe** an experience
                    2. **Follow up** with what happened next
                    3. **Watch** the vector evolve

                    The framework never labels at t=0.
                    Confidence rises with evidence.
                    Signal depth > breadth.
                    """,
                    elem_classes="disclaimer",
                )

        # ----------------------------------------------------------
        # Chat handlers
        # ----------------------------------------------------------

        def _ensure_system(state: dict) -> dict:
            """Lazily initialize system, storage, web client, and agent."""
            if state.get("system") is None:
                storage = get_storage()
                state["storage"] = storage

                # Generate a session_id for conversation logging
                import uuid
                state["session_id"] = str(uuid.uuid4())[:12]

                # Create web client for Defence Layers 2 & 5
                # (Artifact Verification + Evidence-Based Extrapolation)
                web_client = None
                try:
                    from resonance_alignment.core.web_client import HttpxWebClient
                    web_client = HttpxWebClient()
                except ImportError:
                    pass  # httpx not installed -- degrade gracefully

                state["system"] = ResonanceAlignmentSystem(
                    storage=storage,
                    web_client=web_client,
                )
                if has_agent:
                    try:
                        from resonance_alignment.agent.wrapper import OpusAgent
                        state["agent"] = OpusAgent(
                            api_key=anthropic_key,
                            storage=storage,
                            web_client=web_client,
                            user_id=state["user_id"],
                        )
                    except ImportError:
                        state["agent"] = None
            return state

        def respond(
            message: str,
            chat_history: list,
            state: dict,
            metrics: dict | None,
        ):
            """Handle a user message."""
            if not message.strip():
                return "", chat_history, state, metrics, _format_metrics_display(metrics)

            state = _ensure_system(state)
            storage = state.get("storage")
            session_id = state.get("session_id", "unknown")
            user_id = state.get("user_id", "unknown")

            # Add user message to chat
            chat_history = chat_history + [{"role": "user", "content": message}]

            # Log user message
            if storage:
                storage.log_conversation(
                    session_id=session_id,
                    user_id=user_id,
                    role="user",
                    content=message,
                    mode="agent" if state.get("agent") else "direct",
                )

            agent = state.get("agent")

            if agent is not None:
                # Full LLM agent path
                try:
                    response = agent.process_message(message)
                    bot_text = response.text or "I've processed that."
                    # Extract metrics from assessment if available
                    if response.assessment:
                        metrics = _assessment_to_metrics(response.assessment)
                        state["latest_experience_id"] = response.assessment.experience.id
                        state["latest_assessment"] = response.assessment
                except Exception as e:
                    import traceback
                    error_detail = traceback.format_exc()
                    print(f"[AGENT ERROR] {e}\n{error_detail}")
                    bot_text = (
                        f"[Agent error, falling back to framework]: {e}"
                    )
                    state["agent"] = None
                    # Still provide a framework response after the error
                    bot_text_fb, metrics_fb = _build_framework_response(
                        state["system"], state["user_id"], message, state,
                    )
                    bot_text = f"{bot_text}\n\n---\n\n{bot_text_fb}"
                    metrics = metrics_fb or metrics
            else:
                # Direct framework path
                bot_text, new_metrics = _build_framework_response(
                    state["system"], state["user_id"], message, state,
                )
                if new_metrics:
                    metrics = new_metrics

            chat_history = chat_history + [{"role": "assistant", "content": bot_text}]
            metrics_md = _format_metrics_display(metrics)

            # Log assistant response with metrics snapshot
            if storage:
                storage.log_conversation(
                    session_id=session_id,
                    user_id=user_id,
                    role="assistant",
                    content=bot_text,
                    mode="agent" if state.get("agent") else "direct",
                    metrics=metrics,
                )

            return "", chat_history, state, metrics, metrics_md

        def clear_conversation(state: dict):
            """Reset conversation and framework state."""
            new_state = {
                "user_id": f"user_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "latest_experience_id": None,
                "latest_assessment": None,
                "system": None,
                "agent": None,
            }
            return (
                [],             # chatbot
                new_state,      # state
                None,           # metrics
                _format_metrics_display(None),  # metrics display
            )

        # Wire up events
        msg_input.submit(
            fn=respond,
            inputs=[msg_input, chatbot, chat_state, latest_metrics],
            outputs=[msg_input, chatbot, chat_state, latest_metrics, metrics_display],
        )
        send_btn.click(
            fn=respond,
            inputs=[msg_input, chatbot, chat_state, latest_metrics],
            outputs=[msg_input, chatbot, chat_state, latest_metrics, metrics_display],
        )
        clear_btn.click(
            fn=clear_conversation,
            inputs=[chat_state],
            outputs=[chatbot, chat_state, latest_metrics, metrics_display],
        )

    return demo
