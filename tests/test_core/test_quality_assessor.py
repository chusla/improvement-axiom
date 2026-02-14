"""Tests for QualityAssessor -- signal depth based quality measurement.

Core principle under test: quality is measured by DEPTH of response
(intensity, devotion, return engagement) not BREADTH of reach
(virality, audience size).  A craftsman with 5 devoted local fans
carries the same quality signal as a platform with millions.
"""

from datetime import datetime, timedelta

import pytest

from resonance_alignment.core.quality_assessor import QualityAssessor
from resonance_alignment.core.models import (
    Experience,
    FollowUp,
    UserTrajectory,
)


@pytest.fixture
def assessor():
    return QualityAssessor()


class TestBasicContract:
    """The assessor must always return a score and all dimensions."""

    def test_returns_score_and_dimensions(self, assessor):
        exp = Experience(user_rating=0.8, description="writing a novel")
        score, dims = assessor.assess_quality(exp)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
        assert set(dims.keys()) == set(assessor.DIMENSIONS)

    def test_all_dimension_scores_bounded(self, assessor):
        exp = Experience(user_rating=0.6)
        _, dims = assessor.assess_quality(exp)
        for dim, val in dims.items():
            assert 0.0 <= val <= 1.0, f"{dim} out of bounds: {val}"

    def test_weights_sum_to_one(self, assessor):
        total = sum(assessor.DEFAULT_WEIGHTS.values())
        assert abs(total - 1.0) < 0.01


class TestSignalDepthOverBreadth:
    """Signal depth must be the highest-weighted dimension and must
    measure INTENSITY (rate) not REACH (count)."""

    def test_signal_depth_has_highest_weight(self, assessor):
        max_dim = max(
            assessor.DEFAULT_WEIGHTS, key=assessor.DEFAULT_WEIGHTS.get
        )
        assert max_dim == "signal_depth"

    def test_t0_quality_is_capped_by_self_report(self, assessor):
        """At t=0 with no follow-ups, quality should be modest --
        self-report alone can't confirm depth."""
        exp_high = Experience(user_rating=1.0)
        exp_low = Experience(user_rating=0.2)

        score_high, _ = assessor.assess_quality(exp_high)
        score_low, _ = assessor.assess_quality(exp_low)

        # High self-report still can't exceed a modest ceiling at t=0
        assert score_high < 0.50
        # But higher self-report should still score higher than low
        assert score_high > score_low

    def test_deep_follow_ups_raise_quality(self, assessor):
        """Follow-ups with creation + sharing = deep signal → higher quality."""
        base = datetime(2025, 1, 1)
        exp = Experience(user_rating=0.7, timestamp=base)

        # No follow-ups: baseline
        score_before, _ = assessor.assess_quality(exp)

        # Add deep follow-up: created, shared, inspired
        exp.follow_ups.append(FollowUp(
            timestamp=base + timedelta(days=2),
            created_something=True,
            creation_description="Built a project inspired by this",
            shared_or_taught=True,
            inspired_further_action=True,
        ))

        score_after, dims = assessor.assess_quality(exp)

        assert score_after > score_before
        assert dims["signal_depth"] > 0.5

    def test_shallow_follow_ups_do_not_inflate(self, assessor):
        """Follow-ups with no action = shallow.  Quality should NOT rise."""
        base = datetime(2025, 1, 1)
        exp = Experience(user_rating=0.7, timestamp=base)

        # Add passive follow-ups (no creation, no sharing, no inspiration)
        for i in range(5):
            exp.follow_ups.append(FollowUp(
                timestamp=base + timedelta(days=i + 1),
                created_something=False,
                shared_or_taught=False,
                inspired_further_action=False,
            ))

        score, dims = assessor.assess_quality(exp)

        # Signal depth should be very low despite many follow-ups
        assert dims["signal_depth"] < 0.3
        # Overall quality should not be inflated by passive consumption
        assert score < 0.40


class TestLocalizedContext:
    """A craftsman with a few devoted local fans has the same quality
    signal as a platform with millions -- depth over breadth."""

    def test_few_devoted_equals_quality(self, assessor):
        """3 follow-ups, all deeply engaged → high quality."""
        base = datetime(2025, 1, 1)
        exp = Experience(user_rating=0.8, timestamp=base)

        # 3 "devoted fans" -- each created AND shared
        for i in range(3):
            exp.follow_ups.append(FollowUp(
                timestamp=base + timedelta(days=i + 1),
                created_something=True,
                creation_description=f"Creation #{i+1}",
                shared_or_taught=True,
                inspired_further_action=True,
            ))

        score, dims = assessor.assess_quality(exp)
        assert score > 0.55
        assert dims["signal_depth"] > 0.7

    def test_many_passive_is_not_quality(self, assessor):
        """20 follow-ups, all passive → low quality despite volume."""
        base = datetime(2025, 1, 1)
        exp = Experience(user_rating=0.6, timestamp=base)

        for i in range(20):
            exp.follow_ups.append(FollowUp(
                timestamp=base + timedelta(days=i + 1),
                created_something=False,
                shared_or_taught=False,
                inspired_further_action=False,
            ))

        score, dims = assessor.assess_quality(exp)
        assert dims["signal_depth"] < 0.2
        assert score < 0.35


class TestRecursiveness:
    """Quality layers compounding -- multiple creations, shared
    creations flowing through layers."""

    def test_no_follow_ups_zero_recursiveness(self, assessor):
        exp = Experience(user_rating=0.8)
        _, dims = assessor.assess_quality(exp)
        assert dims["recursiveness"] == 0.0

    def test_single_creation_base_recursiveness(self, assessor):
        base = datetime(2025, 1, 1)
        exp = Experience(user_rating=0.7, timestamp=base)
        exp.follow_ups.append(FollowUp(
            timestamp=base + timedelta(days=1),
            created_something=True,
            creation_description="A painting",
        ))

        _, dims = assessor.assess_quality(exp)
        assert 0.2 <= dims["recursiveness"] <= 0.5

    def test_multiple_creations_higher_recursiveness(self, assessor):
        base = datetime(2025, 1, 1)
        exp = Experience(user_rating=0.7, timestamp=base)

        for i in range(4):
            exp.follow_ups.append(FollowUp(
                timestamp=base + timedelta(days=i + 1),
                created_something=True,
                creation_description=f"Creation #{i+1}",
                shared_or_taught=(i % 2 == 0),
                inspired_further_action=(i > 1),
            ))

        _, dims = assessor.assess_quality(exp)
        assert dims["recursiveness"] > 0.6


class TestDurability:
    """Genuine quality persists across time horizons.  Sugar hits collapse."""

    def test_short_term_only_capped(self, assessor):
        """Only short-term evidence → durability ceiling."""
        base = datetime(2025, 1, 1)
        exp = Experience(user_rating=0.9, timestamp=base)
        exp.follow_ups.append(FollowUp(
            timestamp=base + timedelta(hours=12),
            created_something=True,
            creation_description="Quick sketch",
        ))

        _, dims = assessor.assess_quality(exp)
        # Only short-term data → modest ceiling
        assert dims["durability"] <= 0.50

    def test_long_term_evidence_high_durability(self, assessor):
        """Evidence across all temporal buckets → high durability."""
        base = datetime(2025, 1, 1)
        exp = Experience(user_rating=0.7, timestamp=base)

        # Short-term
        exp.follow_ups.append(FollowUp(
            timestamp=base + timedelta(days=1),
            created_something=True,
            creation_description="Immediate creation",
        ))
        # Medium-term
        exp.follow_ups.append(FollowUp(
            timestamp=base + timedelta(days=30),
            created_something=True,
            creation_description="Month-later creation",
            shared_or_taught=True,
        ))
        # Long-term
        exp.follow_ups.append(FollowUp(
            timestamp=base + timedelta(days=120),
            created_something=True,
            creation_description="Quarterly creation",
            inspired_further_action=True,
        ))

        _, dims = assessor.assess_quality(exp)
        assert dims["durability"] > 0.6


class TestAuthenticity:
    """Authentic quality: self-report aligned with action evidence.
    Spike-crash pattern: high self-report, no follow-through."""

    def test_high_report_plus_action_is_authentic(self, assessor):
        base = datetime(2025, 1, 1)
        exp = Experience(user_rating=0.9, timestamp=base)
        exp.follow_ups.append(FollowUp(
            timestamp=base + timedelta(days=1),
            created_something=True,
            creation_description="Built something",
            shared_or_taught=True,
        ))

        _, dims = assessor.assess_quality(exp)
        assert dims["authenticity"] > 0.5

    def test_high_report_no_action_is_spike_crash(self, assessor):
        base = datetime(2025, 1, 1)
        exp = Experience(user_rating=0.9, timestamp=base)
        # High rating but nothing came of it
        exp.follow_ups.append(FollowUp(
            timestamp=base + timedelta(days=3),
            created_something=False,
            shared_or_taught=False,
            inspired_further_action=False,
        ))

        _, dims = assessor.assess_quality(exp)
        assert dims["authenticity"] < 0.45


class TestGrowthEnabling:
    """Does the experience raise the floor for future quality?"""

    def test_no_trajectory_weak_proxy(self, assessor):
        exp = Experience(user_rating=0.6)
        _, dims = assessor.assess_quality(exp, trajectory=None)
        assert 0.0 <= dims["growth_enabling"] <= 0.3

    def test_trajectory_shows_improvement(self, assessor):
        """Experiences after the target show higher creation rate →
        growth-enabling."""
        base = datetime(2025, 1, 1)
        target = Experience(
            id="target",
            user_rating=0.7,
            timestamp=base + timedelta(days=5),
        )

        # Before: mostly passive
        before = [
            Experience(
                id=f"b{i}",
                timestamp=base + timedelta(days=i),
                propagated=False,
            )
            for i in range(5)
        ]

        # After: mostly creative
        after = [
            Experience(
                id=f"a{i}",
                timestamp=base + timedelta(days=6 + i),
                propagated=True,
            )
            for i in range(5)
        ]

        traj = UserTrajectory(
            experiences=before + [target] + after,
        )

        _, dims = assessor.assess_quality(target, trajectory=traj)
        assert dims["growth_enabling"] > 0.5
