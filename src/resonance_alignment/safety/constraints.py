"""Hard safety constraints to prevent wireheading and ensure balanced activity."""

from __future__ import annotations


class SafetyConstraints:
    """Enforces hard limits on recommendations to prevent wireheading
    and ensure a healthy balance of activities.
    """

    DEFAULT_CONSTRAINTS = {
        "max_passive_time": 4.0,        # hours per day
        "min_active_creation": 1.0,     # hours per day
        "social_interaction_min": 0.5,  # hours per day
        "physical_activity_min": 0.5,   # hours per day
    }

    def __init__(self, constraints: dict[str, float] | None = None):
        self.constraints = constraints or self.DEFAULT_CONSTRAINTS.copy()

    def apply_constraints(self, recommendation: dict) -> dict:
        """Apply hard limits to a recommendation.

        Args:
            recommendation: Dict describing the recommended action,
                including estimated time allocations.

        Returns:
            The recommendation, adjusted if it violates constraints.
        """
        if self._violates_constraints(recommendation):
            return self._adjust_recommendation(recommendation)
        return recommendation

    def _violates_constraints(self, recommendation: dict) -> bool:
        """Check if a recommendation violates any hard constraints."""
        passive_time = recommendation.get("passive_time", 0.0)
        active_creation = recommendation.get("active_creation", 0.0)
        social_time = recommendation.get("social_time", 0.0)
        physical_time = recommendation.get("physical_time", 0.0)

        if passive_time > self.constraints["max_passive_time"]:
            return True
        if active_creation < self.constraints["min_active_creation"]:
            return True
        if social_time < self.constraints["social_interaction_min"]:
            return True
        if physical_time < self.constraints["physical_activity_min"]:
            return True

        return False

    def _adjust_recommendation(self, recommendation: dict) -> dict:
        """Adjust a recommendation to satisfy constraints.

        TODO: Implement smarter rebalancing logic.
        """
        adjusted = recommendation.copy()
        adjusted["passive_time"] = min(
            adjusted.get("passive_time", 0.0),
            self.constraints["max_passive_time"],
        )
        adjusted["active_creation"] = max(
            adjusted.get("active_creation", 0.0),
            self.constraints["min_active_creation"],
        )
        adjusted["social_time"] = max(
            adjusted.get("social_time", 0.0),
            self.constraints["social_interaction_min"],
        )
        adjusted["physical_time"] = max(
            adjusted.get("physical_time", 0.0),
            self.constraints["physical_activity_min"],
        )
        adjusted["_adjusted"] = True
        return adjusted
