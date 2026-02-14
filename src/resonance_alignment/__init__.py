"""Resonance-based AI alignment framework -- the Improvement Axiom."""

__version__ = "0.3.0"

# Core models
from resonance_alignment.core.models import (
    Artifact,
    ArtifactVerification,
    AssessmentResult,
    Experience,
    ExtrapolationHypothesis,
    FollowUp,
    HorizonAssessment,
    IntentionSignal,
    PendingQuestion,
    TimeHorizon,
    TrajectoryEvidence,
    UserTrajectory,
    VectorSnapshot,
)

# Core components
from resonance_alignment.core.vector_tracker import VectorTracker
from resonance_alignment.core.intention_classifier import IntentionClassifier
from resonance_alignment.core.quality_assessor import QualityAssessor
from resonance_alignment.core.resonance_tracker import ResonanceTracker
from resonance_alignment.core.resonance_validator import ResonanceValidator
from resonance_alignment.core.temporal_evaluator import TemporalEvaluator
from resonance_alignment.core.propagation_tracker import PropagationTracker
from resonance_alignment.core.question_engine import QuestionEngine
from resonance_alignment.core.extrapolation_model import ExtrapolationModel
from resonance_alignment.core.web_client import (
    WebClient,
    HttpxWebClient,
    MockWebClient,
    WebPage,
    SearchResult,
)

# Safety
from resonance_alignment.safety.ouroboros_anchor import OuroborosAnchor
from resonance_alignment.safety.external_validator import ExternalValidator
from resonance_alignment.safety.artifact_verifier import ArtifactVerifier
from resonance_alignment.safety.human_verification import HumanVerification
from resonance_alignment.safety.constraints import SafetyConstraints
from resonance_alignment.safety.observable_action_policy import ObservableActionPolicy

# Explainability
from resonance_alignment.explainability.explainable_resonance import ExplainableResonance

# Orchestrator
from resonance_alignment.system import ResonanceAlignmentSystem

__all__ = [
    # Models
    "Artifact",
    "ArtifactVerification",
    "AssessmentResult",
    "Experience",
    "ExtrapolationHypothesis",
    "FollowUp",
    "HorizonAssessment",
    "IntentionSignal",
    "PendingQuestion",
    "TimeHorizon",
    "TrajectoryEvidence",
    "UserTrajectory",
    "VectorSnapshot",
    # Core
    "VectorTracker",
    "IntentionClassifier",
    "QualityAssessor",
    "ResonanceTracker",
    "ResonanceValidator",
    "TemporalEvaluator",
    "PropagationTracker",
    "QuestionEngine",
    "ExtrapolationModel",
    # Web access
    "WebClient",
    "HttpxWebClient",
    "MockWebClient",
    "WebPage",
    "SearchResult",
    # Safety
    "OuroborosAnchor",
    "ExternalValidator",
    "ArtifactVerifier",
    "HumanVerification",
    "SafetyConstraints",
    "ObservableActionPolicy",
    # Explainability
    "ExplainableResonance",
    # System
    "ResonanceAlignmentSystem",
]
