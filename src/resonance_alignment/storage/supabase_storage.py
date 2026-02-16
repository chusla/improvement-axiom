"""Supabase (PostgreSQL) storage backend for production persistence.

Stores trajectories, experiences, follow-ups, and vector history in
Supabase, enabling the 'long arc' principle across sessions.

TABLES REQUIRED (run the SQL in supabase_schema.sql):
  - trajectories: user-level trajectory metadata
  - experiences: individual experiences with evolving assessments
  - follow_ups: follow-up observations linked to experiences
  - vector_snapshots: point-in-time vector measurements

SETUP:
  pip install supabase
  export SUPABASE_URL="https://your-project.supabase.co"
  export SUPABASE_KEY="your-service-role-key"

The schema is designed for the vector-based architecture:
trajectories are the primary entity, experiences are children,
follow-ups are children of experiences.  Vector snapshots are
append-only (full history preserved for the long arc).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any


def _safe_fromisoformat(value: str) -> datetime:
    """Parse an ISO-format datetime string with any fractional-second precision.

    Python < 3.11 only accepts 0, 3, or 6 fractional digits.  Supabase
    (PostgreSQL) may return 5 digits (e.g. ``...47.71966+00:00``).
    This helper normalises to 6 digits before parsing.
    """
    # Match fractional seconds of any length
    m = re.search(r'\.(\d+)', value)
    if m:
        frac = m.group(1)
        if len(frac) not in (0, 3, 6):
            # Pad or truncate to 6 digits
            normalised = frac[:6].ljust(6, '0')
            value = value[:m.start(1)] + normalised + value[m.end(1):]
    return datetime.fromisoformat(value)

from resonance_alignment.core.models import (
    Experience,
    FollowUp,
    IntentionSignal,
    UserTrajectory,
    VectorSnapshot,
    TimeHorizon,
    HorizonAssessment,
)
from resonance_alignment.storage.base import StorageBackend


class SupabaseStorage(StorageBackend):
    """Supabase-backed persistence for production use.

    Requires: pip install supabase
    """

    def __init__(
        self,
        supabase_url: str,
        supabase_key: str,
    ) -> None:
        try:
            from supabase import create_client, Client
            self._client: Client = create_client(supabase_url, supabase_key)
        except ImportError:
            raise ImportError(
                "supabase is required for Supabase storage.  "
                "Install it with: pip install supabase"
            )
        # Track already-persisted snapshots to avoid redundant upserts.
        # Key: (user_id, experience_id_or_none, timestamp_iso)
        self._saved_snapshots: set[tuple[str, str | None, str]] = set()

    # ------------------------------------------------------------------
    # Trajectories
    # ------------------------------------------------------------------

    def load_trajectory(self, user_id: str) -> UserTrajectory | None:
        """Load full trajectory from Supabase."""
        # Load trajectory metadata
        result = (
            self._client.table("trajectories")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        if not result.data:
            return None

        row = result.data[0]
        trajectory = UserTrajectory(
            user_id=user_id,
            creation_rate=row.get("creation_rate", 0.0),
            propagation_rate=row.get("propagation_rate", 0.0),
            compounding_direction=row.get("compounding_direction", 0.0),
        )

        # Load current vector
        if row.get("current_direction") is not None:
            trajectory.current_vector = VectorSnapshot(
                direction=row["current_direction"],
                magnitude=row.get("current_magnitude", 0.0),
                confidence=row.get("current_confidence", 0.0),
            )

        # Load experiences
        exp_result = (
            self._client.table("experiences")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at")
            .execute()
        )
        for exp_row in exp_result.data:
            experience = self._row_to_experience(exp_row)

            # Load follow-ups for this experience
            fu_result = (
                self._client.table("follow_ups")
                .select("*")
                .eq("experience_id", experience.id)
                .order("created_at")
                .execute()
            )
            for fu_row in fu_result.data:
                experience.follow_ups.append(self._row_to_follow_up(fu_row))

            # Load vector snapshots
            vs_result = (
                self._client.table("vector_snapshots")
                .select("*")
                .eq("experience_id", experience.id)
                .order("created_at")
                .execute()
            )
            for vs_row in vs_result.data:
                experience.vector_snapshots.append(
                    self._row_to_vector_snapshot(vs_row)
                )
                # Mark as already persisted so save_trajectory won't re-upsert
                self._saved_snapshots.add(
                    (user_id, experience.id, vs_row["created_at"])
                )

            trajectory.experiences.append(experience)

        # Load trajectory-level vector history
        hist_result = (
            self._client.table("vector_snapshots")
            .select("*")
            .eq("user_id", user_id)
            .is_("experience_id", "null")
            .order("created_at")
            .execute()
        )
        for vs_row in hist_result.data:
            trajectory.vector_history.append(
                self._row_to_vector_snapshot(vs_row)
            )
            self._saved_snapshots.add(
                (user_id, None, vs_row["created_at"])
            )

        return trajectory

    def save_trajectory(self, trajectory: UserTrajectory) -> None:
        """Persist trajectory to Supabase (upsert)."""
        self._client.table("trajectories").upsert({
            "user_id": trajectory.user_id,
            "creation_rate": trajectory.creation_rate,
            "propagation_rate": trajectory.propagation_rate,
            "compounding_direction": trajectory.compounding_direction,
            "current_direction": trajectory.current_vector.direction,
            "current_magnitude": trajectory.current_vector.magnitude,
            "current_confidence": trajectory.current_vector.confidence,
            "experience_count": trajectory.experience_count,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

        # Save experiences
        for exp in trajectory.experiences:
            self.save_experience(exp)

        # Save trajectory-level vector history (append new snapshots)
        for vs in trajectory.vector_history:
            self._save_vector_snapshot(
                vs, trajectory.user_id, experience_id=None
            )

    def list_user_ids(self) -> list[str]:
        result = (
            self._client.table("trajectories")
            .select("user_id")
            .execute()
        )
        return [row["user_id"] for row in result.data]

    # ------------------------------------------------------------------
    # Experiences
    # ------------------------------------------------------------------

    def save_experience(self, experience: Experience) -> None:
        self._client.table("experiences").upsert({
            "id": experience.id,
            "user_id": experience.user_id,
            "description": experience.description,
            "context": experience.context,
            "user_rating": experience.user_rating,
            "created_at": experience.timestamp.isoformat(),
            "provisional_intention": experience.provisional_intention.value,
            "intention_confidence": experience.intention_confidence,
            "resonance_score": experience.resonance_score,
            "quality_score": experience.quality_score,
            "quality_dimensions": json.dumps(experience.quality_dimensions),
            "propagated": experience.propagated,
            "propagation_events": json.dumps(experience.propagation_events),
            "matrix_position": experience.matrix_position,
        }).execute()

        # Save follow-ups
        for fu in experience.follow_ups:
            self.save_follow_up(experience.user_id, experience.id, fu)

        # Save vector snapshots
        for vs in experience.vector_snapshots:
            self._save_vector_snapshot(
                vs, experience.user_id, experience.id
            )

    def load_experience(
        self, user_id: str, experience_id: str
    ) -> Experience | None:
        result = (
            self._client.table("experiences")
            .select("*")
            .eq("id", experience_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not result.data:
            return None
        return self._row_to_experience(result.data[0])

    # ------------------------------------------------------------------
    # Follow-ups
    # ------------------------------------------------------------------

    def save_follow_up(
        self, user_id: str, experience_id: str, follow_up: FollowUp
    ) -> None:
        self._client.table("follow_ups").upsert({
            "id": follow_up.id,
            "experience_id": experience_id,
            "user_id": user_id,
            "created_at": follow_up.timestamp.isoformat(),
            "source": follow_up.source,
            "content": follow_up.content,
            "created_something": follow_up.created_something,
            "creation_description": follow_up.creation_description,
            "creation_magnitude": follow_up.creation_magnitude,
            "shared_or_taught": follow_up.shared_or_taught,
            "inspired_further_action": follow_up.inspired_further_action,
        }).execute()

    # ------------------------------------------------------------------
    # Vector snapshots (append-only)
    # ------------------------------------------------------------------

    def _save_vector_snapshot(
        self,
        vs: VectorSnapshot,
        user_id: str,
        experience_id: str | None,
    ) -> None:
        key = (user_id, experience_id, vs.timestamp.isoformat())
        if key in self._saved_snapshots:
            return  # Already persisted this session
        self._client.table("vector_snapshots").upsert({
            "user_id": user_id,
            "experience_id": experience_id,
            "created_at": vs.timestamp.isoformat(),
            "direction": vs.direction,
            "magnitude": vs.magnitude,
            "confidence": vs.confidence,
            "horizon": vs.horizon.value,
        }).execute()
        self._saved_snapshots.add(key)

    # ------------------------------------------------------------------
    # Row → model converters
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_experience(row: dict[str, Any]) -> Experience:
        return Experience(
            id=row["id"],
            user_id=row["user_id"],
            description=row.get("description", ""),
            context=row.get("context", ""),
            user_rating=row.get("user_rating", 0.5),
            timestamp=_safe_fromisoformat(row["created_at"]),
            provisional_intention=IntentionSignal(
                row.get("provisional_intention", "pending")
            ),
            intention_confidence=row.get("intention_confidence", 0.0),
            resonance_score=row.get("resonance_score", 0.0),
            quality_score=row.get("quality_score", 0.0),
            quality_dimensions=json.loads(
                row.get("quality_dimensions", "{}")
            ),
            propagated=row.get("propagated", False),
            propagation_events=json.loads(
                row.get("propagation_events", "[]")
            ),
            matrix_position=row.get("matrix_position", "Pending"),
        )

    @staticmethod
    def _row_to_follow_up(row: dict[str, Any]) -> FollowUp:
        return FollowUp(
            id=row["id"],
            experience_id=row.get("experience_id", ""),
            timestamp=_safe_fromisoformat(row["created_at"]),
            source=row.get("source", "user_response"),
            content=row.get("content", ""),
            created_something=row.get("created_something", False),
            creation_description=row.get("creation_description", ""),
            creation_magnitude=row.get("creation_magnitude", 0.0),
            shared_or_taught=row.get("shared_or_taught", False),
            inspired_further_action=row.get("inspired_further_action", False),
        )

    @staticmethod
    def _row_to_vector_snapshot(row: dict[str, Any]) -> VectorSnapshot:
        return VectorSnapshot(
            timestamp=_safe_fromisoformat(row["created_at"]),
            direction=row.get("direction", 0.0),
            magnitude=row.get("magnitude", 0.0),
            confidence=row.get("confidence", 0.0),
            horizon=TimeHorizon(row.get("horizon", "immediate")),
        )

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
        """Persist a chat message to the conversation_logs table.

        Raises on failure so the caller can decide how to handle it
        (e.g. log a warning instead of silently swallowing).
        """
        try:
            self._client.table("conversation_logs").insert({
                "session_id": session_id,
                "user_id": user_id,
                "role": role,
                "content": content,
                "mode": mode,
                "metrics": json.dumps(metrics) if metrics else None,
            }).execute()
        except Exception as e:
            import warnings
            warnings.warn(
                f"[SupabaseStorage] Failed to log conversation: {e}",
                stacklevel=2,
            )
            raise

    def get_conversation_logs(
        self,
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Retrieve conversation logs from Supabase."""
        query = self._client.table("conversation_logs").select("*")
        if session_id:
            query = query.eq("session_id", session_id)
        if user_id:
            query = query.eq("user_id", user_id)
        query = query.order("created_at", desc=True).limit(limit)
        result = query.execute()
        rows = result.data or []
        # Parse metrics JSON back to dict
        for row in rows:
            if row.get("metrics") and isinstance(row["metrics"], str):
                try:
                    row["metrics"] = json.loads(row["metrics"])
                except (json.JSONDecodeError, TypeError):
                    pass
        return list(reversed(rows))  # chronological order

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        try:
            self._client.table("trajectories").select("user_id").limit(1).execute()
            return True
        except Exception:
            return False
