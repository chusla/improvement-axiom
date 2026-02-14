"""Captures and tracks raw resonance signals from experiences.

IMPORTANT CONSTRAINT -- Observable Actions Only:

Resonance prediction is based SOLELY on the individual's own history
of observable actions and their outcomes.  The system never predicts
resonance by comparing to demographic groups, identity attributes, or
statistical stereotypes.

'Similar experiences' means similar *actions* -- not similar people.

DESIGN PRINCIPLE -- Two Sides of the Same Coin:

Quality and resonance are two sides of the same coin.  Quality is the
objective signal (what the experience produces in others).  Resonance
is the subjective experience of it (what the individual feels).

This tracker captures the RAW resonance signal.  At t=0, that's just
the user's self-report.  The ResonanceValidator then calibrates this
against evidence: propagation, temporal arc, depth of response.

The tracker also maintains individual action history for prediction,
always based on the person's OWN past actions, never cross-user
profiling.
"""

from __future__ import annotations

import numpy as np

from resonance_alignment.core.models import Experience, UserTrajectory


class ResonanceTracker:
    """Captures raw resonance signals and maintains action history.

    Resonance is the visceral response -- the 'ringing'.  At t=0 we
    only have the user's self-report.  This tracker captures that raw
    signal and, as evidence accumulates, provides increasingly informed
    measurements.

    All tracking is action-based.  The tracker maintains a history of
    what a person DID and what the resonance outcome was.  It never
    stores or uses identity attributes (race, creed, gender, etc.).
    """

    # At t=0 with no follow-ups, self-report is capped at this ceiling.
    # Self-report alone cannot confirm genuine resonance -- the long
    # arc must validate it.
    _T0_CEILING = 0.60

    # With evidence, self-report weight decreases as action evidence
    # accumulates.  More follow-ups = more trust in action evidence.
    _MAX_EVIDENCE_WEIGHT = 0.70  # caps at 70% evidence, 30% self-report

    def __init__(self) -> None:
        # Action histories per user -- keyed by user_id, contains only
        # observable action data and resonance outcomes.
        self.action_histories: dict[str, list[dict]] = {}
        self.resonance_history: list[dict] = []

    def measure_resonance(
        self,
        experience: Experience,
    ) -> float:
        """Capture resonance from an experience using available evidence.

        At t=0 (no follow-ups): the user's self-report is the raw
        signal, capped at a ceiling because self-report alone can't
        confirm genuine resonance.

        With follow-ups: incorporates depth-of-response evidence.
        Signal depth (intensity of action) matters more than breadth
        (how many people).  This is measured by RATE of deep responses,
        not COUNT.

        Returns raw resonance score between 0.0 and 1.0.

        NOTE: This is the RAW score.  The ResonanceValidator applies
        further adjustments for temporal arc, propagation history, and
        anti-wireheading checks.
        """
        raw = experience.user_rating

        if not experience.follow_ups:
            # t=0: raw self-report capped -- can't confirm depth yet
            score = min(raw, self._T0_CEILING)
        else:
            # With follow-ups, resonance is calibrated by action depth.
            # The hallmarks of genuine resonance (per the Axiom):
            # - Inspiration: the 'electricity', the urge to create
            # - Creative impulse: making something from the experience
            # - Sharing impulse: wanting others to experience it too
            #
            # Measured by RATE (depth), not COUNT (reach).
            n = len(experience.follow_ups)
            created = sum(
                1 for f in experience.follow_ups if f.created_something
            )
            shared = sum(
                1 for f in experience.follow_ups if f.shared_or_taught
            )
            inspired = sum(
                1 for f in experience.follow_ups
                if f.inspired_further_action
            )

            # Depth signal: what fraction showed genuine resonance signs?
            action_rate = (
                0.40 * (created / n)
                + 0.30 * (shared / n)
                + 0.30 * (inspired / n)
            )

            # Self-report weight decreases as evidence accumulates
            evidence_weight = min(
                n * 0.15, self._MAX_EVIDENCE_WEIGHT
            )
            self_report_weight = 1.0 - evidence_weight

            score = self_report_weight * raw + evidence_weight * action_rate

        # Record in action history (for prediction, never cross-user)
        entry = {
            "user_id": experience.user_id,
            "action": experience.description,
            "context": experience.context,
            "score": score,
        }
        self.resonance_history.append(entry)
        self.action_histories.setdefault(
            experience.user_id, []
        ).append(entry)

        return max(0.0, min(1.0, score))

    # ------------------------------------------------------------------
    # Legacy API (backward compatibility)
    # ------------------------------------------------------------------

    def measure_resonance_legacy(
        self, user_id: str, experience: str, context: str
    ) -> float:
        """Legacy string-based API.  Wraps the new evidence-aware method.

        Creates a minimal Experience with just user_rating=0.5 (neutral).
        Prefer the new measure_resonance(experience) for full evidence.
        """
        exp = Experience(
            user_id=user_id,
            description=experience,
            context=context,
            user_rating=0.5,
        )
        return self.measure_resonance(exp)

    # ------------------------------------------------------------------
    # Prediction (individual action history only)
    # ------------------------------------------------------------------

    def predict_resonance(
        self, user_id: str, proposed_experience: str
    ) -> float:
        """Predict likely resonance before an experience occurs.

        Prediction is based ONLY on this individual's own action history.
        'Similar' means similar observable actions, not similar people.

        Args:
            user_id: Opaque identifier.
            proposed_experience: Description of the proposed action.

        Returns:
            Expected resonance score between 0.0 and 1.0.
        """
        own_history = self.action_histories.get(user_id, [])
        similar = self._find_similar_actions(own_history, proposed_experience)
        return self._calculate_expected_resonance(similar)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_similar_actions(
        own_history: list[dict], proposed_experience: str
    ) -> list[dict]:
        """Find past actions similar to the proposed one.

        Similarity is defined by the ACTIONS themselves (what was done),
        not by who did them.  Searches only the individual's own history.
        """
        proposed_words = set(proposed_experience.lower().split())
        similar: list[dict] = []
        for entry in own_history:
            action_words = set(entry.get("action", "").lower().split())
            if proposed_words & action_words:
                similar.append(entry)
        return similar

    @staticmethod
    def _calculate_expected_resonance(similar_actions: list[dict]) -> float:
        """Calculate expected resonance from similar past actions."""
        if not similar_actions:
            return 0.5
        scores = [e["score"] for e in similar_actions if "score" in e]
        return float(np.mean(scores)) if scores else 0.5

    @staticmethod
    def _weighted_average(
        scores: list[float], weights: list[float] | None = None
    ) -> float:
        """Compute weighted average of scores."""
        if not scores:
            return 0.0
        if weights is None:
            weights = [1.0 / len(scores)] * len(scores)
        arr = np.array(scores)
        w = np.array(weights)
        return float(np.clip(np.dot(arr, w) / w.sum(), 0.0, 1.0))
