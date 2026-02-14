"""Tests for ExtrapolationModel -- evidence-based hypothesis generation.

All tests use MockWebClient with canned search results.
"""

from datetime import datetime

import pytest

from resonance_alignment.core.extrapolation_model import ExtrapolationModel
from resonance_alignment.core.models import (
    Experience,
    UserTrajectory,
    VectorSnapshot,
)
from resonance_alignment.core.web_client import MockWebClient, SearchResult


@pytest.fixture
def mock_web():
    mock = MockWebClient()

    # Canned search results for video game queries
    mock.add_search_results("video games long term outcomes", [
        SearchResult(
            title="The Impact of Video Games on Youth Development",
            url="https://research.example.com/games-youth",
            snippet="Research shows mixed outcomes. Most players engage casually "
                    "with no negative or positive career impact.",
            source="Journal of Youth Studies",
        ),
        SearchResult(
            title="Video Game Addiction: Signs and Risks",
            url="https://health.example.com/game-addiction",
            snippet="Excessive gaming can lead to addiction and social decline "
                    "in a minority of players.",
            source="Health Review",
        ),
        SearchResult(
            title="From Gamer to Game Developer: Career Paths",
            url="https://careers.example.com/game-dev-path",
            snippet="Many successful game developers credit early gaming "
                    "as the spark for their creative career.",
            source="Career Insights",
        ),
    ])

    mock.add_search_results("video games career development research", [
        SearchResult(
            title="Gaming Skills Transfer to Professional Development",
            url="https://research.example.com/gaming-skills",
            snippet="Problem-solving and teamwork skills developed through "
                    "strategic gaming can transfer to professional settings.",
            source="Skills Research",
        ),
    ])

    mock.add_search_results("video games creative results examples", [
        SearchResult(
            title="How Minecraft Inspired a Generation of Builders",
            url="https://edu.example.com/minecraft-builders",
            snippet="Minecraft players who transitioned to creating mods, "
                    "maps, and even full games demonstrate the creative "
                    "potential of gaming as a foundation.",
            source="Education Weekly",
        ),
    ])

    return mock


@pytest.fixture
def model(mock_web):
    return ExtrapolationModel(mock_web)


class TestHypothesisGeneration:
    """The model should generate structured hypotheses from search results."""

    def test_generates_hypotheses_for_gaming(self, model):
        exp = Experience(
            description="Played video games all weekend",
            user_rating=0.8,
        )

        evidence = model.hypothesise(exp)

        assert evidence.total_sources_found > 0
        assert len(evidence.hypotheses) >= 1

    def test_hypotheses_have_required_fields(self, model):
        exp = Experience(
            description="Played video games all weekend",
            user_rating=0.7,
        )

        evidence = model.hypothesise(exp)

        for h in evidence.hypotheses:
            assert h.action_pattern != ""
            assert h.typical_trajectory != ""
            assert h.empowerment_note != ""
            assert isinstance(h.distinguishing_factors, list)
            assert isinstance(h.notable_exceptions, list)
            assert isinstance(h.sources, list)

    def test_always_includes_empowerment(self, model):
        """Every hypothesis must empower the individual, not judge."""
        exp = Experience(
            description="Played video games all weekend",
            user_rating=0.6,
        )

        evidence = model.hypothesise(exp)

        for h in evidence.hypotheses:
            assert len(h.empowerment_note) > 10
            # Empowerment notes should not be deterministic/judgmental
            assert "you must" not in h.empowerment_note.lower()
            assert "you should stop" not in h.empowerment_note.lower()

    def test_always_includes_exceptions(self, model):
        """Every hypothesis must highlight that exceptions exist."""
        exp = Experience(
            description="Played video games all weekend",
            user_rating=0.7,
        )

        evidence = model.hypothesise(exp)

        for h in evidence.hypotheses:
            assert len(h.notable_exceptions) >= 1

    def test_cites_sources(self, model):
        """Non-personalised hypotheses should cite sources."""
        exp = Experience(
            description="Played video games all weekend",
            user_rating=0.7,
        )

        evidence = model.hypothesise(exp)

        # At least one non-personalised hypothesis should have sources
        sourced = [h for h in evidence.hypotheses if h.sources]
        assert len(sourced) >= 1


class TestTrajectoryAwareHypothesis:
    """With user trajectory, the model should include personalised context."""

    def test_creative_trajectory_noted(self, model):
        exp = Experience(
            description="Played video games all weekend",
            user_rating=0.8,
        )

        traj = UserTrajectory(
            user_id="user1",
            experiences=[Experience() for _ in range(5)],
            current_vector=VectorSnapshot(direction=0.6, confidence=0.5),
        )

        evidence = model.hypothesise(exp, trajectory=traj)

        # Should include a trajectory-informed hypothesis
        personalised = [
            h for h in evidence.hypotheses
            if "trajectory" in h.typical_trajectory.lower()
        ]
        assert len(personalised) >= 1

    def test_consumptive_trajectory_noted(self, model):
        exp = Experience(
            description="Played video games all weekend",
            user_rating=0.6,
        )

        traj = UserTrajectory(
            user_id="user2",
            experiences=[Experience() for _ in range(5)],
            current_vector=VectorSnapshot(direction=-0.5, confidence=0.4),
        )

        evidence = model.hypothesise(exp, trajectory=traj)

        personalised = [
            h for h in evidence.hypotheses
            if "trajectory" in h.typical_trajectory.lower()
        ]
        assert len(personalised) >= 1


class TestGracefulDegradation:
    """With no search results, the model should degrade gracefully."""

    def test_no_results_returns_empty_with_note(self):
        empty_mock = MockWebClient()  # No search results configured
        model = ExtrapolationModel(empty_mock)

        exp = Experience(
            description="Did something completely novel",
            user_rating=0.5,
        )

        evidence = model.hypothesise(exp)

        assert len(evidence.hypotheses) == 0
        assert evidence.total_sources_found == 0
        assert "insufficient" in evidence.note.lower() or "no" in evidence.note.lower()


class TestActionPatternExtraction:
    """The model should extract meaningful action phrases."""

    def test_strips_filler_prefixes(self, model):
        queries = model._build_search_queries(
            Experience(description="I have been playing guitar for months")
        )
        # Should not start with "I have been"
        for q in queries:
            assert not q.lower().startswith("i have been")

    def test_generates_multiple_query_types(self, model):
        queries = model._build_search_queries(
            Experience(description="writing poetry")
        )
        # Should generate at least 2 different query angles
        assert len(queries) >= 2
