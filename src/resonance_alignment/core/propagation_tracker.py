"""Tracks whether resonance propagates into downstream creation.

'We write to taste life twice, in the moment and in retrospect.'
                                            -- Anaïs Nin

The transmission test: genuine resonance *propagates*.  The receiver
is inspired to transmit or channel the experience through their own
lens -- to create, share, teach, build.  If an experience produces
high reported resonance but NO downstream creative behaviour, it is
likely a dopamine hit, not genuine resonance.

PropagationTracker monitors this at the individual level and, when
aggregated, across communities of practice -- always defined by
observable shared actions and outcomes, never by identity attributes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from resonance_alignment.core.models import Experience, UserTrajectory


@dataclass
class CreationEvent:
    """Records a downstream creation inspired by an experience."""

    id: str = ""
    user_id: str = ""
    description: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    inspired_by_experience_id: str | None = None


class PropagationTracker:
    """Monitors the transmission of resonance into creative output.

    Core question: after a high-resonance experience, did the person
    *do something* with it?  Create, share, teach, remix, build?

    If yes → resonance was authentic.
    If no  → it may have been a sugar hit.
    """

    def __init__(self) -> None:
        # user_id → list of creation events
        self.creation_events: dict[str, list[CreationEvent]] = {}

    def record_creation_event(
        self,
        user_id: str,
        description: str,
        inspired_by_experience_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> CreationEvent:
        """Record that a user created something."""
        event = CreationEvent(
            user_id=user_id,
            description=description,
            timestamp=timestamp or datetime.utcnow(),
            inspired_by_experience_id=inspired_by_experience_id,
        )
        self.creation_events.setdefault(user_id, []).append(event)
        return event

    def check_propagation(
        self,
        user_id: str,
        experience_id: str,
        time_window_days: int = 30,
    ) -> list[CreationEvent]:
        """Return creation events linked to a specific experience."""
        events = self.creation_events.get(user_id, [])
        return [
            e for e in events
            if e.inspired_by_experience_id == experience_id
        ]

    def compute_propagation_rate(self, trajectory: UserTrajectory) -> float:
        """What fraction of high-resonance experiences led to creation?

        'High-resonance' is defined as user_rating > 0.6.
        An experience 'led to creation' if it has at least one
        propagation event or a follow-up with ``created_something``.
        """
        high_resonance = [
            e for e in trajectory.experiences
            if e.resonance_score > 0.6 or e.user_rating > 0.6
        ]
        if not high_resonance:
            return 0.0

        propagated = sum(1 for e in high_resonance if e.propagated)
        return propagated / len(high_resonance)

    def validate_resonance_authenticity(
        self,
        resonance_score: float,
        trajectory: UserTrajectory,
    ) -> float:
        """Adjust resonance score based on historical propagation pattern.

        If this user's high-resonance experiences consistently lead to
        creation, we *trust* the score (small boost).
        If they consistently DON'T propagate, we *discount* it.

        Returns the adjusted resonance score.
        """
        rate = self.compute_propagation_rate(trajectory)

        if rate > 0.5:
            # Strong propagation history -- resonance is likely genuine
            trust_bonus = min(rate * 0.15, 0.1)
            return min(resonance_score + trust_bonus, 1.0)
        elif rate < 0.2 and trajectory.experience_count >= 3:
            # Weak propagation history -- discount
            penalty = 0.15 * (1.0 - rate)
            return max(resonance_score - penalty, 0.0)

        return resonance_score
