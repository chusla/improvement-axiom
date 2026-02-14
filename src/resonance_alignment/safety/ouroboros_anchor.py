"""Trajectory-based drift detection for the Ouroboros cycle.

REVISED: The original design used static lists of 'clearly creative'
and 'clearly consumptive' *activities*.  This was flawed -- no activity
is inherently one or the other.  Binge-watching can be inspiration for
a screenwriter.  Video games can ignite a career in game development.
The same activity, two different vectors.

The new design detects drift by watching *trajectory patterns*, not
activity labels.  Drift means:
  - A trajectory that the *evidence* shows is consumptive is being
    classified as creative (or vice versa).
  - The system's classifications are diverging from what the follow-up
    evidence actually demonstrates.

The Ouroboros cycle (creation feeds consumption feeds creation) is
honoured not by labelling activities but by checking whether the
*ratio of creation to consumption* over time follows a natural,
sustainable pattern.
"""

from __future__ import annotations

from resonance_alignment.core.models import (
    Experience,
    IntentionSignal,
    UserTrajectory,
)


class OuroborosAnchor:
    """Detects classification drift using trajectory evidence.

    Rather than maintaining static 'ground truth' activity lists, this
    validates that the system's classifications are *consistent with
    observed outcomes*.

    If the system labels an experience 'creative' but no follow-up
    evidence of creation ever materialises, that is drift.  If a
    trajectory is trending consumptive but individual experiences keep
    being labelled 'creative', that is drift.
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
        """Check if the creation/consumption cycle is healthy.

        The Ouroboros cycle is healthy when consumption *serves* creation
        -- when there is a sustainable ratio of creation to consumption
        over time.  A trajectory that is purely consumptive with no
        creative output is an unhealthy cycle.

        This does NOT judge individual activities -- it judges the
        *aggregate pattern* over time.
        """
        if trajectory.experience_count < 3:
            return True, "Insufficient history to assess Ouroboros health."

        # Check creation rate
        if trajectory.creation_rate < self.NATURAL_RATIO_MIN:
            # Check for sustained consumption streak
            recent = trajectory.experiences[-self.SUSTAINED_CONSUMPTION_THRESHOLD:]
            all_consumptive = all(
                e.provisional_intention == IntentionSignal.CONSUMPTIVE
                for e in recent
                if e.intention_confidence >= self.DRIFT_CONFIDENCE_MIN
            )
            if all_consumptive and len(recent) >= self.SUSTAINED_CONSUMPTION_THRESHOLD:
                return False, (
                    f"Ouroboros cycle unhealthy: {self.SUSTAINED_CONSUMPTION_THRESHOLD} "
                    f"consecutive consumptive experiences with creation rate "
                    f"{trajectory.creation_rate:.0%}.  Consumption is not serving creation."
                )

            return False, (
                f"Ouroboros cycle warning: creation rate is {trajectory.creation_rate:.0%} "
                f"(below {self.NATURAL_RATIO_MIN:.0%} minimum).  "
                f"The cycle may be tilting toward unsustainable consumption."
            )

        # Check compounding direction
        if trajectory.compounding_direction < -0.3:
            return False, (
                f"Ouroboros cycle warning: trajectory is accelerating toward "
                f"consumption (compounding {trajectory.compounding_direction:+.2f}).  "
                f"Even if creation rate is adequate now, the trend is concerning."
            )

        return True, (
            f"Ouroboros cycle healthy: creation rate {trajectory.creation_rate:.0%}, "
            f"compounding direction {trajectory.compounding_direction:+.2f}."
        )

    def verify_natural_pattern(self, action: dict, outcome: dict) -> tuple[bool, str]:
        """Check if an action follows the Ouroboros cycle as seen in nature.

        In nature, consumption serves creation (lion eats gazelle to
        sustain itself and reproduce).  Consumption without creation
        is the unnatural pattern.

        This method is retained for explicit action/outcome pair checks.
        """
        if outcome.get("contains_creation", False):
            consumption = action.get("required_consumption", 0.0)
            creation = outcome.get("creation_value", 0.0)
            if creation > 0 and consumption / creation < 1:
                return True, "Natural pattern: more created than consumed."

        return False, "Consumption without sufficient creation."

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
            IntentionSignal.CREATIVE: 0.8,
            IntentionSignal.MIXED: 0.0,
            IntentionSignal.CONSUMPTIVE: -0.8,
            IntentionSignal.PENDING: 0.0,
        }.get(signal, 0.0)

    @staticmethod
    def _describe_direction(direction: float) -> str:
        if direction > 0.3:
            return "toward creative"
        elif direction < -0.3:
            return "toward consumptive"
        return "mixed/neutral"
