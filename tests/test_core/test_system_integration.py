"""Integration tests for the full ResonanceAlignmentSystem pipeline.

These tests demonstrate the core philosophy: the system withholds
judgment at t=0 and the vector reveals itself through follow-ups.
"""

import pytest
from datetime import datetime, timedelta

from resonance_alignment.system import ResonanceAlignmentSystem
from resonance_alignment.core.models import FollowUp, IntentionSignal


class TestNewExperienceIsProvisional:
    """A new experience should always be provisional with low confidence."""

    def test_first_experience_generates_questions(self):
        system = ResonanceAlignmentSystem()
        result = system.process_experience(
            user_id="user1",
            experience_description="Played video games all weekend",
            user_rating=0.8,
            context="First time trying this game",
        )

        # Should have generated follow-up questions
        assert len(result.pending_questions) >= 2

        # Confidence should be low
        assert result.experience.intention_confidence < 0.20

        # Should not have definitive matrix placement
        assert result.is_provisional

    def test_questions_are_contextual(self):
        system = ResonanceAlignmentSystem()
        result = system.process_experience(
            user_id="user1",
            experience_description="Watched 3 seasons of anime",
            user_rating=0.9,
            context="",
        )

        # Questions should reference the experience
        for q in result.pending_questions:
            assert "anime" in q.question.lower() or "seasons" in q.question.lower()


class TestFollowUpRevealsVector:
    """The two-entry-point flow: experience then follow-up."""

    def test_creative_follow_up_shifts_assessment(self):
        system = ResonanceAlignmentSystem()

        # Step 1: Record experience
        result1 = system.process_experience(
            user_id="user1",
            experience_description="Binge watched a cooking show",
            user_rating=0.7,
            context="",
        )
        exp_id = result1.experience.id
        initial_confidence = result1.experience.intention_confidence

        # Step 2: Follow up -- user started cooking!
        follow_up = FollowUp(
            timestamp=result1.experience.timestamp + timedelta(days=3),
            source="user_response",
            content="I was so inspired I started cooking the recipes myself",
            created_something=True,
            creation_description="Cooked three new recipes from the show",
            shared_or_taught=True,  # shared with family
            inspired_further_action=True,
        )
        result2 = system.process_follow_up("user1", exp_id, follow_up)

        assert result2 is not None
        # Confidence should have increased
        assert result2.experience.intention_confidence > initial_confidence
        # Should lean creative now
        assert result2.experience.provisional_intention in (
            IntentionSignal.CREATIVE, IntentionSignal.MIXED
        )
        # Propagation should be recorded
        assert result2.experience.propagated is True

    def test_consumptive_follow_up_shifts_assessment(self):
        system = ResonanceAlignmentSystem()

        result1 = system.process_experience(
            user_id="user2",
            experience_description="Binge watched a cooking show",
            user_rating=0.7,
            context="",
        )
        exp_id = result1.experience.id

        # Nothing came of it
        follow_up = FollowUp(
            timestamp=result1.experience.timestamp + timedelta(days=3),
            content="Just ordered takeout and watched more TV",
            created_something=False,
            shared_or_taught=False,
            inspired_further_action=False,
        )
        result2 = system.process_follow_up("user2", exp_id, follow_up)

        assert result2 is not None
        assert result2.experience.provisional_intention in (
            IntentionSignal.CONSUMPTIVE, IntentionSignal.MIXED
        )


class TestSameActivityDifferentVectors:
    """The definitive test: same activity, two users, divergent outcomes."""

    def test_video_game_kids_diverge(self):
        system = ResonanceAlignmentSystem()

        # Both kids play the same game
        result_a = system.process_experience(
            "kid_a", "Played Minecraft all weekend", 0.9, ""
        )
        result_b = system.process_experience(
            "kid_b", "Played Minecraft all weekend", 0.9, ""
        )

        # At t=0 they should be nearly identical
        diff_0 = abs(
            result_a.experience.intention_confidence
            - result_b.experience.intention_confidence
        )
        assert diff_0 < 0.05

        # Kid A: just consumes more
        system.process_follow_up("kid_a", result_a.experience.id, FollowUp(
            timestamp=result_a.experience.timestamp + timedelta(days=7),
            content="Played more Minecraft",
            created_something=False,
        ))

        # Kid B: starts building
        system.process_follow_up("kid_b", result_b.experience.id, FollowUp(
            timestamp=result_b.experience.timestamp + timedelta(days=7),
            content="Started learning redstone circuits and built a calculator",
            created_something=True,
            creation_description="Redstone calculator in Minecraft",
            inspired_further_action=True,
        ))

        # Now the trajectories should have diverged
        traj_a = system.vector_tracker.get_trajectory("kid_a")
        traj_b = system.vector_tracker.get_trajectory("kid_b")

        assert traj_a.current_vector.direction < traj_b.current_vector.direction


class TestExplanationIncludesProvisionalMarkers:
    """Explanations should clearly indicate when assessment is provisional."""

    def test_provisional_note_in_explanation(self):
        system = ResonanceAlignmentSystem()
        result = system.process_experience("user1", "Did something", 0.5, "")

        assert result.explanation["intention"]["is_provisional"] is True
        assert "provisional" in result.explanation["intention"]["note"].lower()

    def test_temporal_note_indicates_pending_horizons(self):
        system = ResonanceAlignmentSystem()
        result = system.process_experience("user1", "Did something", 0.5, "")

        # Most horizons should be pending at t=0
        assert result.explanation["temporal"]["horizons_with_data"] <= 2
        assert "long arc" in result.explanation["temporal"]["note"].lower() or \
               "needs time" in result.explanation["temporal"]["note"].lower()
