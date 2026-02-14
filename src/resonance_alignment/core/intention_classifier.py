"""Infers intent as a VECTOR over time, not a snapshot label.

The fundamental insight: no activity is inherently creative or
consumptive.  Binge-watching anime could be an input phase with
creative intent (a future screenwriter) OR an endpoint with
consumptive intent.  Two kids playing the same video game -- one
with creative intent that will later reveal itself, one without.

At t=0 these are *indistinguishable*.  Intent inference must
therefore be:
  1. Provisional -- returned with low confidence at t=0.
  2. Trajectory-informed -- uses prior history if available.
  3. Retrospective -- confidence rises only as follow-up evidence
     reveals what the experience actually led to.

KEYWORD HINTS REMOVED (v0.4.0):
The original design used keyword lists ('produces', 'consumes', etc.)
as weak suggestive signals.  These were philosophically inconsistent
with the core principle that no activity is inherently creative or
consumptive -- intent is hidden at t=0.  At cold start, the correct
answer is PENDING with ~0 confidence -- the system genuinely does not
know the intent yet.
"""

from __future__ import annotations

from resonance_alignment.core.models import (
    Experience,
    IntentionSignal,
    UserTrajectory,
    VectorSnapshot,
)


class IntentionClassifier:
    """Vector-aware intent inference engine.

    Returns ``(IntentionSignal, confidence)`` where confidence reflects
    how much evidence supports the intent inference.  At t=0 with no
    history, confidence is very low and the signal is ``PENDING``.

    Two evidence sources, in order of strength:
      1. Follow-up evidence (strongest: what actually happened after?)
      2. Trajectory context (what is this user's existing vector?)

    At cold start (no follow-ups, no history), the system returns
    PENDING with near-zero confidence.  This is correct -- the system
    genuinely cannot infer intent yet.
    """

    _TRAJECTORY_WEIGHT = 0.45  # trajectory history
    _FOLLOWUP_WEIGHT = 0.55   # follow-up evidence (strongest signal)

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
        # 1. Trajectory context (what is this user's existing vector?)
        traj_direction = trajectory.current_vector.direction if trajectory.has_history else 0.0
        traj_confidence = trajectory.current_vector.confidence if trajectory.has_history else 0.0

        # 2. Follow-up evidence (the strongest and most reliable signal)
        fu_direction, fu_confidence = self._follow_up_evidence(experience)

        # Blend signals with appropriate weights
        if fu_confidence > 0:
            # We have follow-up data -- it dominates
            blended_direction = (
                self._TRAJECTORY_WEIGHT * traj_direction
                + self._FOLLOWUP_WEIGHT * fu_direction
            )
            blended_confidence = (
                self._TRAJECTORY_WEIGHT * traj_confidence
                + self._FOLLOWUP_WEIGHT * fu_confidence
            )
        elif trajectory.has_history:
            # No follow-ups but we have trajectory history -- weak prior
            blended_direction = traj_direction
            blended_confidence = min(traj_confidence * 0.4, 0.30)
        else:
            # Cold start: no evidence at all.  PENDING is the honest answer.
            blended_direction = 0.0
            blended_confidence = 0.0

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

    @staticmethod
    def _follow_up_evidence(experience: Experience) -> tuple[float, float]:
        """Compute direction and confidence from follow-up data.

        This is the most important signal: what actually happened after
        the experience?  Uses graduated creation magnitude for nuance.
        """
        if not experience.follow_ups:
            return 0.0, 0.0

        creative_signals = 0.0
        total_signals = 0.0
        for fu in experience.follow_ups:
            total_signals += 3.0  # three possible signal slots per follow-up
            if fu.created_something:
                # Use graduated magnitude (default 1.0 for backward compat)
                mag = fu.creation_magnitude if fu.creation_magnitude > 0 else 1.0
                creative_signals += mag
            if fu.shared_or_taught:
                creative_signals += 1.0
            if fu.inspired_further_action:
                creative_signals += 1.0

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
        """Map continuous direction to discrete intent inference."""
        if confidence < 0.15:
            return IntentionSignal.PENDING
        if direction > 0.2:
            return IntentionSignal.CREATIVE_INTENT
        elif direction < -0.2:
            return IntentionSignal.CONSUMPTIVE_INTENT
        else:
            return IntentionSignal.MIXED
