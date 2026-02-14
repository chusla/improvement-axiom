"""Tests for ArtifactVerifier -- portfolio-based external verification.

All tests use MockWebClient so they run without internet access.
The mock simulates various artifact scenarios: substantive blog posts,
trivial content, inaccessible URLs, timestamp mismatches, etc.
"""

from datetime import datetime, timedelta

import pytest

from resonance_alignment.core.models import Artifact, Experience
from resonance_alignment.core.web_client import MockWebClient, WebPage
from resonance_alignment.safety.artifact_verifier import ArtifactVerifier


@pytest.fixture
def mock_web():
    return MockWebClient()


@pytest.fixture
def verifier(mock_web):
    return ArtifactVerifier(mock_web)


@pytest.fixture
def experience():
    return Experience(
        id="exp1",
        user_id="user1",
        description="Built a woodworking project inspired by the workshop",
        context="attended woodworking workshop",
        timestamp=datetime(2025, 6, 1),
    )


class TestVerifiedArtifact:
    """Substantive, relevant, plausibly-timed artifacts should verify."""

    def test_blog_post_verifies(self, mock_web, verifier, experience):
        mock_web.add_page(
            "https://medium.com/user1/my-woodworking-project",
            WebPage(
                url="https://medium.com/user1/my-woodworking-project",
                status_code=200,
                title="My First Woodworking Project",
                content_text=(
                    "After attending a woodworking workshop, I was inspired "
                    "to build my own bookshelf. I started with pine boards "
                    "and worked through the joinery techniques we learned. "
                    "The project took three weekends and taught me patience "
                    "and precision. Here are the steps I followed and what "
                    "I learned along the way about wood grain selection, "
                    "proper sanding technique, and finishing with natural "
                    "oils for a warm appearance."
                ),
                publish_date="2025-06-15",
                platform="medium",
                accessible=True,
            ),
        )

        artifact = Artifact(
            experience_id="exp1",
            user_id="user1",
            url="https://medium.com/user1/my-woodworking-project",
            user_claim="Blog post about my woodworking project",
        )

        result = verifier.verify(artifact, experience)

        assert result.url_accessible is True
        assert result.content_substantive is True
        assert result.timestamp_plausible is True
        assert result.relevance_score > 0.2
        assert result.status == "verified"

    def test_github_repo_verifies(self, mock_web, verifier):
        exp = Experience(
            id="exp2",
            description="Learning Python programming through online course",
            timestamp=datetime(2025, 3, 1),
        )

        mock_web.add_page(
            "https://github.com/user1/python-projects",
            WebPage(
                url="https://github.com/user1/python-projects",
                status_code=200,
                title="python-projects - My Python learning journey",
                content_text=(
                    "A collection of Python projects built while learning "
                    "programming through an online course. Includes data "
                    "analysis scripts, a simple web scraper, and a CLI "
                    "tool for tracking habits. Each project builds on the "
                    "skills learned in the previous one, demonstrating "
                    "progression from basic syntax to more complex patterns. "
                    "The repository also includes documentation and notes "
                    "about the learning process and key insights gained."
                ),
                publish_date="2025-04-10",
                platform="github",
                accessible=True,
            ),
        )

        artifact = Artifact(
            experience_id="exp2",
            url="https://github.com/user1/python-projects",
            user_claim="My GitHub repo with Python projects",
        )

        result = verifier.verify(artifact, exp)
        assert result.status == "verified"
        assert result.content_substantive is True


class TestInaccessibleURL:
    """URLs that can't be fetched should return 'inaccessible'."""

    def test_404_returns_inaccessible(self, verifier, experience):
        # MockWebClient returns inaccessible for unknown URLs
        artifact = Artifact(
            experience_id="exp1",
            url="https://example.com/doesnt-exist",
            user_claim="My blog post",
        )

        result = verifier.verify(artifact, experience)
        assert result.url_accessible is False
        assert result.status == "inaccessible"

    def test_network_error_returns_inaccessible(self, mock_web, verifier, experience):
        mock_web.add_page(
            "https://broken.example.com",
            WebPage(
                url="https://broken.example.com",
                accessible=False,
                error="Connection refused",
            ),
        )

        artifact = Artifact(
            experience_id="exp1",
            url="https://broken.example.com",
            user_claim="My project",
        )

        result = verifier.verify(artifact, experience)
        assert result.status == "inaccessible"


class TestTrivialContent:
    """Content that's too thin should NOT verify."""

    def test_too_short_is_unverified(self, mock_web, verifier, experience):
        mock_web.add_page(
            "https://x.com/user1/status/123",
            WebPage(
                url="https://x.com/user1/status/123",
                status_code=200,
                title="Post",
                content_text="Nice workshop today!",  # Too short
                platform="x",
                accessible=True,
            ),
        )

        artifact = Artifact(
            experience_id="exp1",
            url="https://x.com/user1/status/123",
            user_claim="My tweet about the workshop",
        )

        result = verifier.verify(artifact, experience)
        assert result.content_substantive is False
        assert result.status == "unverified"


class TestTimestampPlausibility:
    """Artifact dates far outside the experience window are suspicious."""

    def test_reasonable_timestamp_is_plausible(self, mock_web, verifier, experience):
        # Experience: June 2025, artifact: July 2025 → plausible
        mock_web.add_page(
            "https://example.com/post",
            WebPage(
                url="https://example.com/post",
                status_code=200,
                title="Woodworking Workshop Results",
                content_text="A detailed article about woodworking project " * 20,
                publish_date="2025-07-01",
                platform="web",
                accessible=True,
            ),
        )

        artifact = Artifact(experience_id="exp1", url="https://example.com/post")
        result = verifier.verify(artifact, experience)
        assert result.timestamp_plausible is True

    def test_no_timestamp_gives_benefit_of_doubt(self, mock_web, verifier, experience):
        mock_web.add_page(
            "https://example.com/no-date",
            WebPage(
                url="https://example.com/no-date",
                status_code=200,
                title="Woodworking Workshop Project",
                content_text="I built this after the woodworking workshop " * 20,
                publish_date=None,
                platform="web",
                accessible=True,
            ),
        )

        artifact = Artifact(experience_id="exp1", url="https://example.com/no-date")
        result = verifier.verify(artifact, experience)
        assert result.timestamp_plausible is True


class TestRelevanceScoring:
    """Artifacts should relate to the claimed experience."""

    def test_relevant_content_scores_high(self, mock_web, verifier, experience):
        mock_web.add_page(
            "https://example.com/relevant",
            WebPage(
                url="https://example.com/relevant",
                status_code=200,
                title="My Woodworking Workshop Experience",
                content_text=(
                    "After attending the woodworking workshop I was inspired "
                    "to build a project using the techniques we learned about "
                    "joinery and wood selection in the workshop sessions."
                    + " More content about woodworking and the project." * 10
                ),
                platform="web",
                accessible=True,
            ),
        )

        artifact = Artifact(
            experience_id="exp1",
            url="https://example.com/relevant",
            user_claim="Workshop project documentation",
        )
        result = verifier.verify(artifact, experience)
        assert result.relevance_score > 0.2

    def test_unrelated_content_scores_low(self, mock_web, verifier, experience):
        mock_web.add_page(
            "https://example.com/unrelated",
            WebPage(
                url="https://example.com/unrelated",
                status_code=200,
                title="Best Pizza Recipes 2025",
                content_text=(
                    "Here are the top pizza recipes for making authentic "
                    "Neapolitan pizza at home with a standard kitchen oven."
                    + " More pizza recipe content here." * 10
                ),
                platform="web",
                accessible=True,
            ),
        )

        artifact = Artifact(
            experience_id="exp1",
            url="https://example.com/unrelated",
            user_claim="My woodworking project",
        )
        result = verifier.verify(artifact, experience)
        assert result.relevance_score < 0.3


class TestDepthOverBreadth:
    """Consistent with the quality framework: a few substantive
    artifacts > many trivial ones."""

    def test_batch_verification(self, mock_web, verifier, experience):
        """Multiple artifacts verified as a batch."""
        for i in range(3):
            mock_web.add_page(
                f"https://example.com/post-{i}",
                WebPage(
                    url=f"https://example.com/post-{i}",
                    status_code=200,
                    title=f"Woodworking Project Part {i+1}",
                    content_text=(
                        f"Part {i+1} of my woodworking project documented "
                        "with photos and detailed build instructions for "
                        "the workshop-inspired bookshelf project from the "
                        "woodworking workshop I attended. "
                        + "Covering techniques in joinery and finishing. " * 5
                    ),
                    platform="web",
                    accessible=True,
                ),
            )

        artifacts = [
            Artifact(
                experience_id="exp1",
                url=f"https://example.com/post-{i}",
                user_claim=f"Build log part {i+1}",
            )
            for i in range(3)
        ]

        results = verifier.verify_batch(artifacts, experience)
        assert len(results) == 3
        verified_count = sum(1 for r in results if r.status == "verified")
        assert verified_count >= 2
