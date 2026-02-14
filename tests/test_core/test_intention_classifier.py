"""Tests for the vector-aware IntentionClassifier."""

import pytest
from datetime import timedelta

from resonance_alignment.core.intention_classifier import IntentionClassifier
from resonance_alignment.core.models import (
    Experience,
    FollowUp,
    IntentionSignal,
    UserTrajectory,
    VectorSnapshot,
)


class TestColdStart:
    """With no history, classification should be PENDING or very low confidence."""

    def test_no_history_low_confidence(self):
        classifier = IntentionClassifier()
        exp = Experience(description="played video games all day")
        traj = UserTrajectory()

        signal, confidence = classifier.classify(exp, traj)

        # Confidence should be very low
        assert confidence < 0.20

    def test_neutral_description_is_pending(self):
        classifier = IntentionClassifier()
        exp = Experience(description="spent time with something")
        traj = UserTrajectory()

        signal, confidence = classifier.classify(exp, traj)

        assert signal == IntentionSignal.PENDING


class TestFollowUpDominates:
    """Follow-up evidence should be the strongest signal."""

    def test_creative_follow_up_overrides_consumptive_hints(self):
        """Even if keywords suggest consumption, follow-up creation flips it."""
        classifier = IntentionClassifier()
        exp = Experience(description="binge watched scrolling consuming content")
        exp.follow_ups.append(FollowUp(
            created_something=True,
            shared_or_taught=True,
            inspired_further_action=True,
            creation_description="Wrote a review blog post",
        ))
        traj = UserTrajectory()

        signal, confidence = classifier.classify(exp, traj)

        # Follow-up evidence of creation should push toward creative
        assert signal in (IntentionSignal.CREATIVE, IntentionSignal.MIXED)
        assert confidence > 0.15  # some confidence from follow-up

    def test_no_follow_up_creation_leans_consumptive(self):
        """Experience with consumptive keywords and no creative follow-up."""
        classifier = IntentionClassifier()
        exp = Experience(description="scrolling through social media for hours")
        exp.follow_ups.append(FollowUp(
            created_something=False,
            shared_or_taught=False,
            inspired_further_action=False,
            content="Just kept scrolling more",
        ))
        traj = UserTrajectory()

        signal, confidence = classifier.classify(exp, traj)

        assert signal == IntentionSignal.CONSUMPTIVE


class TestTrajectoryContext:
    """User's trajectory history should inform provisional classification."""

    def test_creative_trajectory_informs_new_experience(self):
        """A user with a strong creative history gets a slight creative lean."""
        classifier = IntentionClassifier()
        exp = Experience(description="watched a documentary")

        traj = UserTrajectory(user_id="creator")
        traj.current_vector = VectorSnapshot(direction=0.7, magnitude=0.6, confidence=0.6)
        traj.experiences = [Experience() for _ in range(5)]  # has history

        signal, confidence = classifier.classify(exp, traj)

        # Should lean creative due to trajectory, but confidence still moderate
        assert signal in (IntentionSignal.CREATIVE, IntentionSignal.MIXED)


class TestLegacyAPI:
    """The old classify_intent() should still work."""

    def test_legacy_returns_string(self):
        classifier = IntentionClassifier()
        label, confidence = classifier.classify_intent("wrote a song", "")

        assert isinstance(label, str)
        assert label in ("creative", "consumptive", "mixed", "pending")
