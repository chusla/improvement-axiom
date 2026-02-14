"""Tests for the evidence request/response protocol and AgentWebClient."""

import pytest

from resonance_alignment.core.evidence import (
    EvidenceType,
    EvidenceRequest,
    EvidenceResponse,
)
from resonance_alignment.core.agent_web_client import AgentWebClient


class TestEvidenceRequest:
    """EvidenceRequest should produce clear agent prompts."""

    def test_artifact_verify_prompt(self):
        req = EvidenceRequest(
            request_type=EvidenceType.ARTIFACT_VERIFY,
            query="verify artifact",
            url="https://example.com/post",
            experience_description="wrote a blog about cooking",
            user_claim="This is my blog post about the recipes I learned",
        )
        prompt = req.to_agent_prompt()
        assert "https://example.com/post" in prompt
        assert "cooking" in prompt.lower() or "blog" in prompt.lower()
        assert "substantive" in prompt.lower()

    def test_trajectory_search_prompt(self):
        req = EvidenceRequest(
            request_type=EvidenceType.TRAJECTORY_SEARCH,
            query="what happens when someone plays video games",
            experience_description="played video games all weekend",
        )
        prompt = req.to_agent_prompt()
        assert "video games" in prompt.lower()
        assert "trajectory" in prompt.lower() or "typically" in prompt.lower()

    def test_quality_evidence_prompt(self):
        req = EvidenceRequest(
            request_type=EvidenceType.QUALITY_EVIDENCE,
            query="quality of local woodworking",
            experience_description="built a wooden shelf for my kitchen",
        )
        prompt = req.to_agent_prompt()
        assert "quality" in prompt.lower()
        assert "wooden shelf" in prompt.lower() or "woodworking" in prompt.lower()

    def test_vector_probability_prompt(self):
        req = EvidenceRequest(
            request_type=EvidenceType.VECTOR_PROBABILITY,
            query="video game trajectory",
            experience_description="playing competitive chess online",
        )
        prompt = req.to_agent_prompt()
        assert "creative" in prompt.lower()
        assert "consumptive" in prompt.lower()
        assert "chess" in prompt.lower()


class TestAgentWebClient:
    """AgentWebClient should delegate to the fulfiller callback."""

    @staticmethod
    def _mock_fulfiller(request: EvidenceRequest) -> EvidenceResponse:
        """Mock agent that returns canned responses."""
        if request.request_type == EvidenceType.ARTIFACT_VERIFY:
            return EvidenceResponse(
                request_type=EvidenceType.ARTIFACT_VERIFY,
                success=True,
                url_accessible=True,
                content_substantive=True,
                content_summary="A detailed blog post about cooking techniques",
                relevance_score=0.85,
                source_urls=["https://example.com/post"],
                confidence=0.9,
            )
        elif request.request_type == EvidenceType.TRAJECTORY_SEARCH:
            return EvidenceResponse(
                request_type=EvidenceType.TRAJECTORY_SEARCH,
                success=True,
                summary="Research shows varied outcomes for gaming",
                source_urls=["https://research.com/study1"],
                hypotheses=[{
                    "action_pattern": "playing video games",
                    "typical_trajectory": "Most remain consumers",
                    "probability_estimate": 0.7,
                    "sources": ["https://research.com/study1"],
                }],
                confidence=0.6,
            )
        elif request.request_type == EvidenceType.QUALITY_EVIDENCE:
            return EvidenceResponse(
                request_type=EvidenceType.QUALITY_EVIDENCE,
                success=True,
                quality_score=0.75,
                quality_dimensions={"signal_depth": 0.8, "durability": 0.7},
                confidence=0.7,
            )
        elif request.request_type == EvidenceType.VECTOR_PROBABILITY:
            return EvidenceResponse(
                request_type=EvidenceType.VECTOR_PROBABILITY,
                success=True,
                creative_probability=0.3,
                consumptive_probability=0.7,
                key_factors=["intentional practice", "community engagement"],
                resolution_horizon="months",
                confidence=0.5,
            )
        return EvidenceResponse(
            request_type=request.request_type,
            success=False,
            error="Unknown request type",
        )

    def test_fetch_page_delegates(self):
        client = AgentWebClient(fulfiller=self._mock_fulfiller)
        page = client.fetch_page("https://example.com/post")

        assert page.accessible is True
        assert "blog post" in page.content_text.lower() or "cooking" in page.content_text.lower()

    def test_search_delegates(self):
        client = AgentWebClient(fulfiller=self._mock_fulfiller)
        results = client.search("video games outcomes")

        assert len(results) >= 1
        assert any("research.com" in r.url for r in results)

    def test_verify_artifact_direct(self):
        client = AgentWebClient(fulfiller=self._mock_fulfiller)
        resp = client.verify_artifact(
            url="https://example.com/post",
            experience_description="cooking blog",
            user_claim="My blog post",
        )

        assert resp.success is True
        assert resp.url_accessible is True
        assert resp.relevance_score > 0.5

    def test_assess_quality_direct(self):
        client = AgentWebClient(fulfiller=self._mock_fulfiller)
        resp = client.assess_quality("built a wooden shelf")

        assert resp.success is True
        assert resp.quality_score > 0.5
        assert "signal_depth" in resp.quality_dimensions

    def test_assess_vector_probability_direct(self):
        client = AgentWebClient(fulfiller=self._mock_fulfiller)
        resp = client.assess_vector_probability("playing chess online")

        assert resp.success is True
        assert resp.creative_probability + resp.consumptive_probability <= 1.01
        assert len(resp.key_factors) > 0

    def test_failed_fulfiller(self):
        def failing_fulfiller(req: EvidenceRequest) -> EvidenceResponse:
            return EvidenceResponse(
                request_type=req.request_type,
                success=False,
                error="Network error",
            )

        client = AgentWebClient(fulfiller=failing_fulfiller)
        page = client.fetch_page("https://example.com")

        assert page.accessible is False
        assert "Network error" in page.error


class TestGraduatedCreation:
    """Graduated creation_magnitude should influence scoring."""

    def test_partial_creation_lower_signal(self):
        """A sketch (0.25) should contribute less than a shipped project (1.0)."""
        from resonance_alignment.core.vector_tracker import VectorTracker
        from resonance_alignment.core.models import FollowUp
        from datetime import timedelta

        tracker = VectorTracker()

        # User A: shipped a complete project
        exp_a = tracker.record_experience("user_a", "took a photography class", "", 0.7)
        tracker.record_follow_up("user_a", exp_a.id, FollowUp(
            timestamp=exp_a.timestamp + timedelta(days=7),
            created_something=True,
            creation_description="Published a photo essay",
            creation_magnitude=1.0,  # completed and shipped
        ))

        # User B: just started sketching ideas
        exp_b = tracker.record_experience("user_b", "took a photography class", "", 0.7)
        tracker.record_follow_up("user_b", exp_b.id, FollowUp(
            timestamp=exp_b.timestamp + timedelta(days=7),
            created_something=True,
            creation_description="Started collecting photo ideas",
            creation_magnitude=0.25,  # just started
        ))

        traj_a = tracker.get_trajectory("user_a")
        traj_b = tracker.get_trajectory("user_b")

        # Full creation should produce a stronger creative vector
        assert traj_a.current_vector.direction > traj_b.current_vector.direction

    def test_backward_compatible_default(self):
        """created_something=True with magnitude=0.0 should default to 1.0."""
        from resonance_alignment.core.vector_tracker import VectorTracker
        from resonance_alignment.core.models import FollowUp
        from datetime import timedelta

        tracker = VectorTracker()
        exp = tracker.record_experience("user", "did something", "", 0.7)
        tracker.record_follow_up("user", exp.id, FollowUp(
            timestamp=exp.timestamp + timedelta(days=3),
            created_something=True,
            creation_description="Made something",
            # creation_magnitude not set → defaults to 0.0, treated as 1.0
        ))

        traj = tracker.get_trajectory("user")
        assert traj.current_vector.direction > 0  # should still register creative
