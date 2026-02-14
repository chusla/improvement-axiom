"""Integration tests for web-enabled system (Defence Layers 2 & 5).

Tests the full pipeline with MockWebClient: experience processing
with extrapolation, artifact submission, and graceful degradation
when offline.
"""

from datetime import datetime, timedelta

import pytest

from resonance_alignment.system import ResonanceAlignmentSystem
from resonance_alignment.core.models import FollowUp
from resonance_alignment.core.web_client import (
    MockWebClient,
    WebPage,
    SearchResult,
)


@pytest.fixture
def mock_web():
    mock = MockWebClient()

    # Search results for extrapolation
    mock.add_search_results("cooking show long term outcomes", [
        SearchResult(
            title="TV Cooking Shows and Home Cooking Trends",
            url="https://research.example.com/cooking-shows",
            snippet="Studies show cooking shows inspire some viewers to cook "
                    "more at home, though many remain passive viewers.",
        ),
        SearchResult(
            title="From Food Network Fan to Professional Chef",
            url="https://careers.example.com/chef-paths",
            snippet="Several professional chefs credit cooking shows as their "
                    "initial creative spark for entering the culinary field.",
        ),
    ])

    # Artifact pages
    mock.add_page(
        "https://medium.com/user1/my-recipe-blog",
        WebPage(
            url="https://medium.com/user1/my-recipe-blog",
            status_code=200,
            title="My First Recipe: Inspired by a Cooking Show",
            content_text=(
                "After binge watching a cooking show, I was so inspired "
                "I started cooking the recipes myself. Here are three "
                "recipes I adapted and what I learned about flavour "
                "combinations, knife technique, and plating presentation. "
                "The experience of creating something tangible from "
                "watching was transformative for me as a home cook."
            ),
            publish_date="2025-06-20",
            platform="medium",
            accessible=True,
        ),
    )

    return mock


class TestOnlineSystem:
    """System with web access should include extrapolation and artifacts."""

    def test_process_experience_includes_extrapolation(self, mock_web):
        system = ResonanceAlignmentSystem(web_client=mock_web)
        assert system.has_web_access is True

        result = system.process_experience(
            user_id="user1",
            experience_description="Binge watched a cooking show",
            user_rating=0.7,
            context="",
        )

        # Should include trajectory evidence
        assert result.trajectory_evidence is not None
        # May or may not have hypotheses depending on search results
        # but should at least have a note
        assert result.trajectory_evidence.note != ""

    def test_submit_artifact_verifies(self, mock_web):
        system = ResonanceAlignmentSystem(web_client=mock_web)

        # First record an experience
        result = system.process_experience(
            user_id="user1",
            experience_description="Watched a cooking show and was inspired",
            user_rating=0.8,
            context="weekend binge",
        )
        exp_id = result.experience.id

        # Submit an artifact as evidence
        verification = system.submit_artifact(
            user_id="user1",
            experience_id=exp_id,
            url="https://medium.com/user1/my-recipe-blog",
            user_claim="Blog post about recipes I created after the show",
        )

        assert verification.url_accessible is True
        assert verification.content_substantive is True
        assert verification.status == "verified"

    def test_verified_artifact_updates_propagation(self, mock_web):
        """A verified artifact should update the experience's propagation."""
        system = ResonanceAlignmentSystem(web_client=mock_web)

        result = system.process_experience(
            "user1", "Watched a cooking show", 0.7, ""
        )
        exp_id = result.experience.id

        assert result.experience.propagated is False

        system.submit_artifact(
            user_id="user1",
            experience_id=exp_id,
            url="https://medium.com/user1/my-recipe-blog",
            user_claim="My recipe blog post",
        )

        # The experience should now show propagation
        traj = system.vector_tracker.get_trajectory("user1")
        exp = system.vector_tracker._find_experience(traj, exp_id)
        assert exp.propagated is True
        assert len(exp.propagation_events) >= 1


class TestOfflineSystem:
    """System without web access should degrade gracefully."""

    def test_offline_system_still_works(self):
        system = ResonanceAlignmentSystem()  # No web client
        assert system.has_web_access is False

        result = system.process_experience(
            user_id="user1",
            experience_description="Played video games",
            user_rating=0.6,
            context="",
        )

        # Should still produce a valid assessment
        assert result.experience is not None
        assert result.is_provisional is True

        # Trajectory evidence should exist but with a degradation note
        assert result.trajectory_evidence is not None
        assert "web access" in result.trajectory_evidence.note.lower() or \
               "internet" in result.trajectory_evidence.note.lower()

    def test_offline_artifact_returns_inaccessible(self):
        system = ResonanceAlignmentSystem()  # No web client

        # Record experience first
        result = system.process_experience("user1", "Test", 0.5, "")
        exp_id = result.experience.id

        verification = system.submit_artifact(
            user_id="user1",
            experience_id=exp_id,
            url="https://example.com/post",
            user_claim="My creation",
        )

        assert verification.status == "inaccessible"
        assert "web access" in verification.notes.lower() or \
               "internet" in verification.notes.lower()

    def test_offline_follow_up_still_works(self):
        """Follow-up processing works without web access."""
        system = ResonanceAlignmentSystem()

        result1 = system.process_experience(
            "user1", "Attended a workshop", 0.7, ""
        )
        # Capture initial confidence BEFORE follow-up mutates the
        # shared Experience object.
        initial_confidence = result1.experience.intention_confidence

        follow_up = FollowUp(
            timestamp=result1.experience.timestamp + timedelta(days=3),
            created_something=True,
            creation_description="Built a project",
            shared_or_taught=True,
            inspired_further_action=True,
        )

        result2 = system.process_follow_up(
            "user1", result1.experience.id, follow_up
        )

        assert result2 is not None
        assert result2.experience.intention_confidence > initial_confidence
