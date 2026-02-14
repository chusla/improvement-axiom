"""Tests for the trajectory-based OuroborosAnchor."""

import pytest

from resonance_alignment.safety.ouroboros_anchor import OuroborosAnchor
from resonance_alignment.core.models import (
    Experience,
    FollowUp,
    IntentionSignal,
    UserTrajectory,
    VectorSnapshot,
)


class TestClassificationDriftDetection:
    """Drift = when the label diverges from what evidence actually shows."""

    def test_low_confidence_skips_drift_check(self):
        anchor = OuroborosAnchor()
        exp = Experience(
            provisional_intention=IntentionSignal.CREATIVE_INTENT,
            intention_confidence=0.1,  # too low to check
        )
        traj = UserTrajectory()

        valid, msg = anchor.validate_classification(exp, traj)
        assert valid is True
        assert "provisional" in msg.lower()

    def test_creative_label_with_no_creative_evidence_is_drift(self):
        """If labelled creative but follow-ups show no creation → drift."""
        anchor = OuroborosAnchor()
        exp = Experience(
            provisional_intention=IntentionSignal.CREATIVE_INTENT,
            intention_confidence=0.6,
        )
        # Follow-ups show NO creative output
        exp.follow_ups = [
            FollowUp(created_something=False, shared_or_taught=False, inspired_further_action=False),
            FollowUp(created_something=False, shared_or_taught=False, inspired_further_action=False),
        ]
        traj = UserTrajectory()

        valid, msg = anchor.validate_classification(exp, traj)
        assert valid is False
        assert "drift" in msg.lower()

    def test_creative_label_with_creative_evidence_is_valid(self):
        anchor = OuroborosAnchor()
        exp = Experience(
            provisional_intention=IntentionSignal.CREATIVE_INTENT,
            intention_confidence=0.6,
        )
        exp.follow_ups = [
            FollowUp(created_something=True, shared_or_taught=True, inspired_further_action=True),
        ]
        traj = UserTrajectory()

        valid, msg = anchor.validate_classification(exp, traj)
        assert valid is True


class TestOuroborosHealthCheck:
    """Checks whether the creation/consumption cycle is sustainable."""

    def test_insufficient_history(self):
        anchor = OuroborosAnchor()
        traj = UserTrajectory(experiences=[Experience()])

        healthy, msg = anchor.check_ouroboros_health(traj)
        assert healthy is True  # not enough data to judge

    def test_healthy_cycle(self):
        anchor = OuroborosAnchor()
        traj = UserTrajectory()
        traj.creation_rate = 0.6
        traj.compounding_direction = 0.1
        traj.experiences = [Experience() for _ in range(10)]

        healthy, msg = anchor.check_ouroboros_health(traj)
        assert healthy is True
        assert "healthy" in msg.lower()

    def test_unhealthy_sustained_consumption(self):
        anchor = OuroborosAnchor()
        traj = UserTrajectory()
        traj.creation_rate = 0.05  # very low

        # 5 consecutive consumptive experiences with sufficient confidence
        for _ in range(5):
            exp = Experience(
                provisional_intention=IntentionSignal.CONSUMPTIVE_INTENT,
                intention_confidence=0.5,
            )
            traj.experiences.append(exp)

        healthy, msg = anchor.check_ouroboros_health(traj)
        assert healthy is False
        assert "consumptive-intent" in msg.lower() or "input-focused" in msg.lower()


class TestNaturalPattern:
    """Retained test for explicit action/outcome pair checking."""

    def test_more_created_than_consumed(self):
        anchor = OuroborosAnchor()
        valid, _ = anchor.verify_natural_pattern(
            {"required_consumption": 0.3},
            {"contains_creation": True, "creation_value": 0.8},
        )
        assert valid is True

    def test_consumption_without_creation(self):
        anchor = OuroborosAnchor()
        valid, _ = anchor.verify_natural_pattern(
            {"required_consumption": 0.5},
            {"contains_creation": False},
        )
        assert valid is False
