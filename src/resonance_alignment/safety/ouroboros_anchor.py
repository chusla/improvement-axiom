"""Trajectory-based drift detection for the Ouroboros cycle.

REVISED: The original design used static lists of 'clearly creative'
and 'clearly consumptive' *activities*.  This was flawed -- no activity
is inherently one or the other.  Binge-watching can be inspiration for
a screenwriter.  Video games can ignite a career in game development.
The same activity, two different intents.

The new design detects drift by watching *trajectory patterns*, not
activity labels.  Drift means:
  - A trajectory whose evidence suggests consumptive intent is being
    classified as creative (or vice versa).
  - The system's intent inferences are diverging from what the follow-up
    evidence actually demonstrates.

The Ouroboros cycle (creation feeds consumption feeds creation) is a
neutral, natural process.  The framework checks whether the *ratio of
creation to consumption evidence* over time suggests healthy intent
patterns -- not whether consumption is 'bad'.
"""

from __future__ import annotations

from resonance_alignment.core.models import (
    Experience,
    IntentionSignal,
    UserTrajectory,
)


class OuroborosAnchor:
    """Detects intent-inference drift using trajectory evidence.

    Rather than maintaining static 'ground truth' activity lists, this
    validates that the system's intent inferences are *consistent with
    observed outcomes*.

    If the system infers creative intent but no follow-up evidence of
    creation ever materialises, that is drift.  If a trajectory's
    evidence suggests consumptive intent but individual experiences keep
    being inferred as creative, that is drift.
    """

    # Thresholds
    DRIFT_CONFIDENCE_MIN = 0.3   # don't check drift below this confidence
    CLASSIFICATION_MISMATCH_THRESHOLD = 0.4  # how far label can diverge from evidence
    NATURAL_RATIO_MIN = 0.2  # minimum creation-to-total ratio for healthy cycle
    SUSTAINED_CONSUMPTION_THRESHOLD = 5  # consecutive consumptive experiences before warning

    def validate_classification(
        self,
        experience: Experience,
        trajectory: UserTrajectory,
    ) -> tuple[bool, str]:
        """Check whether an experience's classification matches evidence.

        Args:
            experience: The experience with its current provisional label.
            trajectory: The user's full trajectory for context.

        Returns:
            (is_valid, reason) -- False if drift is detected.
        """
        # If confidence is too low, classification is essentially 'pending'
        # and there's nothing to validate yet.
        if experience.intention_confidence < self.DRIFT_CONFIDENCE_MIN:
            return True, "Confidence too low to assess drift; classification is provisional."

        # Check 1: Does the label match the follow-up evidence?
        if experience.follow_ups:
            evidence_direction = self._evidence_direction(experience)
            label_direction = self._label_to_direction(experience.provisional_intention)

            mismatch = abs(evidence_direction - label_direction)
            if mismatch > self.CLASSIFICATION_MISMATCH_THRESHOLD:
                return False, (
                    f"Classification drift: label is "
                    f"'{experience.provisional_intention.value}' but follow-up "
                    f"evidence points {self._describe_direction(evidence_direction)} "
                    f"(mismatch {mismatch:.2f})."
                )

        # Check 2: Is this label consistent with the trajectory trend?
        if trajectory.has_history and len(trajectory.vector_history) >= 3:
            traj_direction = trajectory.current_vector.direction
            label_direction = self._label_to_direction(experience.provisional_intention)

            # A 'creative' label on an experience when the overall trajectory
            # is strongly consumptive is suspicious (not necessarily wrong,
            # but worth flagging).
            if (
                label_direction > 0.3
                and traj_direction < -0.3
                and experience.intention_confidence > 0.5
            ):
                return False, (
                    f"Classification drift: experience labelled 'creative' but "
                    f"overall trajectory is trending consumptive "
                    f"(direction {traj_direction:+.2f}).  "
                    f"This may be valid (a turning point) -- verify with follow-ups."
                )

        return True, "Classification consistent with available evidence."

    def check_ouroboros_health(self, trajectory: UserTrajectory) -> tuple[bool, str]:
        """Check if the Ouroboros cycle shows healthy intent patterns.

        The Ouroboros cycle is healthy when the evidence shows a
        sustainable ratio of creative output to input over time.
        A trajectory with no visible creative output may indicate
        consumptive intent -- but this is an inference, not a judgment.

        This does NOT judge individual activities -- it reads the
        *aggregate pattern* of intent over time.
        """
        if trajectory.experience_count < 3:
            return True, "Insufficient history to assess Ouroboros health."

        # Check creation rate
        if trajectory.creation_rate < self.NATURAL_RATIO_MIN:
            # Check for sustained consumption streak
            recent = trajectory.experiences[-self.SUSTAINED_CONSUMPTION_THRESHOLD:]
            all_consumptive = all(
                e.provisional_intention == IntentionSignal.CONSUMPTIVE_INTENT
                for e in recent
                if e.intention_confidence >= self.DRIFT_CONFIDENCE_MIN
            )
            if all_consumptive and len(recent) >= self.SUSTAINED_CONSUMPTION_THRESHOLD:
                return False, (
                    f"Ouroboros cycle notice: {self.SUSTAINED_CONSUMPTION_THRESHOLD} "
                    f"consecutive experiences with consumptive-intent inference and "
                    f"creation rate {trajectory.creation_rate:.0%}.  "
                    f"Intent may be purely input-focused."
                )

            return False, (
                f"Ouroboros cycle notice: creation rate is {trajectory.creation_rate:.0%} "
                f"(below {self.NATURAL_RATIO_MIN:.0%} threshold).  "
                f"The evidence so far suggests mostly input-focused intent."
            )

        # Check compounding direction
        if trajectory.compounding_direction < -0.3:
            return False, (
                f"Ouroboros cycle notice: inferred intent is accelerating toward "
                f"input-focused (compounding {trajectory.compounding_direction:+.2f}).  "
                f"The trend suggests a shift in intent pattern."
            )

        return True, (
            f"Ouroboros cycle healthy: creation rate {trajectory.creation_rate:.0%}, "
            f"compounding direction {trajectory.compounding_direction:+.2f}."
        )

    def verify_natural_pattern(self, action: dict, outcome: dict) -> tuple[bool, str]:
        """Check if an action/outcome pair reflects the Ouroboros cycle.

        In the natural cycle, consumption feeds creation (input leads to
        output).  This method checks whether the outcome evidence
        suggests creative intent behind the consumption.

        This method is retained for explicit action/outcome pair checks.
        """
        if outcome.get("contains_creation", False):
            consumption = action.get("required_consumption", 0.0)
            creation = outcome.get("creation_value", 0.0)
            if creation > 0 and consumption / creation < 1:
                return True, "Healthy cycle: input led to creative output."

        return False, "No visible creative output from this input yet."

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _evidence_direction(experience: Experience) -> float:
        """Compute directional signal from follow-up evidence.

        +1 = all follow-ups show creation/sharing/inspiration.
        -1 = no follow-ups show any creative output.
        """
        if not experience.follow_ups:
            return 0.0

        signals = 0
        total = 0
        for fu in experience.follow_ups:
            total += 3
            if fu.created_something:
                signals += 1
            if fu.shared_or_taught:
                signals += 1
            if fu.inspired_further_action:
                signals += 1

        if total == 0:
            return 0.0
        ratio = signals / total
        return (ratio * 2.0) - 1.0  # map [0,1] → [-1,1]

    @staticmethod
    def _label_to_direction(signal: IntentionSignal) -> float:
        """Map a discrete signal to a continuous direction."""
        return {
            IntentionSignal.CREATIVE_INTENT: 0.8,
            IntentionSignal.MIXED: 0.0,
            IntentionSignal.CONSUMPTIVE_INTENT: -0.8,
            IntentionSignal.PENDING: 0.0,
        }.get(signal, 0.0)

    @staticmethod
    def _describe_direction(direction: float) -> str:
        if direction > 0.3:
            return "toward creative intent"
        elif direction < -0.3:
            return "toward consumptive intent"
        return "mixed/unclear intent"
