"""Core data models for the Improvement Axiom framework.

These models represent experiences, trajectories, and assessments as
evolving structures rather than static labels.  An experience recorded
at t=0 carries a *provisional* intent inference with low confidence.
As follow-ups, observations, and time accumulate, the confidence and
inference update -- the intent reveals itself over the long arc.

KEY PRINCIPLE: Creation and consumption are a neutral cycle (the
Ouroboros).  The framework does not judge acts -- it infers *intent*
from accumulated evidence.  A consumptive act with creative intent
(Scorsese watching films) looks identical at t=0 to one with
consumptive intent.  Only the long arc distinguishes them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional


def _utcnow() -> datetime:
    """Timezone-aware UTC now, replacing deprecated datetime.utcnow()."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class IntentionSignal(Enum):
    """Inferred intent behind a pattern of behaviour.

    These represent the framework's *inference* about what the evidence
    suggests, NOT a label on the activity itself.  A consumptive act
    (watching films) can have creative intent (Scorsese).  A creative
    act (producing content) can have consumptive intent (spam/fraud).

    Intent is hidden at t=0 and reveals itself over the long arc.
    """

    CREATIVE_INTENT = "creative"       # Evidence suggests creative intent
    CONSUMPTIVE_INTENT = "consumptive" # Evidence suggests consumptive intent
    MIXED = "mixed"                    # Evidence is ambiguous
    PENDING = "pending"                # Not enough evidence to infer intent


class TimeHorizon(Enum):
    """Expanding time horizons for evaluation.

    Each horizon represents a wider lens through which to judge whether
    an outcome is genuinely 'Better'.
    """

    IMMEDIATE = "immediate"          # t = 0, moment of experience
    SHORT_TERM = "short_term"        # hours to days
    MEDIUM_TERM = "medium_term"      # weeks to months
    LONG_TERM = "long_term"          # months to years
    GENERATIONAL = "generational"    # years to decades+


# Mapping from horizon to rough duration for scheduling questions.
HORIZON_DURATIONS: dict[TimeHorizon, timedelta] = {
    TimeHorizon.IMMEDIATE: timedelta(seconds=0),
    TimeHorizon.SHORT_TERM: timedelta(days=1),
    TimeHorizon.MEDIUM_TERM: timedelta(weeks=2),
    TimeHorizon.LONG_TERM: timedelta(days=90),
    TimeHorizon.GENERATIONAL: timedelta(days=365),
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FollowUp:
    """An observation or response recorded *after* an experience.

    Follow-ups are the primary evidence source for revealing *intent*.
    They answer the question: 'What happened next?'  Each follow-up
    makes the hidden intent slightly more visible.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    experience_id: str = ""
    timestamp: datetime = field(default_factory=_utcnow)
    source: str = "user_response"  # 'user_response' | 'behavioral' | 'system_observation'
    content: str = ""

    # The critical signals
    created_something: bool = False
    creation_description: str = ""
    shared_or_taught: bool = False
    inspired_further_action: bool = False

    # Graduated creation: 0.0 = nothing, 0.25 = sketched/started,
    # 0.5 = partial draft/prototype, 0.75 = substantial work,
    # 1.0 = completed and shipped.  When created_something is True
    # but creation_magnitude is 0.0, it defaults to 1.0 for backward
    # compatibility.
    creation_magnitude: float = 0.0


@dataclass
class VectorSnapshot:
    """A point-in-time measurement of inferred intent.

    - direction: -1.0 (consumptive intent) to +1.0 (creative intent)
    - magnitude:  0.0 (no signal) to 1.0 (strong signal)
    - confidence: 0.0 (no evidence) to 1.0 (extensive evidence)

    Direction reflects the framework's best inference of intent based
    on accumulated evidence, NOT a judgment of the activity itself.
    """

    timestamp: datetime = field(default_factory=_utcnow)
    direction: float = 0.0
    magnitude: float = 0.0
    confidence: float = 0.0
    horizon: TimeHorizon = TimeHorizon.IMMEDIATE


@dataclass
class HorizonAssessment:
    """Assessment of an experience at a single time horizon."""

    horizon: TimeHorizon = TimeHorizon.IMMEDIATE
    score: Optional[float] = None       # None = not yet evaluable
    evidence_count: int = 0
    notes: str = ""


@dataclass
class Experience:
    """A recorded experience with its *evolving* assessment.

    At t=0, ``provisional_intention`` is ``PENDING`` and
    ``intention_confidence`` is near zero.  As follow-ups accumulate,
    these update.  Classification is retrospective, not predictive.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    user_id: str = ""
    description: str = ""
    context: str = ""
    user_rating: float = 0.5
    timestamp: datetime = field(default_factory=_utcnow)

    # Evolving evidence
    follow_ups: list[FollowUp] = field(default_factory=list)
    vector_snapshots: list[VectorSnapshot] = field(default_factory=list)
    horizon_assessments: list[HorizonAssessment] = field(default_factory=list)

    # Provisional classification (updates over time)
    provisional_intention: IntentionSignal = IntentionSignal.PENDING
    intention_confidence: float = 0.0

    # Resonance & quality (initial measurement, may be revised)
    resonance_score: float = 0.0
    quality_score: float = 0.0
    quality_dimensions: dict[str, float] = field(default_factory=dict)

    # Propagation tracking
    propagated: bool = False
    propagation_events: list[str] = field(default_factory=list)

    # Matrix position (provisional)
    matrix_position: str = "Pending"


@dataclass
class UserTrajectory:
    """Aggregated trajectory for a user across all their experiences.

    This is the 'vector' -- direction + magnitude + compounding rate.
    """

    user_id: str = ""
    experiences: list[Experience] = field(default_factory=list)
    current_vector: VectorSnapshot = field(default_factory=VectorSnapshot)
    vector_history: list[VectorSnapshot] = field(default_factory=list)

    # Computed rates (updated as evidence accumulates)
    creation_rate: float = 0.0        # fraction of experiences that led to creation
    propagation_rate: float = 0.0     # fraction of resonance events that propagated
    compounding_direction: float = 0.0  # second derivative: is the vector accelerating?

    @property
    def experience_count(self) -> int:
        return len(self.experiences)

    @property
    def has_history(self) -> bool:
        return self.experience_count > 0


@dataclass
class PendingQuestion:
    """A question to be asked at a future time to reveal the vector.

    Instead of classifying at t=0, the system generates questions to
    ask at appropriate intervals.  The answers feed back into the
    VectorTracker.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    experience_id: str = ""
    user_id: str = ""
    question: str = ""
    ask_after: datetime = field(default_factory=_utcnow)
    horizon: TimeHorizon = TimeHorizon.SHORT_TERM
    asked: bool = False
    response: Optional[FollowUp] = None


# ---------------------------------------------------------------------------
# Artifact Verification (Defence Layer 2 -- breaks circular self-validation)
# ---------------------------------------------------------------------------

@dataclass
class Artifact:
    """An externally-hosted artifact the user presents as evidence of creation.

    This is PORTFOLIO-BASED verification: the person presents → the
    system confirms.  NOT surveillance: the system watches → the person.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    experience_id: str = ""
    user_id: str = ""
    url: str = ""
    platform: str = ""          # 'x', 'github', 'medium', 'wiki', etc.
    user_claim: str = ""        # what the user says this artifact is
    submitted_at: datetime = field(default_factory=_utcnow)


@dataclass
class ArtifactVerification:
    """Result of verifying an externally-hosted artifact."""

    artifact_id: str = ""
    url_accessible: bool = False
    content_summary: str = ""
    content_substantive: bool = False  # real substance, not trivial?
    timestamp_plausible: bool = False  # artifact date makes sense?
    relevance_score: float = 0.0      # 0-1, how related to claimed experience
    verified_at: datetime = field(default_factory=_utcnow)
    notes: str = ""

    # Overall status
    status: str = "pending"  # 'verified' | 'unverified' | 'suspicious' | 'inaccessible'


# ---------------------------------------------------------------------------
# Extrapolation Model (Defence Layer 5 -- evidence-based hypothesis generation)
# ---------------------------------------------------------------------------

@dataclass
class ExtrapolationHypothesis:
    """An evidence-based hypothesis about where an action typically leads.

    NOT a judgment.  A mentor saying: 'Here is what the evidence shows.
    Most who did X ended up at Y, but some reached Z.  Here is what
    distinguished them.  What do you want to do?'
    """

    action_pattern: str = ""              # what type of action
    typical_trajectory: str = ""          # what most people end up doing
    probability_estimate: float = 0.0     # rough, 0-1, never deterministic
    distinguishing_factors: list[str] = field(default_factory=list)
    notable_exceptions: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)   # URLs / citations
    empowerment_note: str = ""            # always empowers individual choice
    confidence: float = 0.0               # confidence in this hypothesis


@dataclass
class TrajectoryEvidence:
    """Aggregated evidence from public sources about action outcomes."""

    query: str = ""
    hypotheses: list[ExtrapolationHypothesis] = field(default_factory=list)
    search_timestamp: datetime = field(default_factory=_utcnow)
    total_sources_found: int = 0
    note: str = ""  # caveats about the evidence


# ---------------------------------------------------------------------------
# Assessment Result
# ---------------------------------------------------------------------------

@dataclass
class AssessmentResult:
    """Complete result from the processing pipeline.

    Combines the provisional assessment with questions for later,
    trajectory context, artifact verifications, extrapolation evidence,
    and explicit confidence / horizon markers.
    """

    experience: Experience = field(default_factory=Experience)
    trajectory: UserTrajectory = field(default_factory=UserTrajectory)
    pending_questions: list[PendingQuestion] = field(default_factory=list)
    arc_trend: str = "insufficient_data"  # 'improving' | 'declining' | 'stable' | 'insufficient_data'
    recommendations: list[str] = field(default_factory=list)
    explanation: dict = field(default_factory=dict)

    # Defence layers 2 & 5 (require internet)
    artifact_verifications: list[ArtifactVerification] = field(default_factory=list)
    trajectory_evidence: Optional[TrajectoryEvidence] = None

    # Agent-mediated evidence (new in v0.4.0 -- requires AgentWebClient)
    quality_evidence: Optional[dict] = None          # external quality signals
    vector_probability: Optional[dict] = None        # creative vs consumptive intent probability

    @property
    def is_provisional(self) -> bool:
        """True when there isn't enough evidence for confident classification."""
        return self.experience.intention_confidence < 0.5
