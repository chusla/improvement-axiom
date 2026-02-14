"""Tests for the InMemoryStorage backend."""

import pytest
from datetime import timedelta, timezone, datetime

from resonance_alignment.storage.memory import InMemoryStorage
from resonance_alignment.core.models import (
    Experience,
    FollowUp,
    UserTrajectory,
    VectorSnapshot,
)


class TestTrajectoryPersistence:
    """InMemoryStorage should store and retrieve trajectories."""

    def test_save_and_load_trajectory(self):
        storage = InMemoryStorage()
        traj = UserTrajectory(user_id="user1")
        traj.creation_rate = 0.5
        traj.current_vector = VectorSnapshot(direction=0.3, magnitude=0.5, confidence=0.4)

        storage.save_trajectory(traj)
        loaded = storage.load_trajectory("user1")

        assert loaded is not None
        assert loaded.user_id == "user1"
        assert loaded.creation_rate == 0.5
        assert loaded.current_vector.direction == 0.3

    def test_load_nonexistent_returns_none(self):
        storage = InMemoryStorage()
        assert storage.load_trajectory("nonexistent") is None

    def test_list_user_ids(self):
        storage = InMemoryStorage()
        storage.save_trajectory(UserTrajectory(user_id="alice"))
        storage.save_trajectory(UserTrajectory(user_id="bob"))

        ids = storage.list_user_ids()
        assert set(ids) == {"alice", "bob"}

    def test_save_is_deep_copy(self):
        """Modifying the original should not affect stored data."""
        storage = InMemoryStorage()
        traj = UserTrajectory(user_id="user1")
        traj.creation_rate = 0.3

        storage.save_trajectory(traj)
        traj.creation_rate = 0.9  # modify original

        loaded = storage.load_trajectory("user1")
        assert loaded.creation_rate == 0.3  # should be unchanged

    def test_load_is_deep_copy(self):
        """Modifying a loaded trajectory should not affect storage."""
        storage = InMemoryStorage()
        storage.save_trajectory(UserTrajectory(user_id="user1"))

        loaded = storage.load_trajectory("user1")
        loaded.creation_rate = 0.99

        reloaded = storage.load_trajectory("user1")
        assert reloaded.creation_rate == 0.0  # default, not 0.99


class TestExperiencePersistence:

    def test_save_and_load_experience(self):
        storage = InMemoryStorage()
        storage.save_trajectory(UserTrajectory(user_id="user1"))

        exp = Experience(id="exp1", user_id="user1", description="test")
        storage.save_experience(exp)

        loaded = storage.load_experience("user1", "exp1")
        assert loaded is not None
        assert loaded.description == "test"

    def test_load_nonexistent_experience(self):
        storage = InMemoryStorage()
        storage.save_trajectory(UserTrajectory(user_id="user1"))
        assert storage.load_experience("user1", "nonexistent") is None


class TestFollowUpPersistence:

    def test_save_follow_up(self):
        storage = InMemoryStorage()
        traj = UserTrajectory(user_id="user1")
        exp = Experience(id="exp1", user_id="user1")
        traj.experiences.append(exp)
        storage.save_trajectory(traj)

        fu = FollowUp(
            id="fu1",
            content="created something",
            created_something=True,
            creation_magnitude=0.75,
        )
        storage.save_follow_up("user1", "exp1", fu)

        loaded_traj = storage.load_trajectory("user1")
        assert len(loaded_traj.experiences[0].follow_ups) == 1
        assert loaded_traj.experiences[0].follow_ups[0].creation_magnitude == 0.75


class TestVectorTrackerWithStorage:
    """VectorTracker should use storage when provided."""

    def test_tracker_persists_to_storage(self):
        from resonance_alignment.core.vector_tracker import VectorTracker

        storage = InMemoryStorage()
        tracker = VectorTracker(storage=storage)

        tracker.record_experience("user1", "played chess", "", 0.8)

        # Storage should have the trajectory now
        loaded = storage.load_trajectory("user1")
        assert loaded is not None
        assert loaded.experience_count == 1

    def test_tracker_loads_from_storage(self):
        from resonance_alignment.core.vector_tracker import VectorTracker

        # Pre-populate storage
        storage = InMemoryStorage()
        traj = UserTrajectory(user_id="user1")
        exp = Experience(id="exp_old", user_id="user1", description="old experience")
        exp.propagated = True
        traj.experiences.append(exp)
        traj.creation_rate = 0.5
        storage.save_trajectory(traj)

        # New tracker should load existing history
        tracker = VectorTracker(storage=storage)
        loaded_traj = tracker.get_trajectory("user1")

        # First access triggers load
        tracker.record_experience("user1", "new experience", "", 0.7)
        loaded_traj = tracker.get_trajectory("user1")

        assert loaded_traj is not None
        assert loaded_traj.experience_count == 2  # old + new

    def test_tracker_works_without_storage(self):
        """Backward compatibility: tracker works fine with storage=None."""
        from resonance_alignment.core.vector_tracker import VectorTracker

        tracker = VectorTracker()  # no storage
        tracker.record_experience("user1", "did something", "", 0.5)

        traj = tracker.get_trajectory("user1")
        assert traj is not None
        assert traj.experience_count == 1
