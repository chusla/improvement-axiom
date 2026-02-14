"""Transparency layer providing clear reasoning for all recommendations.

Language in explanations is deliberately action-focused.  The system
explains what was OBSERVED about the action and its outcomes, never
making claims about the person's identity, group membership, or
demographic characteristics.
"""

from __future__ import annotations


class ExplainableResonance:
    """Provides human-readable explanations grounded in observable evidence."""

    def explain_recommendation(self, recommendation: dict) -> dict:
        """Generate a structured explanation for a recommendation.

        Args:
            recommendation: Dict containing position, quality, intention,
                resonance, and other scores.

        Returns:
            Dict with explanations for each dimension.
        """
        return {
            "resonance_prediction": self._explain_resonance(recommendation),
            "quality_assessment": self._explain_quality(recommendation),
            "intention_classification": self._explain_intention(recommendation),
            "alternative_options": self._list_alternatives(recommendation),
        }

    def _explain_resonance(self, recommendation: dict) -> str:
        score = recommendation.get("resonance", 0.0)
        if score > 0.7:
            return (
                f"High resonance ({score:.2f}): this action produced a strong "
                f"response based on observed engagement and your own reported experience."
            )
        elif score > 0.4:
            return (
                f"Moderate resonance ({score:.2f}): this action produced a "
                f"moderate response.  Follow-up observations will clarify."
            )
        else:
            return (
                f"Low resonance ({score:.2f}): this action produced a weak "
                f"response based on available observations."
            )

    def _explain_quality(self, recommendation: dict) -> str:
        score = recommendation.get("quality", 0.0)
        if score > 0.7:
            return f"High quality ({score:.2f}): durable, rich, and growth-enabling."
        elif score > 0.4:
            return f"Moderate quality ({score:.2f}): some positive dimensions, room for improvement."
        else:
            return f"Low quality ({score:.2f}): limited durability, richness, or growth potential."

    def _explain_intention(self, recommendation: dict) -> str:
        intention = recommendation.get("intention", "unknown")
        if isinstance(intention, str):
            intent_value = intention
        else:
            # Handle IntentionSignal enum
            intent_value = getattr(intention, "value", str(intention))

        return {
            "creative": "Creative vector: observable evidence suggests this action is producing new value.",
            "consumptive": "Consumptive vector: observable evidence suggests this action primarily extracts value.",
            "mixed": "Mixed vector: observable evidence shows both creative and consumptive elements.",
            "pending": "Vector pending: not enough observable evidence yet.  The system is watching, not judging.",
        }.get(intent_value, f"Intention not yet classifiable: {intent_value}")

    def _list_alternatives(self, recommendation: dict) -> list[str]:
        """Suggest alternative actions based on matrix position.

        This provides lightweight positional hints only.  The main
        coaching logic lives in the pipeline: system.py generates
        trajectory-aware recommendations for every quadrant, and the
        ExtrapolationModel provides evidence-based hypotheses with
        empowerment notes and distinguishing factors.  Any agent
        consuming the AssessmentResult has the full context to coach.

        These hints are supplementary for simple consumers that only
        have the recommendation dict.
        """
        position = recommendation.get("position", "")
        if not isinstance(position, str):
            return []

        if "Optimal" in position:
            return [
                "You're in the target quadrant.  Keep creating and sharing.",
                "Consider mentoring or teaching what you've learned.",
            ]
        elif "Hedonism" in position:
            return [
                "High quality input -- now channel it into something you create.",
                "Try a time-bounded session followed by an active/creative sprint.",
            ]
        elif "Slop" in position:
            return [
                "Creative intent is there.  Seek feedback to raise quality.",
                "Study work you admire in this area.  Iteration raises the bar.",
            ]
        elif "Junk Food" in position:
            return [
                "Pair this with a hands-on component -- build, write, teach, share.",
                "Even small creative acts shift the vector over time.",
            ]
        elif "Transitional" in position:
            return [
                "Lean into the creative elements of this experience.",
            ]
        elif "Pending" in position:
            return [
                "Too early to suggest alternatives.  The vector is still forming.",
            ]
        return []
