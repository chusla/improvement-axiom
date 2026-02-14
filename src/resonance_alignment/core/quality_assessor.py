"""Multi-dimensional quality assessment through observable signal depth.

Quality is measured by DEPTH of response, not BREADTH of reach.

A master craftsman with 50 devoted local clients who return year after
year, leave 5-star reviews, and refer friends carries a *stronger*
quality signal than a viral post with millions of shallow likes.  The
framework must never become another engagement-maximiser where the
"big get bigger".

Core principle: signal INTENSITY over signal REACH.

The NPS (Net Promoter Score) concept applies perfectly: not "how many
people rated you" but "how strongly do the people who experienced you
feel?"  Were they moved to act -- to create, share, teach, return?

Quality and resonance are two sides of the same coin.  Quality is the
objective signal (what the experience produces); resonance is the
subjective experience of it (what the individual feels).  Both converge
over the long arc through the same observable evidence, evaluated across
the 5-level temporal structure.

Localized / niche contexts are FIRST CLASS.  A boutique sushi bar with
a devoted following in one neighbourhood has the same quality standing
as a Michelin-starred restaurant with global press.  In many cases the
former is the precursor to the latter -- organic expansion from deep
local roots is the *healthy* pattern.

ANTI-VIRALITY PROTECTION:
- Breadth without depth is a WARNING, not a positive.
- Signal depth is measured by RATE of strong responses, not COUNT.
- 90% of 20 people deeply moved > 0.1% of 1,000,000 who clicked "like".
"""

from __future__ import annotations

import statistics
from datetime import timedelta

from resonance_alignment.core.models import (
    Experience,
    FollowUp,
    UserTrajectory,
)


class QualityAssessor:
    """Measures quality through signal depth and recursiveness.

    Five observable dimensions, each measurable across temporal horizons:

    1. Signal Depth (0.35) -- How INTENSELY does the receiver respond?
       Not how many people, but how deeply each one is moved.
       Five-star ratings from avid followers of a local craftsman
       are a stronger signal than broad shallow engagement.

    2. Recursiveness (0.20) -- Do quality layers compound?
       Sushi restaurant: knife artisan → fisherman → rice purveyor →
       vinegar crafter → chef.  Layers of quality feeding each other.
       Measured by depth, not by scale.

    3. Durability (0.20) -- Does the signal persist across time?
       Loyal repeat customers, still-referenced work months later.
       Sugar hits collapse; genuine quality endures.

    4. Growth-Enabling (0.15) -- Does it raise subsequent quality?
       Each creation builds on the last, raising the floor.

    5. Authenticity (0.10) -- Consistent pattern, not spike-crash?
       Steady devoted following > viral moment that vanishes.

    At t=0 with no follow-ups, quality assessment relies on the user's
    self-report (weakest signal).  As follow-ups accumulate, the
    dimensions gain real data.
    """

    DIMENSIONS = [
        "signal_depth",
        "recursiveness",
        "durability",
        "growth_enabling",
        "authenticity",
    ]

    DEFAULT_WEIGHTS = {
        "signal_depth": 0.35,      # Highest: depth of response is king
        "recursiveness": 0.20,     # Quality layers compounding
        "durability": 0.20,        # Persistence across time
        "growth_enabling": 0.15,   # Raises future quality floor
        "authenticity": 0.10,      # Consistent vs spike-crash
    }

    def assess_quality(
        self,
        experience: Experience,
        trajectory: UserTrajectory | None = None,
    ) -> tuple[float, dict[str, float]]:
        """Run multi-dimensional quality assessment.

        Uses follow-up evidence and trajectory history when available.
        At t=0, falls back to user's self-report as a weak prior.

        Args:
            experience: The experience with its accumulated evidence.
            trajectory: The user's full trajectory for growth analysis.

        Returns:
            Tuple of (quality_score, dimension_scores).
        """
        dimensions = {
            "signal_depth": self._measure_signal_depth(experience),
            "recursiveness": self._measure_recursiveness(experience),
            "durability": self._measure_durability(experience),
            "growth_enabling": self._measure_growth_enabling(
                experience, trajectory
            ),
            "authenticity": self._measure_authenticity(
                experience, trajectory
            ),
        }

        quality_score = sum(
            score * self.DEFAULT_WEIGHTS[dim]
            for dim, score in dimensions.items()
        )

        return quality_score, dimensions

    # ------------------------------------------------------------------
    # Dimension measurements
    # ------------------------------------------------------------------

    def _measure_signal_depth(self, experience: Experience) -> float:
        """How INTENSELY does the receiver respond?

        This is the NPS of quality: not 'how many people saw it' but
        'were you moved to act on it -- create, share, teach, return?'

        Depth indicators (all measured by RATE, not count):
        - Fraction of follow-ups with active signals (created/shared/inspired)
        - Breadth of response types (created AND shared AND inspired > just one)
        - Speed of response (faster = more visceral = deeper signal)

        At t=0 with no follow-ups: user_rating as a weak proxy.
        """
        if not experience.follow_ups:
            # Only have self-report.  Cap ceiling -- self-report alone
            # can't confirm depth.
            return experience.user_rating * 0.4

        total = len(experience.follow_ups)

        # --- Intensity rate (what FRACTION responded deeply?) ---
        # This is the anti-virality measure: rate, not count.
        created = sum(1 for f in experience.follow_ups if f.created_something)
        shared = sum(1 for f in experience.follow_ups if f.shared_or_taught)
        inspired = sum(
            1 for f in experience.follow_ups if f.inspired_further_action
        )

        any_active = sum(
            1 for f in experience.follow_ups
            if f.created_something or f.shared_or_taught
            or f.inspired_further_action
        )
        intensity_rate = any_active / total

        # --- Response breadth (multiple types = deeper engagement) ---
        # Created + shared + inspired together is much stronger than any alone.
        breadth = 0.0
        if created > 0:
            breadth += 0.4
        if shared > 0:
            breadth += 0.3
        if inspired > 0:
            breadth += 0.3

        # --- Speed of response (visceral depth) ---
        speed = self._compute_response_speed(experience)

        # Combine: intensity rate is primary (depth, not reach)
        score = (
            0.55 * intensity_rate
            + 0.25 * breadth
            + 0.20 * speed
        )

        return max(0.0, min(1.0, score))

    def _measure_recursiveness(self, experience: Experience) -> float:
        """Do quality layers compound on each other?

        The sushi restaurant: knife artisan → fisherman → rice purveyor
        → vinegar crafter → chef.  Each layer of quality feeds the next.

        Measured by DEPTH of layering, not SCALE of distribution:
        - Multiple distinct creation events from one experience
        - Creation that itself was shared/taught (flowing through layers)
        - Follow-up inspiration leading to further distinct action

        At t=0: not measurable.  Returns 0.
        """
        if not experience.follow_ups:
            return 0.0

        creation_events = [
            f for f in experience.follow_ups if f.created_something
        ]
        if not creation_events:
            return 0.0

        n_creations = len(creation_events)

        # Single creation = base recursiveness
        base = 0.3

        # Additional DISTINCT creations show deeper layering
        # (capped: we care about depth, not volume)
        additional = min((n_creations - 1) * 0.15, 0.35)

        # Creation that was ALSO shared/taught = flowing through layers
        shared_creations = sum(
            1 for f in experience.follow_ups
            if f.created_something and f.shared_or_taught
        )
        layer_flow = min(shared_creations * 0.15, 0.25)

        # Inspiration leading to further action = recursive seed
        inspired_after_creation = sum(
            1 for f in experience.follow_ups
            if f.inspired_further_action and f.created_something
        )
        recursive_seed = min(inspired_after_creation * 0.1, 0.2)

        return max(0.0, min(1.0, base + additional + layer_flow + recursive_seed))

    def _measure_durability(self, experience: Experience) -> float:
        """Does the quality signal persist as time horizons expand?

        Loyal repeat customers, work still referenced months later,
        a craftsman whose clients return year after year.  Sugar hits
        collapse; genuine quality endures and often deepens.

        Measured by the RATE of active signals at each temporal bucket
        (not the count -- a local craftsman with 3 devoted long-term
        clients scores the same as a platform with 3000).

        At t=0: only user's immediate self-report.
        """
        if not experience.follow_ups:
            # Immediate self-report.  Very weak durability signal.
            return experience.user_rating * 0.3

        # Bucket follow-ups by temporal distance
        short = [
            f for f in experience.follow_ups
            if (f.timestamp - experience.timestamp) < timedelta(days=3)
        ]
        medium = [
            f for f in experience.follow_ups
            if timedelta(days=3)
            <= (f.timestamp - experience.timestamp)
            < timedelta(days=60)
        ]
        long = [
            f for f in experience.follow_ups
            if (f.timestamp - experience.timestamp) >= timedelta(days=60)
        ]

        def bucket_active_rate(bucket: list[FollowUp]) -> float | None:
            """Rate of active signals in bucket.  None if bucket empty."""
            if not bucket:
                return None
            active = sum(
                1 for f in bucket
                if f.created_something or f.shared_or_taught
                or f.inspired_further_action
            )
            return active / len(bucket)

        short_rate = bucket_active_rate(short)
        medium_rate = bucket_active_rate(medium)
        long_rate = bucket_active_rate(long)

        # Weight later horizons more heavily (durability = persistence)
        # But only use buckets that have data.
        weighted_sum = 0.0
        total_weight = 0.0

        if short_rate is not None:
            weighted_sum += 0.20 * short_rate
            total_weight += 0.20
        if medium_rate is not None:
            weighted_sum += 0.35 * medium_rate
            total_weight += 0.35
        if long_rate is not None:
            weighted_sum += 0.45 * long_rate
            total_weight += 0.45

        if total_weight < 1e-9:
            return 0.0

        # Normalize by available weight, but apply a ceiling if only
        # short-term data exists (can't confirm durability from hours).
        raw = weighted_sum / total_weight

        if medium_rate is None and long_rate is None:
            # Only short-term evidence -- modest ceiling
            return min(raw, 0.45)

        return max(0.0, min(1.0, raw))

    def _measure_growth_enabling(
        self,
        experience: Experience,
        trajectory: UserTrajectory | None = None,
    ) -> float:
        """Does this experience raise the quality of subsequent creations?

        Growth-enabling quality compounds: each creation builds on the
        last, raising the floor.  Observable through whether the user's
        trajectory shows increased creation after this experience.

        At t=0 or without trajectory: not measurable.
        """
        if trajectory is None or trajectory.experience_count < 2:
            return experience.user_rating * 0.2  # weak proxy

        # Find this experience's position in the trajectory
        exp_index = None
        for i, e in enumerate(trajectory.experiences):
            if e.id == experience.id:
                exp_index = i
                break

        if exp_index is None or exp_index >= trajectory.experience_count - 1:
            return experience.user_rating * 0.2

        # Compare creation rates before and after this experience
        before = trajectory.experiences[:exp_index]
        after = trajectory.experiences[exp_index + 1:]

        if not before or not after:
            return experience.user_rating * 0.2

        before_creation_rate = (
            sum(1 for e in before if e.propagated) / len(before)
        )
        after_creation_rate = (
            sum(1 for e in after if e.propagated) / len(after)
        )

        # Positive shift = this experience was growth-enabling
        growth_delta = after_creation_rate - before_creation_rate

        # Also check vector direction improvement
        direction_improvement = 0.0
        if len(trajectory.vector_history) >= 2:
            recent = trajectory.vector_history[-1].direction
            if 0 < exp_index < len(trajectory.vector_history):
                earlier = trajectory.vector_history[
                    max(0, exp_index - 1)
                ].direction
                direction_improvement = recent - earlier

        score = (
            0.6 * max(0.0, min(1.0, growth_delta + 0.5))  # centre at 0.5
            + 0.4 * max(0.0, min(1.0, (direction_improvement + 1.0) / 2.0))
        )

        return max(0.0, min(1.0, score))

    def _measure_authenticity(
        self,
        experience: Experience,
        trajectory: UserTrajectory | None = None,
    ) -> float:
        """Is the signal pattern steady/growing, not spike-crash?

        Authentic quality: a devoted local following that grows
        organically over time.  Manufactured quality: a viral spike
        followed by rapid disinterest.

        Observable through:
        - Self-report alignment with action evidence
        - Trajectory consistency (low quality-score variance)
        - Absence of the spike-crash pattern

        At t=0: not measurable.
        """
        if not experience.follow_ups:
            return experience.user_rating * 0.3

        n = len(experience.follow_ups)
        any_action = sum(
            1 for f in experience.follow_ups
            if f.created_something or f.shared_or_taught
            or f.inspired_further_action
        )
        action_rate = any_action / n

        # Alignment: self-report vs. action evidence
        if experience.user_rating > 0.7:
            if action_rate > 0.5:
                alignment = 0.9  # high report + high action = authentic
            else:
                alignment = 0.3  # high report + low action = spike-crash
        elif experience.user_rating > 0.4:
            alignment = 0.5 + action_rate * 0.3
        else:
            if action_rate > 0.3:
                alignment = 0.8  # low self-report but still acted = very authentic
            else:
                alignment = 0.4  # low report + low action = honest low quality

        # Trajectory consistency if available
        trajectory_consistency = 0.5
        if trajectory and trajectory.experience_count >= 3:
            recent_qualities = [
                e.quality_score for e in trajectory.experiences[-5:]
                if e.quality_score > 0
            ]
            if len(recent_qualities) >= 2:
                try:
                    stdev = statistics.stdev(recent_qualities)
                    # Lower variance = more consistent = more authentic
                    trajectory_consistency = max(0.0, 1.0 - stdev * 2.0)
                except statistics.StatisticsError:
                    pass

        score = 0.6 * alignment + 0.4 * trajectory_consistency
        return max(0.0, min(1.0, score))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_response_speed(experience: Experience) -> float:
        """How quickly did a deep response happen?

        Faster visceral response = deeper signal.  But this measures
        the speed of the FIRST active response, not the count.

        Returns 0-1: 1.0 = immediate action, 0.0 = no action.
        """
        active_follow_ups = [
            f for f in experience.follow_ups
            if f.created_something or f.shared_or_taught
            or f.inspired_further_action
        ]

        if not active_follow_ups:
            return 0.0

        earliest = min(active_follow_ups, key=lambda f: f.timestamp)
        delay = earliest.timestamp - experience.timestamp

        if delay < timedelta(hours=6):
            return 1.0
        elif delay < timedelta(days=1):
            return 0.85
        elif delay < timedelta(days=3):
            return 0.7
        elif delay < timedelta(days=7):
            return 0.55
        elif delay < timedelta(days=30):
            return 0.4
        return 0.2
