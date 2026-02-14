"""Evaluates outcomes across expanding time horizons -- the 'long arc'.

The key determinant of any measurable outcome in determining causality
is an issue of time horizon.  As Dr. King said: 'The arc of the moral
universe is long, but it bends towards justice.'

This component operationalises that principle.  The longer something
stays 'Better' as you zoom out, the more confidently the system
validates it.  Conversely, if an outcome looks great at t=0 but
degrades as the horizon widens, that is the hallmark of a sugar hit,
wireheading, or consumption masquerading as quality.
"""

from __future__ import annotations

from resonance_alignment.core.models import (
    Experience,
    HorizonAssessment,
    TimeHorizon,
    UserTrajectory,
    VectorSnapshot,
)


class TemporalEvaluator:
    """Multi-timescale evaluation engine.

    Horizons that lack evidence are returned as ``None`` (pending)
    rather than guessed.  Only horizons with actual data contribute
    to the weighted score.

    Weights increase with horizon breadth -- longer-validated outcomes
    carry more moral weight.
    """

    HORIZON_WEIGHTS: dict[TimeHorizon, float] = {
        TimeHorizon.IMMEDIATE: 0.05,
        TimeHorizon.SHORT_TERM: 0.10,
        TimeHorizon.MEDIUM_TERM: 0.20,
        TimeHorizon.LONG_TERM: 0.30,
        TimeHorizon.GENERATIONAL: 0.35,
    }

    def evaluate(
        self,
        experience: Experience,
        trajectory: UserTrajectory,
    ) -> list[HorizonAssessment]:
        """Evaluate an experience across all available time horizons.

        Returns one ``HorizonAssessment`` per horizon.  Horizons without
        evidence have ``score=None``.
        """
        assessments: list[HorizonAssessment] = []
        for horizon in TimeHorizon:
            assessment = self._evaluate_at_horizon(experience, trajectory, horizon)
            assessments.append(assessment)
        return assessments

    def compute_arc_trend(self, assessments: list[HorizonAssessment]) -> str:
        """Determine whether the arc bends toward 'Better' or away.

        * ``'improving'``  -- scores rise as horizons expand (genuine quality).
        * ``'declining'``  -- scores drop as horizons expand (sugar hit / wireheading).
        * ``'stable'``     -- scores roughly constant across horizons.
        * ``'insufficient_data'`` -- fewer than two horizons have evidence.
        """
        scored = [(a.horizon, a.score) for a in assessments if a.score is not None]
        if len(scored) < 2:
            return "insufficient_data"

        # Compare across ordered horizons
        horizon_order = list(TimeHorizon)
        scored_sorted = sorted(scored, key=lambda x: horizon_order.index(x[0]))

        diffs: list[float] = []
        for i in range(1, len(scored_sorted)):
            diffs.append(scored_sorted[i][1] - scored_sorted[i - 1][1])

        avg_diff = sum(diffs) / len(diffs)
        if avg_diff > 0.05:
            return "improving"
        elif avg_diff < -0.05:
            return "declining"
        return "stable"

    def weighted_score(self, assessments: list[HorizonAssessment]) -> float | None:
        """Compute a single weighted score from horizon assessments.

        Only horizons with evidence contribute.  Returns ``None`` if
        no horizon has been evaluated yet.
        """
        total_weight = 0.0
        total_score = 0.0
        for a in assessments:
            if a.score is not None:
                w = self.HORIZON_WEIGHTS.get(a.horizon, 0.1)
                total_score += a.score * w
                total_weight += w
        if total_weight < 1e-9:
            return None
        return total_score / total_weight

    # ------------------------------------------------------------------
    # Per-horizon evaluation
    # ------------------------------------------------------------------

    def _evaluate_at_horizon(
        self,
        experience: Experience,
        trajectory: UserTrajectory,
        horizon: TimeHorizon,
    ) -> HorizonAssessment:
        """Evaluate a single time horizon with whatever evidence exists."""

        if horizon == TimeHorizon.IMMEDIATE:
            return self._eval_immediate(experience)
        elif horizon == TimeHorizon.SHORT_TERM:
            return self._eval_short_term(experience)
        elif horizon == TimeHorizon.MEDIUM_TERM:
            return self._eval_medium_term(experience, trajectory)
        elif horizon == TimeHorizon.LONG_TERM:
            return self._eval_long_term(experience, trajectory)
        elif horizon == TimeHorizon.GENERATIONAL:
            return self._eval_generational(trajectory)
        return HorizonAssessment(horizon=horizon)

    def _eval_immediate(self, experience: Experience) -> HorizonAssessment:
        """t=0: we only have the user's rating and description.

        This is the *weakest* horizon -- high immediate scores mean
        very little on their own.
        """
        return HorizonAssessment(
            horizon=TimeHorizon.IMMEDIATE,
            score=experience.user_rating,
            evidence_count=1,
            notes="User's immediate self-report only; low weight.",
        )

    def _eval_short_term(self, experience: Experience) -> HorizonAssessment:
        """Hours to days: do we have any follow-up evidence?"""
        from datetime import timedelta

        short_follow_ups = [
            fu for fu in experience.follow_ups
            if (fu.timestamp - experience.timestamp) < timedelta(days=3)
        ]
        if not short_follow_ups:
            return HorizonAssessment(
                horizon=TimeHorizon.SHORT_TERM,
                score=None,
                notes="No short-term follow-up data yet.",
            )

        # Score based on creative output in the short term
        creation_count = sum(1 for f in short_follow_ups if f.created_something)
        share_count = sum(1 for f in short_follow_ups if f.shared_or_taught)
        inspired_count = sum(1 for f in short_follow_ups if f.inspired_further_action)
        n = len(short_follow_ups)

        score = (
            0.4 * (creation_count / n)
            + 0.3 * (share_count / n)
            + 0.3 * (inspired_count / n)
        )

        return HorizonAssessment(
            horizon=TimeHorizon.SHORT_TERM,
            score=score,
            evidence_count=n,
            notes=f"{creation_count} creation events, {share_count} shares in short term.",
        )

    def _eval_medium_term(
        self, experience: Experience, trajectory: UserTrajectory
    ) -> HorizonAssessment:
        """Weeks to months: look for pattern changes in the trajectory."""
        from datetime import timedelta

        medium_follow_ups = [
            fu for fu in experience.follow_ups
            if timedelta(days=3) <= (fu.timestamp - experience.timestamp) < timedelta(days=60)
        ]
        if not medium_follow_ups:
            return HorizonAssessment(
                horizon=TimeHorizon.MEDIUM_TERM,
                score=None,
                notes="No medium-term follow-up data yet.",
            )

        creation_count = sum(1 for f in medium_follow_ups if f.created_something)
        n = len(medium_follow_ups)
        creation_fraction = creation_count / n

        # Also factor in whether the trajectory vector shifted after this experience
        direction_shift = 0.0
        if len(trajectory.vector_history) >= 2:
            # Look at vector direction before and after this experience timestamp
            before = [v for v in trajectory.vector_history if v.timestamp <= experience.timestamp]
            after = [v for v in trajectory.vector_history if v.timestamp > experience.timestamp]
            if before and after:
                direction_shift = after[-1].direction - before[-1].direction

        # Positive direction shift + creation = high medium-term score
        score = 0.6 * creation_fraction + 0.4 * max(0.0, min(1.0, (direction_shift + 1.0) / 2.0))

        return HorizonAssessment(
            horizon=TimeHorizon.MEDIUM_TERM,
            score=score,
            evidence_count=n,
            notes=f"{creation_count}/{n} medium-term creation events; direction shift {direction_shift:+.2f}.",
        )

    def _eval_long_term(
        self, experience: Experience, trajectory: UserTrajectory
    ) -> HorizonAssessment:
        """Months to years: is the user's overall trajectory compounding?"""
        from datetime import timedelta

        long_follow_ups = [
            fu for fu in experience.follow_ups
            if (fu.timestamp - experience.timestamp) >= timedelta(days=60)
        ]
        if not long_follow_ups and trajectory.experience_count < 5:
            return HorizonAssessment(
                horizon=TimeHorizon.LONG_TERM,
                score=None,
                notes="Insufficient long-term data.",
            )

        # Use trajectory compounding as the primary signal
        compounding = trajectory.compounding_direction
        creation_rate = trajectory.creation_rate

        # Compounding toward creative + high creation rate = high long-term score
        score = (
            0.5 * max(0.0, min(1.0, (compounding + 1.0) / 2.0))
            + 0.5 * creation_rate
        )

        evidence_n = len(long_follow_ups) + trajectory.experience_count

        return HorizonAssessment(
            horizon=TimeHorizon.LONG_TERM,
            score=score,
            evidence_count=evidence_n,
            notes=f"Compounding direction {compounding:+.2f}; creation rate {creation_rate:.0%}.",
        )

    def _eval_generational(self, trajectory: UserTrajectory) -> HorizonAssessment:
        """Years to decades: ecosystem-level assessment.

        This horizon is almost never directly evaluable for an individual
        experience.  It represents the Jiro-level ecosystem question:
        is the broader network of quality flourishing?

        For now, this is always pending unless the trajectory is very
        mature with extensive history.
        """
        if trajectory.experience_count < 20:
            return HorizonAssessment(
                horizon=TimeHorizon.GENERATIONAL,
                score=None,
                notes="Generational horizon requires extensive history; pending.",
            )

        # With a long history, use the overall propagation rate
        # and compounding direction as a proxy for ecosystem health.
        score = (
            0.4 * trajectory.propagation_rate
            + 0.3 * trajectory.creation_rate
            + 0.3 * max(0.0, min(1.0, (trajectory.compounding_direction + 1.0) / 2.0))
        )

        return HorizonAssessment(
            horizon=TimeHorizon.GENERATIONAL,
            score=score,
            evidence_count=trajectory.experience_count,
            notes=f"Ecosystem proxy: propagation {trajectory.propagation_rate:.0%}, "
                  f"creation rate {trajectory.creation_rate:.0%}.",
        )
