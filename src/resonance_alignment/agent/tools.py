"""Anthropic tool definitions for the three framework entry points.

Defines the tool schemas that the LLM agent uses to interact with
the Improvement Axiom framework.  Each tool maps to one of the
three entry points on ResonanceAlignmentSystem.

Also provides serialisation helpers to convert framework results
into concise JSON the agent can reason about.
"""

from __future__ import annotations

from typing import Any

from resonance_alignment.core.models import (
    AssessmentResult,
    ArtifactVerification,
)


# ------------------------------------------------------------------
# Tool definitions (Anthropic format)
# ------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    # Server-side web search tool -- Anthropic handles execution.
    # Claude uses this automatically when it needs current evidence,
    # research, or real-time information to ground its responses.
    {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 5,
    },
    {
        "name": "process_experience",
        "description": (
            "Record a new experience the user describes.  Use this when "
            "the user tells you about an activity, hobby, or event they "
            "participated in.  Returns a provisional assessment with low "
            "confidence -- the vector needs time and follow-ups to reveal "
            "itself.  NEVER use keywords in the description to pre-judge "
            "the intention; the system evaluates trajectory, not labels."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "Unique identifier for the user.",
                },
                "description": {
                    "type": "string",
                    "description": (
                        "Factual description of what the user did.  "
                        "Use the user's own words.  Do NOT add "
                        "evaluative language."
                    ),
                },
                "user_rating": {
                    "type": "number",
                    "description": (
                        "How positively the user felt about the experience "
                        "(0.0 = terrible, 1.0 = amazing).  Infer from their "
                        "tone and words."
                    ),
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "context": {
                    "type": "string",
                    "description": (
                        "Additional context: when, where, with whom, "
                        "why they're telling you."
                    ),
                },
            },
            "required": ["user_id", "description", "user_rating", "context"],
        },
    },
    {
        "name": "process_follow_up",
        "description": (
            "Record what happened AFTER a previously recorded experience.  "
            "Use this when the user tells you about outcomes, actions taken "
            "since then, things created, or inspiration gained.  This is "
            "how confidence rises and classification evolves.  Each follow-up "
            "shifts the vector based on evidence."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "Unique identifier for the user.",
                },
                "experience_id": {
                    "type": "string",
                    "description": "ID of the original experience this follows up on.",
                },
                "content": {
                    "type": "string",
                    "description": "What happened since the experience.  Use the user's own words.",
                },
                "created_something": {
                    "type": "boolean",
                    "description": (
                        "Did the user create something tangible?  A blog post, "
                        "code, art, a meal, a lesson plan, a mod, etc."
                    ),
                },
                "creation_magnitude": {
                    "type": "number",
                    "description": (
                        "Degree of creation: 0.0 = nothing, 0.25 = sketched/started, "
                        "0.5 = partial draft/prototype, 0.75 = substantial work, "
                        "1.0 = completed and shipped."
                    ),
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "creation_description": {
                    "type": "string",
                    "description": "Brief description of what was created, if anything.",
                },
                "shared_or_taught": {
                    "type": "boolean",
                    "description": (
                        "Did the user share their creation or teach someone "
                        "something related to the experience?"
                    ),
                },
                "inspired_further_action": {
                    "type": "boolean",
                    "description": (
                        "Did the experience inspire the user to take further "
                        "action, learn more, or create something?"
                    ),
                },
            },
            "required": ["user_id", "experience_id", "content"],
        },
    },
    {
        "name": "submit_artifact",
        "description": (
            "Submit a URL to an externally-hosted artifact as evidence of "
            "creation.  Use this when the user shares a link to something "
            "they made: a blog post, GitHub repo, YouTube video, forum "
            "post, etc.  The system verifies the artifact exists and is "
            "substantive.  This is PORTFOLIO-BASED verification: the "
            "person presents, the system confirms."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "Unique identifier for the user.",
                },
                "experience_id": {
                    "type": "string",
                    "description": "ID of the experience this artifact evidences.",
                },
                "url": {
                    "type": "string",
                    "description": "The URL of the artifact to verify.",
                },
                "user_claim": {
                    "type": "string",
                    "description": "What the user says this artifact is.",
                },
            },
            "required": ["user_id", "experience_id", "url"],
        },
    },
]


# ------------------------------------------------------------------
# Result serialisation
# ------------------------------------------------------------------

def serialize_result(result: Any) -> dict[str, Any]:
    """Serialize a framework result to a concise dict for the agent.

    The agent receives this as the tool result and reasons about it
    to generate its conversational response.
    """
    if isinstance(result, AssessmentResult):
        return _serialize_assessment(result)
    elif isinstance(result, ArtifactVerification):
        return _serialize_verification(result)
    elif result is None:
        return {"error": "Experience not found"}
    return {"raw": str(result)}


def _serialize_assessment(r: AssessmentResult) -> dict[str, Any]:
    """Serialize an AssessmentResult to a concise dict."""
    exp = r.experience
    traj = r.trajectory
    vec = traj.current_vector if traj else None

    out: dict[str, Any] = {
        "experience_id": exp.id,
        "intention": exp.provisional_intention.value,
        "intention_confidence": round(exp.intention_confidence, 3),
        "is_provisional": r.is_provisional,
        "quality_score": round(exp.quality_score, 3),
        "resonance_score": round(exp.resonance_score, 3),
        "matrix_position": exp.matrix_position,
        "arc_trend": r.arc_trend,
    }

    if vec:
        out["vector"] = {
            "direction": round(vec.direction, 3),
            "magnitude": round(vec.magnitude, 3),
            "confidence": round(vec.confidence, 3),
        }

    if traj:
        out["trajectory"] = {
            "experience_count": traj.experience_count,
            "creation_rate": round(traj.creation_rate, 3),
            "compounding_direction": round(traj.compounding_direction, 3),
        }

    if r.pending_questions:
        out["follow_up_questions"] = [
            {"question": q.question, "ask_after": q.ask_after.isoformat()}
            for q in r.pending_questions[:3]  # Limit to 3 for conciseness
        ]

    if r.recommendations:
        out["recommendations"] = r.recommendations[:3]

    return out


def _serialize_verification(v: ArtifactVerification) -> dict[str, Any]:
    """Serialize an ArtifactVerification to a concise dict."""
    return {
        "status": v.status,
        "url_accessible": v.url_accessible,
        "content_substantive": v.content_substantive,
        "content_summary": v.content_summary,
        "relevance_score": round(v.relevance_score, 3),
        "timestamp_plausible": v.timestamp_plausible,
        "notes": v.notes,
    }
