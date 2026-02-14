"""Tests for VectorTracker -- the heart of the vector-based architecture."""

import pytest
from datetime import datetime, timedelta, timezone

from resonance_alignment.core.vector_tracker import VectorTracker
from resonance_alignment.core.models import FollowUp, IntentionSignal


class TestRecordExperience:
    """Recording a new experience should produce a PROVISIONAL assessment."""

    def test_first_experience_is_pending(self):
        """With no history, classification should be PENDING with near-zero confidence."""
        tracker = VectorTracker()
        exp = tracker.record_experience("user1", "watched anime for 6 hours", "", 0.7)

        assert exp.provisional_intention == IntentionSignal.MIXED  # near-zero direction → mixed
        assert exp.intention_confidence < 0.10  # very low confidence
        assert len(exp.vector_snapshots) == 1

    def test_same_activity_different_users_start_equal(self):
        """Two users doing the exact same thing should be indistinguishable at t=0."""
        tracker = VectorTracker()
        exp_a = tracker.record_experience("kid_a", "played minecraft for 3 hours", "", 0.8)
        exp_b = tracker.record_experience("kid_b", "played minecraft for 3 hours", "", 0.8)

        # Both should have essentially the same provisional assessment
        assert exp_a.provisional_intention == exp_b.provisional_intention
        assert abs(exp_a.intention_confidence - exp_b.intention_confidence) < 0.01


class TestFollowUpRevealsVector:
    """The vector should diverge based on what happens AFTER the experience."""

    def test_creation_follow_up_shifts_toward_creative(self):
        """If a user creates something after an experience, the vector shifts creative."""
        tracker = VectorTracker()
        exp = tracker.record_experience("user1", "binge watched anime series", "", 0.7)
        initial_direction = exp.vector_snapshots[-1].direction
        initial_confidence = exp.intention_confidence  # capture before mutation

        # A week later, user started writing their own anime fan fiction
        follow_up = FollowUp(
            timestamp=exp.timestamp + timedelta(days=7),
            source="user_response",
            content="Started writing my own story inspired by the series",
            created_something=True,
            creation_description="Anime fan fiction / original story",
            inspired_further_action=True,
        )
        updated = tracker.record_follow_up("user1", exp.id, follow_up)

        assert updated is not None
        assert updated.vector_snapshots[-1].direction > initial_direction
        assert updated.intention_confidence >= initial_confidence
        assert updated.propagated is True

    def test_no_creation_follow_up_leans_consumptive(self):
        """If nothing comes out of an experience, the vector leans consumptive."""
        tracker = VectorTracker()
        exp = tracker.record_experience("user2", "binge watched anime series", "", 0.7)

        # A week later, nothing happened -- just wanted more of the same
        follow_up = FollowUp(
            timestamp=exp.timestamp + timedelta(days=7),
            source="user_response",
            content="Just started watching another series",
            created_something=False,
            shared_or_taught=False,
            inspired_further_action=False,
        )
        updated = tracker.record_follow_up("user2", exp.id, follow_up)

        assert updated is not None
        assert updated.vector_snapshots[-1].direction < 0  # leans consumptive
        assert updated.propagated is False

    def test_same_activity_diverges_with_different_follow_ups(self):
        """Two users with identical experiences diverge based on follow-ups.

        This is the core test: video game kid A just consumes more,
        video game kid B starts experimenting with Scratch.
        """
        tracker = VectorTracker()

        # Same initial experience
        exp_a = tracker.record_experience("kid_a", "played video games all weekend", "", 0.8)
        exp_b = tracker.record_experience("kid_b", "played video games all weekend", "", 0.8)

        # Kid A: just consumed more
        tracker.record_follow_up("kid_a", exp_a.id, FollowUp(
            timestamp=exp_a.timestamp + timedelta(days=7),
            content="Played more games",
            created_something=False,
        ))

        # Kid B: started experimenting with game dev
        tracker.record_follow_up("kid_b", exp_b.id, FollowUp(
            timestamp=exp_b.timestamp + timedelta(days=7),
            content="Started learning Scratch to make my own game",
            created_something=True,
            creation_description="First Scratch project",
            inspired_further_action=True,
        ))

        traj_a = tracker.get_trajectory("kid_a")
        traj_b = tracker.get_trajectory("kid_b")

        # Vectors should have diverged
        assert traj_a.current_vector.direction < traj_b.current_vector.direction
        assert traj_b.creation_rate > traj_a.creation_rate


class TestTrajectoryCompounding:
    """Over time, small directional differences should compound."""

    def test_consistent_creation_compounds(self):
        """Multiple experiences followed by creation should compound the creative vector."""
        tracker = VectorTracker()

        for i in range(5):
            ts = datetime.now(timezone.utc) + timedelta(days=i * 7)
            exp = tracker.record_experience(
                "creator", f"experience {i}", "", 0.7, timestamp=ts,
            )
            tracker.record_follow_up("creator", exp.id, FollowUp(
                timestamp=ts + timedelta(days=3),
                content=f"Created something from experience {i}",
                created_something=True,
                creation_description=f"Project {i}",
            ))

        traj = tracker.get_trajectory("creator")
        assert traj.current_vector.direction > 0.3  # solidly creative
        assert traj.creation_rate > 0.5

    def test_consistent_consumption_compounds(self):
        """Multiple experiences with no creative output compound consumptive."""
        tracker = VectorTracker()

        for i in range(5):
            ts = datetime.now(timezone.utc) + timedelta(days=i * 7)
            exp = tracker.record_experience(
                "consumer", f"experience {i}", "", 0.5, timestamp=ts,
            )
            tracker.record_follow_up("consumer", exp.id, FollowUp(
                timestamp=ts + timedelta(days=3),
                content="Nothing came of it",
                created_something=False,
            ))

        traj = tracker.get_trajectory("consumer")
        assert traj.current_vector.direction < 0  # leans consumptive
        assert traj.creation_rate == 0.0
