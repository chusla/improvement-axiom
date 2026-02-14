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
    # Conversation logs
    # ------------------------------------------------------------------

    def log_conversation(
        self,
        session_id: str,
        user_id: str,
        role: str,
        content: str,
        mode: str = "direct",
        metrics: dict | None = None,
    ) -> None:
        """Log a single chat message for observability.

        Default implementation is a no-op; SupabaseStorage persists
        to the conversation_logs table.
        """

    def get_conversation_logs(
        self,
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Retrieve conversation logs, optionally filtered.

        Returns a list of dicts with keys: session_id, user_id, role,
        content, mode, metrics, created_at.
        """
        return []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Release any resources (connections, etc.)."""

    def health_check(self) -> bool:
        """Return True if the storage backend is reachable."""
        return True
