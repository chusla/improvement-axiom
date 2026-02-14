"""In-memory storage backend -- current behavior, no persistence.

This is a drop-in replacement for the existing dict-based storage
in VectorTracker and PropagationTracker.  All data is lost on process
restart.

Useful for: testing, demos, single-session use.
Not suitable for: production (no long-arc persistence).
"""

from __future__ import annotations

import copy

from resonance_alignment.core.models import (
    Experience,
    FollowUp,
    UserTrajectory,
)
from resonance_alignment.storage.base import StorageBackend


class InMemoryStorage(StorageBackend):
    """In-memory storage -- all data lost on restart."""

    def __init__(self) -> None:
        self._trajectories: dict[str, UserTrajectory] = {}

    def load_trajectory(self, user_id: str) -> UserTrajectory | None:
        traj = self._trajectories.get(user_id)
        return copy.deepcopy(traj) if traj else None

    def save_trajectory(self, trajectory: UserTrajectory) -> None:
        self._trajectories[trajectory.user_id] = copy.deepcopy(trajectory)

    def list_user_ids(self) -> list[str]:
        return list(self._trajectories.keys())

    def save_experience(self, experience: Experience) -> None:
        user_id = experience.user_id
        traj = self._trajectories.get(user_id)
        if traj is None:
            traj = UserTrajectory(user_id=user_id)
            self._trajectories[user_id] = traj

        # Update or append
        for i, e in enumerate(traj.experiences):
            if e.id == experience.id:
                traj.experiences[i] = copy.deepcopy(experience)
                return
        traj.experiences.append(copy.deepcopy(experience))

    def load_experience(
        self, user_id: str, experience_id: str
    ) -> Experience | None:
        traj = self._trajectories.get(user_id)
        if traj is None:
            return None
        for e in traj.experiences:
            if e.id == experience_id:
                return copy.deepcopy(e)
        return None

    def save_follow_up(
        self, user_id: str, experience_id: str, follow_up: FollowUp
    ) -> None:
        traj = self._trajectories.get(user_id)
        if traj is None:
            return
        for e in traj.experiences:
            if e.id == experience_id:
                e.follow_ups.append(copy.deepcopy(follow_up))
                return

    def health_check(self) -> bool:
        return True
