"""Abstract storage backend for trajectory persistence.

The framework needs to persist user trajectories, experiences,
follow-ups, and vector history across sessions.  Without persistence,
the 'long arc' principle is impossible -- everything resets on restart.

StorageBackend defines the interface.  Implementations:
- InMemoryStorage: current behavior, no persistence (testing/demos)
- SupabaseStorage: PostgreSQL via Supabase (production)

The interface is deliberately simple and trajectory-centric.  The
VectorTracker is the primary consumer: it loads a trajectory, mutates
it, and saves it back.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from resonance_alignment.core.models import (
    Experience,
    FollowUp,
    UserTrajectory,
)


class StorageBackend(ABC):
    """Abstract persistence layer for the Improvement Axiom."""

    # ------------------------------------------------------------------
    # Trajectories
    # ------------------------------------------------------------------

    @abstractmethod
    def load_trajectory(self, user_id: str) -> UserTrajectory | None:
        """Load a user's full trajectory.

        Returns None if the user has no stored history.
        """

    @abstractmethod
    def save_trajectory(self, trajectory: UserTrajectory) -> None:
        """Persist a user's trajectory (upsert: create or update)."""

    @abstractmethod
    def list_user_ids(self) -> list[str]:
        """List all user IDs with stored trajectories."""

    # ------------------------------------------------------------------
    # Experiences (convenience -- also accessible via trajectory)
    # ------------------------------------------------------------------

    @abstractmethod
    def save_experience(self, experience: Experience) -> None:
        """Persist a single experience."""

    @abstractmethod
    def load_experience(
        self, user_id: str, experience_id: str
    ) -> Experience | None:
        """Load a specific experience by ID."""

    # ------------------------------------------------------------------
    # Follow-ups
    # ------------------------------------------------------------------

    @abstractmethod
    def save_follow_up(
        self, user_id: str, experience_id: str, follow_up: FollowUp
    ) -> None:
        """Persist a follow-up observation."""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Release any resources (connections, etc.)."""

    def health_check(self) -> bool:
        """Return True if the storage backend is reachable."""
        return True
