"""Human-in-the-loop verification for low-confidence or high-stakes decisions."""

from __future__ import annotations


class HumanVerification:
    """Routes low-confidence or high-stakes recommendations to human reviewers."""

    CONFIDENCE_THRESHOLD = 0.7

    HIGH_STAKES_KEYWORDS = [
        "health", "medical", "financial", "safety",
        "addiction", "dependency", "substance",
    ]

    def __init__(self):
        self.review_queue: list[dict] = []

    def flag_for_review(self, recommendation: dict, confidence: float) -> dict:
        """Send low-confidence or high-stakes decisions to humans.

        Args:
            recommendation: The recommendation to potentially flag.
            confidence: Confidence score for the recommendation.

        Returns:
            The recommendation (possibly with a review flag).
        """
        if confidence < self.CONFIDENCE_THRESHOLD or self._high_stakes(recommendation):
            flagged = {
                **recommendation,
                "_flagged_for_review": True,
                "_confidence": confidence,
                "_reason": self._get_flag_reason(recommendation, confidence),
            }
            self.review_queue.append(flagged)
            return flagged

        return recommendation

    def _high_stakes(self, recommendation: dict) -> bool:
        """Determine if a recommendation involves high-stakes decisions."""
        text = str(recommendation).lower()
        return any(keyword in text for keyword in self.HIGH_STAKES_KEYWORDS)

    def _get_flag_reason(self, recommendation: dict, confidence: float) -> str:
        if confidence < self.CONFIDENCE_THRESHOLD:
            return f"Low confidence ({confidence:.2f})"
        return "High-stakes content detected"
