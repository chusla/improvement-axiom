"""Evidence request/response protocol for LLM-mediated web access.

The Improvement Axiom framework needs external evidence for Defence
Layers 2 (Artifact Verification) and 5 (Evidence-Based Extrapolation),
plus new capabilities for quality evidence and vector probability.

Rather than doing crude keyword-matching on raw HTML (which an LLM
does natively and far better), the framework defines WHAT evidence
it needs as structured requests.  The agent (LLM) fulfills them.

This decouples the framework from any specific web-access method:
- AgentWebClient: LLM agent fulfills requests via tool use
- HttpxWebClient: standalone HTTP fallback (existing)
- MockWebClient: testing with canned responses (existing)

EVIDENCE REQUEST TYPES:

1. ARTIFACT_VERIFY -- "Is this URL substantive, real, and relevant?"
   The agent fetches the URL, reads the content, and returns a
   structured assessment far richer than regex HTML parsing.

2. TRAJECTORY_SEARCH -- "What do people who do X typically go on to do?"
   The agent searches public evidence and returns structured hypotheses
   with citations, distinguishing factors, and empowerment notes.

3. QUALITY_EVIDENCE -- "What is the external quality signal for this?"
   The agent searches for reviews, mentions, engagement depth, and
   returns a structured quality assessment.

4. VECTOR_PROBABILITY -- "What is the probability this vector goes
   creative vs consumptive based on public evidence?"
   The agent searches for research/data on action outcomes and returns
   a structured probability assessment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional


class EvidenceType(Enum):
    """Types of evidence the framework can request."""

    ARTIFACT_VERIFY = "artifact_verify"
    TRAJECTORY_SEARCH = "trajectory_search"
    QUALITY_EVIDENCE = "quality_evidence"
    VECTOR_PROBABILITY = "vector_probability"


@dataclass
class EvidenceRequest:
    """What the framework needs from the outside world.

    The agent (LLM) interprets this and uses its tools (web search,
    page fetching, reasoning) to produce an EvidenceResponse.
    """

    request_type: EvidenceType
    query: str                          # natural language query for the agent
    context: dict[str, Any] = field(default_factory=dict)  # structured context
    url: str = ""                       # for ARTIFACT_VERIFY: the URL to check
    experience_description: str = ""    # what the user did
    user_claim: str = ""                # what the user claims (for artifacts)

    def to_agent_prompt(self) -> str:
        """Convert to a natural language prompt for the LLM agent.

        This is what gets sent to the agent's tool use system.
        """
        if self.request_type == EvidenceType.ARTIFACT_VERIFY:
            return (
                f"Verify this URL as evidence of creative output: {self.url}\n"
                f"User claims: {self.user_claim}\n"
                f"Related experience: {self.experience_description}\n\n"
                f"Please fetch and read the page, then assess:\n"
                f"1. Is the URL accessible and the content real (not a 404/placeholder)?\n"
                f"2. Is the content substantive (real creative work, not trivial)?\n"
                f"3. Does the publication date make sense relative to the claimed experience?\n"
                f"4. How relevant is the content to the claimed experience (0.0-1.0)?\n"
                f"5. Brief summary of what the content actually is."
            )
        elif self.request_type == EvidenceType.TRAJECTORY_SEARCH:
            return (
                f"Search for public evidence about what typically happens when "
                f"someone does: {self.experience_description}\n\n"
                f"Find research, articles, documented outcomes, and case studies.\n"
                f"For each finding, provide:\n"
                f"1. The typical trajectory (what most people end up doing)\n"
                f"2. Probability estimate (rough, 0-1)\n"
                f"3. Distinguishing factors (what separates different outcomes)\n"
                f"4. Notable exceptions (cases that defied the pattern)\n"
                f"5. Source URLs\n"
                f"6. An empowering note (evidence, not judgment)"
            )
        elif self.request_type == EvidenceType.QUALITY_EVIDENCE:
            return (
                f"Search for external quality signals about: "
                f"{self.experience_description}\n\n"
                f"Look for:\n"
                f"1. Expert reviews or assessments of this type of activity\n"
                f"2. Depth of engagement metrics (devoted fans vs shallow likes)\n"
                f"3. Evidence of skill development or mastery pathways\n"
                f"4. Community quality signals (are practitioners serious?)\n"
                f"5. Durability evidence (does engagement persist over time?)\n"
                f"Return a quality score (0.0-1.0), confidence, and source URLs."
            )
        elif self.request_type == EvidenceType.VECTOR_PROBABILITY:
            return (
                f"Based on public research and evidence, what is the probability "
                f"that someone doing '{self.experience_description}' ends up on "
                f"a creative vs consumptive trajectory?\n\n"
                f"Search for:\n"
                f"1. Research on outcomes of this activity over time\n"
                f"2. Statistics on what percentage go creative vs stay consumptive\n"
                f"3. Key inflection points that distinguish the paths\n"
                f"4. Time horizon data (when does the vector typically resolve?)\n"
                f"Return: creative_probability (0-1), consumptive_probability (0-1), "
                f"key factors, and source URLs."
            )
        return self.query


@dataclass
class EvidenceResponse:
    """What the agent provides back to the framework.

    Each evidence type populates different fields.  The framework
    extracts what it needs based on the request type.
    """

    request_type: EvidenceType
    success: bool = True
    error: str = ""

    # Common fields
    source_urls: list[str] = field(default_factory=list)
    summary: str = ""
    confidence: float = 0.0             # agent's confidence in its response
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ARTIFACT_VERIFY fields
    url_accessible: bool = False
    content_substantive: bool = False
    content_summary: str = ""
    timestamp_plausible: bool = False
    relevance_score: float = 0.0

    # TRAJECTORY_SEARCH fields
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    # Each hypothesis: {action_pattern, typical_trajectory,
    #   probability_estimate, distinguishing_factors, notable_exceptions,
    #   sources, empowerment_note, confidence}

    # QUALITY_EVIDENCE fields
    quality_score: float = 0.0
    quality_dimensions: dict[str, float] = field(default_factory=dict)
    # {signal_depth, recursiveness, durability, growth_enabling, authenticity}

    # VECTOR_PROBABILITY fields
    creative_probability: float = 0.0
    consumptive_probability: float = 0.0
    key_factors: list[str] = field(default_factory=list)
    resolution_horizon: str = ""        # "weeks", "months", "years"


# Type alias for the callback function the agent provides
EvidenceFulfiller = Callable[[EvidenceRequest], EvidenceResponse]
