"""Anti-wireheading validation using multi-timescale evidence and propagation.

REVISED: The original design had a binary check (immediate vs. one
predicted future score).  The new design uses:

1. Temporal arc analysis -- does the experience hold up across expanding
   time horizons?  Sugar hits collapse; genuine quality persists.

2. Propagation check -- did the resonance lead to downstream creation?
   Genuine resonance propagates; wireheading terminates at consumption.

3. Dependency pattern detection -- is the user becoming dependent on
   a particular type of experience?

4. Resonance unpredictability -- genuine resonance is inherently
   surprising and unpredictable.  If the system can too-easily predict
   what will produce high resonance, that's a sign it's optimising for
   shallow patterns rather than genuine quality.
"""

from __future__ import annotations

from resonance_alignment.core.models import (
    Experience,
    HorizonAssessment,
    UserTrajectory,
)


class ResonanceValidator:
    """Validates resonance authenticity through multiple lenses.

    Uses multi-timescale comparison, propagation history, dependency
    detection, and predictability analysis.
    """

    DEPENDENCY_THRESHOLD = 0.7
    LONG_TERM_RATIO_THRESHOLD = 0.5
    PENALTY_FACTOR = 0.3
    PREDICTABILITY_PENALTY = 0.15

    def validate(
        self,
        experience: Experience,
        trajectory: UserTrajectory,
        horizon_assessments: list[HorizonAssessment] | None = None,
    ) -> float:
        """Full validation pipeline.  Returns adjusted resonance score."""
        score = experience.resonance_score

        # 1. Arc analysis: does the score hold up across horizons?
        if horizon_assessments:
            score = self._apply_arc_adjustment(score, horizon_assessments)

        # 2. Propagation check: does this user's resonance lead to creation?
        score = self._apply_propagation_adjustment(score, trajectory)

        # 3. Dependency check
        dependency_risk = self._assess_dependency(trajectory)
        if dependency_risk > self.DEPENDENCY_THRESHOLD:
            score = score * self.PENALTY_FACTOR

        # 4. Predictability check: is resonance too predictable?
        predictability = self._assess_predictability(experience, trajectory)
        if predictability > 0.8:
            score = max(score - self.PREDICTABILITY_PENALTY, 0.0)

        return max(0.0, min(1.0, score))

    # Legacy API for backward compatibility
    def validate_resonance(self, immediate_score: float, context: dict) -> float:
        """Legacy API -- wraps the new validate() for old callers."""
        exp = Experience(resonance_score=immediate_score)
        traj = UserTrajectory()
        exp.resonance_score = immediate_score
        return self.validate(exp, traj)

    # ------------------------------------------------------------------
    # Adjustment lenses
    # ------------------------------------------------------------------

    def _apply_arc_adjustment(
        self,
        score: float,
        assessments: list[HorizonAssessment],
    ) -> float:
        """Adjust score based on temporal arc.

        If scores IMPROVE as horizons widen → genuine quality (small boost).
        If scores DECLINE as horizons widen → sugar hit (penalty).
        """
        scored = [a for a in assessments if a.score is not None]
        if len(scored) < 2:
            return score  # not enough data to adjust

        from resonance_alignment.core.models import TimeHorizon
        horizon_order = list(TimeHorizon)
        scored_sorted = sorted(scored, key=lambda a: horizon_order.index(a.horizon))

        # Compare earliest scored horizon to latest
        earliest = scored_sorted[0].score
        latest = scored_sorted[-1].score

        if latest > earliest + 0.1:
            # Arc bends toward better -- small trust boost
            return min(score + 0.05, 1.0)
        elif latest < earliest - 0.1:
            # Arc bends away -- penalty proportional to decline
            decline = earliest - latest
            return max(score * (1.0 - decline * 0.5), 0.0)

        return score

    def _apply_propagation_adjustment(
        self,
        score: float,
        trajectory: UserTrajectory,
    ) -> float:
        """Adjust based on whether this user's resonance propagates.

        Strong propagation history → trust the score.
        Weak propagation with many experiences → discount.
        """
        if trajectory.experience_count < 3:
            return score  # not enough history

        rate = trajectory.propagation_rate
        if rate > 0.5:
            return min(score + 0.05, 1.0)
        elif rate < 0.15:
            return max(score - 0.10, 0.0)

        return score

    def _assess_dependency(self, trajectory: UserTrajectory) -> float:
        """Detect dependency patterns in the trajectory.

        Dependency indicators:
        - Increasing frequency of similar experiences
        - Declining resonance scores over time for same type
        - Narrowing variety of experiences

        TODO: Implement full dependency detection.
        Currently uses a simplified heuristic based on experience
        descriptions.
        """
        if trajectory.experience_count < 5:
            return 0.0

        # Simple heuristic: if last 5 experiences are very similar
        # (measured by word overlap), that's a dependency signal.
        recent = trajectory.experiences[-5:]
        word_sets = [set(e.description.lower().split()) for e in recent]

        if not word_sets or not word_sets[0]:
            return 0.0

        # Average pairwise overlap
        overlaps: list[float] = []
        for i in range(len(word_sets)):
            for j in range(i + 1, len(word_sets)):
                union = word_sets[i] | word_sets[j]
                if union:
                    overlaps.append(len(word_sets[i] & word_sets[j]) / len(union))

        avg_overlap = sum(overlaps) / len(overlaps) if overlaps else 0.0

        # High overlap among recent experiences → dependency risk
        return min(avg_overlap * 1.5, 1.0)

    def _assess_predictability(
        self,
        experience: Experience,
        trajectory: UserTrajectory,
    ) -> float:
        """Check if resonance is too predictable.

        Genuine resonance is inherently unpredictable -- 'an old letter
        from a long lost friend, the peculiar shape of a leaf'.  If the
        system can too-easily predict what produces high resonance, it
        may be optimising for shallow dopamine patterns rather than
        genuine quality.

        High predictability → resonance may be manufactured.
        Low predictability → resonance is likely genuine.

        TODO: Implement full predictability model (requires prediction
        history tracking).
        """
        if trajectory.experience_count < 5:
            return 0.0  # not enough data to assess

        # Heuristic: if the user's last N resonance scores are all
        # clustered tightly, the system may be in a rut.
        recent_scores = [
            e.resonance_score
            for e in trajectory.experiences[-10:]
            if e.resonance_score > 0
        ]

        if len(recent_scores) < 3:
            return 0.0

        import numpy as np
        std = float(np.std(recent_scores))

        # Very low variance in resonance scores → too predictable
        # (genuine resonance should have natural variance)
        if std < 0.05:
            return 0.9
        elif std < 0.10:
            return 0.5
        return 0.1
