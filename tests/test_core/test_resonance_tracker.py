"""Tests for ResonanceTracker -- evidence-aware resonance measurement.

Core principle: resonance at t=0 is the user's self-report (raw
signal), capped because self-report alone can't confirm depth.  Over
time, the signal is calibrated by action evidence: creation, sharing,
inspiration.  Depth of response (intensity) matters more than breadth
(reach).
"""

from datetime import datetime, timedelta

import pytest

from resonance_alignment.core.resonance_tracker import ResonanceTracker
from resonance_alignment.core.models import Experience, FollowUp


@pytest.fixture
def tracker():
    return ResonanceTracker()


class TestRawSignalCapture:
    """At t=0, resonance is the user's self-report, capped."""

    def test_returns_float_in_range(self, tracker):
        exp = Experience(
            user_id="user1",
            description="writing code",
            context="at home",
            user_rating=0.7,
        )
        score = tracker.measure_resonance(exp)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_t0_capped_at_ceiling(self, tracker):
        """High self-report at t=0 should be capped -- self-report
        alone can't confirm genuine resonance."""
        exp = Experience(user_rating=1.0, description="amazing experience")
        score = tracker.measure_resonance(exp)
        assert score <= tracker._T0_CEILING

    def test_t0_higher_rating_higher_score(self, tracker):
        """Higher self-report should still produce higher score at t=0."""
        exp_high = Experience(user_rating=0.9, description="great")
        exp_low = Experience(user_rating=0.2, description="meh")

        score_high = tracker.measure_resonance(exp_high)
        score_low = tracker.measure_resonance(exp_low)

        assert score_high > score_low

    def test_records_in_history(self, tracker):
        exp = Experience(
            user_id="user1",
            description="painting",
            context="studio",
            user_rating=0.6,
        )
        tracker.measure_resonance(exp)
        assert len(tracker.resonance_history) == 1
        assert tracker.resonance_history[0]["user_id"] == "user1"
        # History stores the ACTION, not identity data
        assert "action" in tracker.resonance_history[0]


class TestEvidenceAwareMeasurement:
    """With follow-ups, resonance incorporates action depth evidence."""

    def test_deep_follow_ups_raise_resonance(self, tracker):
        """Creation + sharing = deep resonance evidence → score rises."""
        base = datetime(2025, 1, 1)
        exp = Experience(
            user_rating=0.5,  # modest self-report
            description="attended a workshop",
            timestamp=base,
        )

        # Add deep follow-up
        exp.follow_ups.append(FollowUp(
            timestamp=base + timedelta(days=2),
            created_something=True,
            creation_description="Built a prototype",
            shared_or_taught=True,
            inspired_further_action=True,
        ))

        score = tracker.measure_resonance(exp)

        # Modest self-report + strong action = resonance rises
        assert score > 0.5

    def test_passive_follow_ups_lower_resonance(self, tracker):
        """Passive follow-ups (no action) bring resonance DOWN from
        self-report, because absence of action suggests the self-report
        was inflated (sugar hit)."""
        base = datetime(2025, 1, 1)
        exp = Experience(
            user_rating=0.9,  # high self-report
            description="watched a viral video",
            timestamp=base,
        )

        # Passive follow-up: nothing came of it
        exp.follow_ups.append(FollowUp(
            timestamp=base + timedelta(days=3),
            created_something=False,
            shared_or_taught=False,
            inspired_further_action=False,
        ))

        score = tracker.measure_resonance(exp)

        # High self-report + no action → discounted
        # Should be below what t=0 would give (which is capped at 0.6)
        assert score < 0.9  # definitely lower than raw self-report

    def test_depth_matters_not_count(self, tracker):
        """Few follow-ups all deeply engaged ≥ many passive follow-ups."""
        base = datetime(2025, 1, 1)

        # 2 deeply engaged follow-ups
        exp_deep = Experience(
            user_rating=0.6, description="deep", timestamp=base
        )
        for i in range(2):
            exp_deep.follow_ups.append(FollowUp(
                timestamp=base + timedelta(days=i + 1),
                created_something=True,
                creation_description=f"Creation {i}",
                shared_or_taught=True,
                inspired_further_action=True,
            ))

        # 10 passive follow-ups
        exp_shallow = Experience(
            user_rating=0.6, description="shallow", timestamp=base
        )
        for i in range(10):
            exp_shallow.follow_ups.append(FollowUp(
                timestamp=base + timedelta(days=i + 1),
                created_something=False,
                shared_or_taught=False,
                inspired_further_action=False,
            ))

        score_deep = tracker.measure_resonance(exp_deep)
        score_shallow = tracker.measure_resonance(exp_shallow)

        assert score_deep > score_shallow


class TestPrediction:
    """Prediction uses the individual's OWN action history only."""

    def test_predict_no_history(self, tracker):
        score = tracker.predict_resonance("user1", "running")
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_predict_with_own_history(self, tracker):
        """Prediction based on similar ACTIONS in own history."""
        exp = Experience(
            user_id="user1",
            description="writing poetry",
            context="home",
            user_rating=0.7,
        )
        tracker.measure_resonance(exp)

        score = tracker.predict_resonance("user1", "writing a short story")
        assert isinstance(score, float)

    def test_predict_does_not_cross_users(self, tracker):
        """One user's actions should not influence another's prediction."""
        for uid in ["user1", "user2"]:
            exp = Experience(
                user_id=uid,
                description="playing guitar",
                context="home",
                user_rating=0.7,
            )
            tracker.measure_resonance(exp)

        # user3 has no history -- should get neutral prediction
        score = tracker.predict_resonance("user3", "playing guitar")
        assert score == pytest.approx(0.5)


class TestLegacyAPI:
    """The legacy string-based API should still work."""

    def test_legacy_returns_float(self, tracker):
        score = tracker.measure_resonance_legacy("user1", "painting", "studio")
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0


class TestHelpers:
    def test_weighted_average(self, tracker):
        assert tracker._weighted_average([1.0, 0.0]) == pytest.approx(0.5)
        assert tracker._weighted_average([1.0, 1.0, 1.0]) == pytest.approx(1.0)
        assert tracker._weighted_average([0.0, 0.0]) == pytest.approx(0.0)
