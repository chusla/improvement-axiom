"""Tracks individual trajectories over time as vectors, not labels.

The central insight: no activity is inherently creative or consumptive.
Two kids can play the same video game for the same duration -- one is
purely consuming, the other is fascinated and later starts building
games.  At t=0 these are indistinguishable.  The difference is the
*vector* -- the direction revealed over time.

VectorTracker records experiences, accepts follow-up observations, and
computes a trajectory that evolves as evidence accumulates.  It never
labels an activity; it tracks what activities *lead to*.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import numpy as np

from resonance_alignment.core.models import (
    Experience,
    FollowUp,
    IntentionSignal,
    UserTrajectory,
    VectorSnapshot,
    TimeHorizon,
)


class VectorTracker:
    """Tracks the creative / consumptive trajectory of individuals.

    Instead of labeling activities, it watches what activities *lead to*
    over time.  The vector has direction (creative ↔ consumptive),
    magnitude (signal strength), and confidence (how much evidence
    supports the reading).

    Confidence starts near zero at t=0 and grows with follow-up evidence.
    """

    # How quickly confidence decays for experiences without follow-ups.
    _CONFIDENCE_HALFLIFE_DAYS = 14.0

    # Weights for different follow-up signals when computing direction.
    _CREATION_WEIGHT = 0.40
    _SHARING_WEIGHT = 0.25
    _INSPIRATION_WEIGHT = 0.20
    _RATING_WEIGHT = 0.15  # user's own resonance rating (weakest signal)

    # Recency weighting: experiences older than this contribute less.
    _RECENCY_HALFLIFE_DAYS = 90.0

    def __init__(self) -> None:
        self.trajectories: dict[str, UserTrajectory] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_experience(
        self,
        user_id: str,
        description: str,
        context: str,
        user_rating: float,
        timestamp: datetime | None = None,
    ) -> Experience:
        """Record a new experience and return it with a PROVISIONAL vector.

        At t=0 with no history the classification is ``PENDING`` with
        very low confidence.  If the user has prior history, the
        trajectory informs (but does not determine) the provisional
        reading.
        """
        ts = timestamp or datetime.utcnow()
        trajectory = self._get_or_create_trajectory(user_id)

        experience = Experience(
            user_id=user_id,
            description=description,
            context=context,
            user_rating=user_rating,
            timestamp=ts,
        )

        # Provisional vector based on history alone (NOT activity keywords)
        provisional = self._compute_provisional_vector(trajectory, experience)
        experience.vector_snapshots.append(provisional)
        experience.provisional_intention = self._direction_to_signal(provisional.direction)
        experience.intention_confidence = provisional.confidence

        trajectory.experiences.append(experience)
        self._update_trajectory_vector(trajectory)

        return experience

    def record_follow_up(
        self,
        user_id: str,
        experience_id: str,
        follow_up: FollowUp,
    ) -> Experience | None:
        """Record what happened after an experience; updates the vector.

        This is the primary mechanism by which classification evolves.
        Each follow-up raises confidence and may shift direction.
        """
        trajectory = self.trajectories.get(user_id)
        if trajectory is None:
            return None

        experience = self._find_experience(trajectory, experience_id)
        if experience is None:
            return None

        follow_up.experience_id = experience_id
        experience.follow_ups.append(follow_up)

        # Recompute vector for this experience with new evidence
        updated = self._recompute_experience_vector(experience)
        experience.vector_snapshots.append(updated)
        experience.provisional_intention = self._direction_to_signal(updated.direction)
        experience.intention_confidence = updated.confidence

        # Update propagation flag
        if follow_up.created_something or follow_up.shared_or_taught:
            experience.propagated = True
            if follow_up.creation_description:
                experience.propagation_events.append(follow_up.creation_description)

        self._update_trajectory_vector(trajectory)
        return experience

    def get_trajectory(self, user_id: str) -> UserTrajectory | None:
        """Return the full trajectory for a user."""
        return self.trajectories.get(user_id)

    def compute_vector(self, user_id: str) -> VectorSnapshot:
        """Compute current aggregate vector from all available evidence."""
        trajectory = self.trajectories.get(user_id)
        if trajectory is None or not trajectory.has_history:
            return VectorSnapshot(confidence=0.0)
        return self._aggregate_vector(trajectory)

    def compute_compounding_rate(self, user_id: str) -> float:
        """Second derivative: is the vector *accelerating*?

        Positive → trending more creative over time.
        Negative → trending more consumptive over time.
        Zero → stable.
        """
        trajectory = self.trajectories.get(user_id)
        if trajectory is None or len(trajectory.vector_history) < 2:
            return 0.0

        recent = trajectory.vector_history[-1].direction
        earlier = trajectory.vector_history[-2].direction
        return recent - earlier

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create_trajectory(self, user_id: str) -> UserTrajectory:
        if user_id not in self.trajectories:
            self.trajectories[user_id] = UserTrajectory(user_id=user_id)
        return self.trajectories[user_id]

    @staticmethod
    def _find_experience(trajectory: UserTrajectory, experience_id: str) -> Experience | None:
        for exp in trajectory.experiences:
            if exp.id == experience_id:
                return exp
        return None

    def _compute_provisional_vector(
        self, trajectory: UserTrajectory, experience: Experience
    ) -> VectorSnapshot:
        """Provisional vector at t=0.

        With no history → direction=0 (neutral), confidence≈0.
        With history → lean toward the user's existing trajectory but
        with LOW confidence (the new experience hasn't proven anything yet).
        """
        if not trajectory.has_history:
            return VectorSnapshot(
                timestamp=experience.timestamp,
                direction=0.0,
                magnitude=0.1,
                confidence=0.05,  # almost no confidence at t=0 with no history
                horizon=TimeHorizon.IMMEDIATE,
            )

        # Use existing trajectory as a weak prior
        current = self._aggregate_vector(trajectory)
        return VectorSnapshot(
            timestamp=experience.timestamp,
            direction=current.direction * 0.3,  # dampen: new experience is unknown
            magnitude=current.magnitude * 0.3,
            confidence=min(current.confidence * 0.2, 0.25),  # cap provisional confidence
            horizon=TimeHorizon.IMMEDIATE,
        )

    def _recompute_experience_vector(self, experience: Experience) -> VectorSnapshot:
        """Recompute vector for a single experience using its follow-ups."""
        if not experience.follow_ups:
            # No follow-ups yet → keep whatever provisional we had
            if experience.vector_snapshots:
                return experience.vector_snapshots[-1]
            return VectorSnapshot(confidence=0.05)

        # Compute creative signal from follow-up evidence
        creation_signals: list[float] = []
        for fu in experience.follow_ups:
            signal = 0.0
            if fu.created_something:
                signal += self._CREATION_WEIGHT
            if fu.shared_or_taught:
                signal += self._SHARING_WEIGHT
            if fu.inspired_further_action:
                signal += self._INSPIRATION_WEIGHT
            creation_signals.append(signal)

        # Average creation signal across follow-ups (0 = no creative evidence)
        avg_creation = sum(creation_signals) / len(creation_signals) if creation_signals else 0.0

        # Direction: scale from -1..+1.  Pure creation → +1, no signals → slight negative
        # (absence of creative output after an experience leans consumptive)
        direction = (avg_creation * 2.0) - 0.3  # slight negative bias when no creation
        direction = max(-1.0, min(1.0, direction))

        # Include user rating as a weak signal toward positive direction
        rating_nudge = (experience.user_rating - 0.5) * self._RATING_WEIGHT
        direction = max(-1.0, min(1.0, direction + rating_nudge))

        # Magnitude: stronger when more follow-ups agree
        magnitude = min(avg_creation + 0.2, 1.0)

        # Confidence: rises with number of follow-ups and time elapsed
        n_follow_ups = len(experience.follow_ups)
        confidence = min(0.15 + n_follow_ups * 0.15, 0.95)

        return VectorSnapshot(
            timestamp=datetime.utcnow(),
            direction=direction,
            magnitude=magnitude,
            confidence=confidence,
            horizon=self._infer_horizon(experience),
        )

    def _aggregate_vector(self, trajectory: UserTrajectory) -> VectorSnapshot:
        """Aggregate across all experiences with recency weighting."""
        now = datetime.utcnow()
        weighted_directions: list[float] = []
        weighted_magnitudes: list[float] = []
        weighted_confidences: list[float] = []
        total_weight = 0.0

        for exp in trajectory.experiences:
            if not exp.vector_snapshots:
                continue
            latest = exp.vector_snapshots[-1]
            age_days = max((now - exp.timestamp).total_seconds() / 86400.0, 0.01)
            recency_weight = math.exp(
                -0.693 * age_days / self._RECENCY_HALFLIFE_DAYS
            )
            w = recency_weight * latest.confidence
            weighted_directions.append(latest.direction * w)
            weighted_magnitudes.append(latest.magnitude * w)
            weighted_confidences.append(latest.confidence * w)
            total_weight += w

        if total_weight < 1e-9:
            return VectorSnapshot(confidence=0.0)

        agg_direction = sum(weighted_directions) / total_weight
        agg_magnitude = sum(weighted_magnitudes) / total_weight
        agg_confidence = sum(weighted_confidences) / total_weight

        return VectorSnapshot(
            timestamp=now,
            direction=max(-1.0, min(1.0, agg_direction)),
            magnitude=max(0.0, min(1.0, agg_magnitude)),
            confidence=max(0.0, min(1.0, agg_confidence)),
        )

    def _update_trajectory_vector(self, trajectory: UserTrajectory) -> None:
        """Refresh the trajectory's aggregate vector and derived rates."""
        agg = self._aggregate_vector(trajectory)
        trajectory.current_vector = agg
        trajectory.vector_history.append(agg)

        # Creation rate: fraction of experiences that propagated
        total = len(trajectory.experiences)
        if total > 0:
            trajectory.creation_rate = (
                sum(1 for e in trajectory.experiences if e.propagated) / total
            )

        # Compounding direction (second derivative)
        if len(trajectory.vector_history) >= 2:
            trajectory.compounding_direction = (
                trajectory.vector_history[-1].direction
                - trajectory.vector_history[-2].direction
            )

    @staticmethod
    def _direction_to_signal(direction: float) -> IntentionSignal:
        """Map continuous direction to a discrete signal."""
        if direction > 0.2:
            return IntentionSignal.CREATIVE
        elif direction < -0.2:
            return IntentionSignal.CONSUMPTIVE
        else:
            return IntentionSignal.MIXED

    @staticmethod
    def _infer_horizon(experience: Experience) -> TimeHorizon:
        """Infer the evaluation horizon from follow-up timing."""
        if not experience.follow_ups:
            return TimeHorizon.IMMEDIATE
        latest_fu = max(experience.follow_ups, key=lambda f: f.timestamp)
        delta = latest_fu.timestamp - experience.timestamp
        if delta < timedelta(days=2):
            return TimeHorizon.SHORT_TERM
        elif delta < timedelta(weeks=4):
            return TimeHorizon.MEDIUM_TERM
        elif delta < timedelta(days=180):
            return TimeHorizon.LONG_TERM
        else:
            return TimeHorizon.GENERATIONAL
