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

        Three converging signals (all must be present for high risk):

        1. NARROWING VARIETY: Recent experiences cluster around the same
           activity type (measured by description similarity).
        2. ESCALATION PATTERN: Increasing frequency or intensity of
           similar experiences (needing more to get the same hit).
        3. DECLINING RETURNS: Resonance scores for similar experiences
           decrease over time (tolerance/habituation).

        Any one signal alone is not dependency -- a craftsman who does
        the same thing every day with rising quality is not dependent,
        they are devoted.  Dependency requires narrowing + escalation +
        declining returns together.
        """
        if trajectory.experience_count < 5:
            return 0.0

        recent = trajectory.experiences[-8:]

        # Signal 1: Narrowing variety (word-set overlap)
        word_sets = [
            set(e.description.lower().split()) - {"i", "a", "the", "and", "or", "to", "of"}
            for e in recent
        ]
        overlaps: list[float] = []
        for i in range(len(word_sets)):
            for j in range(i + 1, len(word_sets)):
                union = word_sets[i] | word_sets[j]
                if union:
                    overlaps.append(len(word_sets[i] & word_sets[j]) / len(union))
        narrowing = (sum(overlaps) / len(overlaps)) if overlaps else 0.0

        # Signal 2: Escalation (increasing frequency -- shorter gaps)
        if len(recent) >= 4:
            gaps_early = []
            gaps_late = []
            mid = len(recent) // 2
            for i in range(1, mid):
                gaps_early.append((recent[i].timestamp - recent[i - 1].timestamp).total_seconds())
            for i in range(mid + 1, len(recent)):
                gaps_late.append((recent[i].timestamp - recent[i - 1].timestamp).total_seconds())
            avg_early = (sum(gaps_early) / len(gaps_early)) if gaps_early else 1.0
            avg_late = (sum(gaps_late) / len(gaps_late)) if gaps_late else 1.0
            # Ratio < 1 means gaps are shrinking (escalation)
            escalation = max(0.0, 1.0 - (avg_late / max(avg_early, 1.0)))
        else:
            escalation = 0.0

        # Signal 3: Declining returns (resonance scores dropping)
        recent_scores = [e.resonance_score for e in recent if e.resonance_score > 0]
        if len(recent_scores) >= 4:
            mid = len(recent_scores) // 2
            avg_early_score = sum(recent_scores[:mid]) / mid
            avg_late_score = sum(recent_scores[mid:]) / (len(recent_scores) - mid)
            declining = max(0.0, avg_early_score - avg_late_score)
        else:
            declining = 0.0

        # Converging signals: all three must be present
        # Each signal contributes, but the product of any two that are
        # near-zero pulls the whole score down.
        risk = (
            0.40 * narrowing
            + 0.30 * escalation
            + 0.30 * declining
        )

        # Boost if ALL three are elevated (convergence multiplier)
        if narrowing > 0.3 and escalation > 0.2 and declining > 0.1:
            risk = min(risk * 1.5, 1.0)

        return max(0.0, min(1.0, risk))

    def _assess_predictability(
        self,
        experience: Experience,
        trajectory: UserTrajectory,
    ) -> float:
        """Check if resonance is too predictable.

        Genuine resonance is inherently unpredictable -- 'an old letter
        from a long lost friend, the peculiar shape of a leaf'.  If the
        system can too-easily predict what produces high resonance, it
        may be optimising for shallow dopamine patterns.

        Three signals:
        1. Score clustering: very low variance in recent resonance scores
        2. Rating inflation: user_rating consistently near ceiling
        3. Monotonic pattern: scores follow a flat/predictable trajectory

        High predictability → resonance may be manufactured.
        Low predictability → resonance is likely genuine.
        """
        if trajectory.experience_count < 5:
            return 0.0

        recent = trajectory.experiences[-10:]

        # Signal 1: Score clustering (low variance)
        recent_scores = [e.resonance_score for e in recent if e.resonance_score > 0]
        if len(recent_scores) < 3:
            return 0.0

        import numpy as np
        std = float(np.std(recent_scores))
        clustering = 0.0
        if std < 0.05:
            clustering = 0.9
        elif std < 0.10:
            clustering = 0.5
        elif std < 0.15:
            clustering = 0.2

        # Signal 2: Rating inflation (user always rates near max)
        recent_ratings = [e.user_rating for e in recent if e.user_rating > 0]
        inflation = 0.0
        if recent_ratings:
            avg_rating = sum(recent_ratings) / len(recent_ratings)
            if avg_rating > 0.9:
                inflation = 0.8
            elif avg_rating > 0.8:
                inflation = 0.4

        # Signal 3: Monotonic pattern (no surprises in the trajectory)
        if len(recent_scores) >= 5:
            diffs = [recent_scores[i] - recent_scores[i - 1] for i in range(1, len(recent_scores))]
            # If all diffs have the same sign or are near zero, it's monotonic
            near_zero = sum(1 for d in diffs if abs(d) < 0.05)
            monotonic = near_zero / len(diffs)
        else:
            monotonic = 0.0

        predictability = (
            0.50 * clustering
            + 0.25 * inflation
            + 0.25 * monotonic
        )

        return max(0.0, min(1.0, predictability))
