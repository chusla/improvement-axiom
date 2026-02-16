"""Agent-mediated web client -- delegates web access to the LLM agent.

When the framework is used with an LLM agent (the primary use case),
the agent has far superior web search and content understanding
capabilities compared to raw HTTP + regex parsing.

AgentWebClient implements the WebClient ABC but delegates all web
operations to the agent via a callback function (EvidenceFulfiller).
The agent uses its native tools (web search, page fetching, reasoning)
and returns structured evidence.

This also exposes a richer evidence API beyond the basic WebClient
interface, enabling the new quality evidence and vector probability
features that leverage the agent's understanding.

Usage:
    def my_agent_callback(request: EvidenceRequest) -> EvidenceResponse:
        # Agent uses its tools to fulfill the request
        ...

    client = AgentWebClient(fulfiller=my_agent_callback)
    system = ResonanceAlignmentSystem(web_client=client)
"""

from __future__ import annotations

from resonance_alignment.core.web_client import (
    WebClient,
    WebPage,
    SearchResult,
)
from resonance_alignment.core.evidence import (
    EvidenceType,
    EvidenceFulfiller,
    EvidenceRequest,
    EvidenceResponse,
)


class AgentWebClient(WebClient):
    """WebClient implementation that delegates to an LLM agent.

    The agent is provided as a callback (EvidenceFulfiller) that
    receives an EvidenceRequest and returns an EvidenceResponse.

    For the basic WebClient interface (fetch_page, search), the
    agent's responses are translated back into WebPage/SearchResult
    objects for backward compatibility with existing components.

    For the richer evidence API (request_evidence), the full
    EvidenceResponse is returned directly.
    """

    def __init__(self, fulfiller: EvidenceFulfiller) -> None:
        """Initialise with an agent callback.

        Args:
            fulfiller: Callable that takes an EvidenceRequest and
                returns an EvidenceResponse.  This is typically
                wired to the LLM agent's tool-use system.
        """
        self._fulfiller = fulfiller

    # ------------------------------------------------------------------
    # WebClient ABC implementation (backward compatibility)
    # ------------------------------------------------------------------

    def fetch_page(self, url: str) -> WebPage:
        """Fetch a page by delegating to the agent.

        The agent reads and understands the page far better than
        raw HTTP + regex extraction.
        """
        request = EvidenceRequest(
            request_type=EvidenceType.ARTIFACT_VERIFY,
            query=f"Fetch and summarize the content at: {url}",
            url=url,
        )
        response = self._fulfiller(request)

        if not response.success:
            return WebPage(url=url, accessible=False, error=response.error)

        return WebPage(
            url=url,
            status_code=200 if response.url_accessible else 404,
            title=response.content_summary[:100] if response.content_summary else "",
            content_text=response.content_summary,
            content_length=len(response.content_summary),
            platform="agent",
            accessible=response.url_accessible,
        )

    def search(
        self, query: str, num_results: int = 10
    ) -> list[SearchResult]:
        """Search by delegating to the agent.

        The agent can use its native search tools and return
        results with full contextual understanding.
        """
        request = EvidenceRequest(
            request_type=EvidenceType.TRAJECTORY_SEARCH,
            query=query,
            experience_description=query,
        )
        response = self._fulfiller(request)

        if not response.success:
            return []

        # Convert agent's response into SearchResult objects
        results: list[SearchResult] = []
        for url in response.source_urls[:num_results]:
            results.append(SearchResult(
                url=url,
                title="",
                snippet=response.summary[:200] if response.summary else "",
                source="agent",
            ))

        # Also convert hypotheses' sources into results
        for hyp in response.hypotheses[:num_results]:
            for source_url in hyp.get("sources", []):
                if source_url not in {r.url for r in results}:
                    results.append(SearchResult(
                        url=source_url,
                        title=hyp.get("action_pattern", ""),
                        snippet=hyp.get("typical_trajectory", ""),
                        source="agent",
                    ))

        return results[:num_results]

    # ------------------------------------------------------------------
    # Rich evidence API (new capabilities)
    # ------------------------------------------------------------------

    def request_evidence(self, request: EvidenceRequest) -> EvidenceResponse:
        """Request evidence directly using the full protocol.

        This bypasses the WebClient ABC and returns the full
        EvidenceResponse, enabling richer evidence types like
        quality assessment and vector probability.
        """
        return self._fulfiller(request)

    def verify_artifact(
        self,
        url: str,
        experience_description: str,
        user_claim: str,
    ) -> EvidenceResponse:
        """Verify an artifact using the agent's understanding.

        Returns a much richer verification than regex-based parsing.
        """
        request = EvidenceRequest(
            request_type=EvidenceType.ARTIFACT_VERIFY,
            query=f"Verify artifact at {url}",
            url=url,
            experience_description=experience_description,
            user_claim=user_claim,
        )
        return self._fulfiller(request)

    def assess_quality(
        self, experience_description: str
    ) -> EvidenceResponse:
        """Get external quality evidence from the agent."""
        request = EvidenceRequest(
            request_type=EvidenceType.QUALITY_EVIDENCE,
            query=f"Quality evidence for: {experience_description}",
            experience_description=experience_description,
        )
        return self._fulfiller(request)

    def assess_vector_probability(
        self, experience_description: str
    ) -> EvidenceResponse:
        """Get vector probability evidence from the agent."""
        request = EvidenceRequest(
            request_type=EvidenceType.VECTOR_PROBABILITY,
            query=f"Vector probability for: {experience_description}",
            experience_description=experience_description,
        )
        return self._fulfiller(request)
