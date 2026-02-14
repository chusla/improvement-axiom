"""Classifies intention as a VECTOR over time, not a snapshot label.

The fundamental insight: no activity is inherently creative or
consumptive.  Binge-watching anime could be pure consumption OR the
seed that inspires a screenwriter.  Two kids playing the same video
game -- one consuming, one fascinated enough to later build games.

At t=0 these are *indistinguishable*.  Classification must therefore
be:
  1. Provisional -- returned with low confidence at t=0.
  2. Trajectory-informed -- uses prior history if available.
  3. Retrospective -- confidence rises only as follow-up evidence
     reveals what the experience actually led to.

The old keyword-based indicators are retained as *weak suggestive
signals* (not deterministic classifiers).  They are blended with
the trajectory vector and weighted far below follow-up evidence.
"""

from __future__ import annotations

from resonance_alignment.core.models import (
    Experience,
    IntentionSignal,
    UserTrajectory,
    VectorSnapshot,
)


class IntentionClassifier:
    """Vector-aware intention classifier.

    Returns ``(IntentionSignal, confidence)`` where confidence reflects
    how much evidence supports the classification.  At t=0 with no
    history, confidence is very low and the signal may be ``PENDING``.
    """

    # Weak suggestive signals -- NOT deterministic.  These nudge the
    # provisional reading when there is no trajectory history, but
    # they carry very little weight once follow-up data exists.
    CREATIVE_HINTS = [
        "produces", "builds", "enhances", "teaches",
        "shares", "improves", "creates", "generates",
        "writes", "designs", "composes", "invents",
        "mentors", "experiments", "practices", "learns",
    ]

    CONSUMPTIVE_HINTS = [
        "depletes", "extracts", "uses_up", "diminishes",
        "takes", "consumes", "exhausts", "wastes",
    ]

    # Weight of keyword hints relative to trajectory evidence
    _HINT_WEIGHT = 0.10   # very low -- keywords are almost noise
    _TRAJECTORY_WEIGHT = 0.40  # trajectory history
    _FOLLOWUP_WEIGHT = 0.50  # follow-up evidence (strongest signal)

    def classify(
        self,
        experience: Experience,
        trajectory: UserTrajectory,
    ) -> tuple[IntentionSignal, float]:
        """Classify an experience's intention given trajectory context.

        Args:
            experience: The experience to classify (may have follow-ups).
            trajectory: The user's full trajectory history.

        Returns:
            Tuple of (signal, confidence).  Confidence < 0.3 means the
            system is essentially saying 'I don't know yet'.
        """
        # 1. Weak keyword hints (almost noise, but non-zero for cold start)
        hint_direction, hint_magnitude = self._keyword_hints(experience.description)

        # 2. Trajectory context (what is this user's existing vector?)
        traj_direction = trajectory.current_vector.direction if trajectory.has_history else 0.0
        traj_confidence = trajectory.current_vector.confidence if trajectory.has_history else 0.0

        # 3. Follow-up evidence (the strongest and most reliable signal)
        fu_direction, fu_confidence = self._follow_up_evidence(experience)

        # Blend signals with appropriate weights
        if fu_confidence > 0:
            # We have follow-up data -- it dominates
            blended_direction = (
                self._HINT_WEIGHT * hint_direction
                + self._TRAJECTORY_WEIGHT * traj_direction
                + self._FOLLOWUP_WEIGHT * fu_direction
            )
            blended_confidence = (
                self._HINT_WEIGHT * hint_magnitude
                + self._TRAJECTORY_WEIGHT * traj_confidence
                + self._FOLLOWUP_WEIGHT * fu_confidence
            )
        elif trajectory.has_history:
            # No follow-ups but we have trajectory history
            blended_direction = (
                0.25 * hint_direction
                + 0.75 * traj_direction
            )
            blended_confidence = min(traj_confidence * 0.4, 0.30)
        else:
            # Cold start: only hints, minimal confidence
            blended_direction = hint_direction
            blended_confidence = hint_magnitude * 0.15  # cap at ~0.15

        # Clamp
        blended_direction = max(-1.0, min(1.0, blended_direction))
        blended_confidence = max(0.0, min(1.0, blended_confidence))

        signal = self._direction_to_signal(blended_direction, blended_confidence)
        return signal, blended_confidence

    # Keep the old API as a compatibility shim
    def classify_intent(
        self, action: str, context: str
    ) -> tuple[str, float]:
        """Legacy API -- wraps ``classify()`` for backward compatibility.

        Creates a minimal Experience and empty trajectory.
        """
        exp = Experience(description=action, context=context)
        traj = UserTrajectory()
        signal, confidence = self.classify(exp, traj)
        return signal.value, confidence

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _keyword_hints(self, text: str) -> tuple[float, float]:
        """Extract a weak directional hint from keywords.

        Returns (direction, magnitude) where direction is in [-1, 1]
        and magnitude indicates how many keywords matched.
        """
        text_lower = text.lower()
        creative_hits = sum(1 for k in self.CREATIVE_HINTS if k in text_lower)
        consumptive_hits = sum(1 for k in self.CONSUMPTIVE_HINTS if k in text_lower)
        total = creative_hits + consumptive_hits

        if total == 0:
            return 0.0, 0.0

        direction = (creative_hits - consumptive_hits) / total  # [-1, 1]
        magnitude = min(total / 5.0, 1.0)  # normalise, cap at 1
        return direction, magnitude

    @staticmethod
    def _follow_up_evidence(experience: Experience) -> tuple[float, float]:
        """Compute direction and confidence from follow-up data.

        This is the most important signal: what actually happened after
        the experience?
        """
        if not experience.follow_ups:
            return 0.0, 0.0

        creative_signals = 0
        total_signals = 0
        for fu in experience.follow_ups:
            total_signals += 3  # three possible signals per follow-up
            if fu.created_something:
                creative_signals += 1
            if fu.shared_or_taught:
                creative_signals += 1
            if fu.inspired_further_action:
                creative_signals += 1

        if total_signals == 0:
            return 0.0, 0.0

        ratio = creative_signals / total_signals
        direction = (ratio * 2.0) - 0.5  # map [0,1] → [-0.5, 1.5], clamp later
        direction = max(-1.0, min(1.0, direction))

        # Confidence scales with number of follow-ups
        confidence = min(0.2 + len(experience.follow_ups) * 0.2, 0.95)

        return direction, confidence

    @staticmethod
    def _direction_to_signal(direction: float, confidence: float) -> IntentionSignal:
        """Map continuous direction to discrete signal."""
        if confidence < 0.15:
            return IntentionSignal.PENDING
        if direction > 0.2:
            return IntentionSignal.CREATIVE
        elif direction < -0.2:
            return IntentionSignal.CONSUMPTIVE
        else:
            return IntentionSignal.MIXED
