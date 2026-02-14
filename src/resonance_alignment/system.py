"""Main orchestrator for the Improvement Axiom framework.

Three entry points:

1. ``process_experience()`` -- Record and provisionally assess a new
   experience.  At t=0, confidence is LOW.  The system returns its
   best guess along with *questions to ask later* so the vector can
   reveal itself over time.

2. ``process_follow_up()`` -- Record what happened *after* an experience.
   This is how confidence rises and classification evolves.  Each
   follow-up shifts the vector based on evidence: did the experience
   lead to creation, sharing, teaching?  Or did it terminate in
   consumption?

3. ``submit_artifact()`` -- User presents an externally-hosted artifact
   (URL) as evidence of creation.  The system fetches and verifies it
   via the internet (Defence Layer 2).

The key principle: the system never labels an activity as inherently
creative or consumptive.  It watches the *trajectory* -- what
activities lead to over time.  Two kids playing the same game are
indistinguishable at t=0; the vector diverges over weeks, months,
years.  Initial degrees may be slight, but over the long arc these
differences compound tremendously.

INTERNET ACCESS:
The system optionally accepts a WebClient for internet-dependent
defence layers (Artifact Verification and Evidence-Based Extrapolation).
Without it, the system operates in offline/degraded mode using the
three local defence layers (Vector Tracking, Temporal Evaluation,
Propagation Tracking).
"""

from __future__ import annotations

from resonance_alignment.core.models import (
    Artifact,
    ArtifactVerification,
    AssessmentResult,
    Experience,
    FollowUp,
    IntentionSignal,
    PendingQuestion,
    UserTrajectory,
)
from resonance_alignment.core.vector_tracker import VectorTracker
from resonance_alignment.core.intention_classifier import IntentionClassifier
from resonance_alignment.core.quality_assessor import QualityAssessor
from resonance_alignment.core.resonance_tracker import ResonanceTracker
from resonance_alignment.core.resonance_validator import ResonanceValidator
from resonance_alignment.core.temporal_evaluator import TemporalEvaluator
from resonance_alignment.core.propagation_tracker import PropagationTracker
from resonance_alignment.core.question_engine import QuestionEngine
from resonance_alignment.core.web_client import WebClient
from resonance_alignment.safety.ouroboros_anchor import OuroborosAnchor
from resonance_alignment.safety.external_validator import ExternalValidator
from resonance_alignment.safety.constraints import SafetyConstraints
from resonance_alignment.explainability.explainable_resonance import ExplainableResonance


QUADRANTS = {
    ("High", "Creative"): "Optimal (Target)",
    ("High", "Consumptive"): "Hedonism (WALL-E)",
    ("Low", "Creative"): "Slop (Low Quality Output)",
    ("Low", "Consumptive"): "Junk Food (Minimal Existence)",
    ("High", "Mixed"): "Transitional (High Quality)",
    ("Low", "Mixed"): "Transitional (Low Quality)",
    ("High", "Pending"): "Pending (High Quality, Vector Unknown)",
    ("Low", "Pending"): "Pending (Low Quality, Vector Unknown)",
}


class ResonanceAlignmentSystem:
    """Top-level system implementing the Improvement Axiom.

    Processes experiences through a vector-based pipeline that:
    - Withholds judgment at t=0 (returns provisional + questions)
    - Accepts follow-up evidence that reveals the true vector
    - Evaluates across expanding time horizons (the 'long arc')
    - Checks whether resonance propagates into creation
    - Detects trajectory drift and unhealthy Ouroboros cycles
    """

    def __init__(
        self,
        web_client: WebClient | None = None,
        storage: "StorageBackend | None" = None,
    ) -> None:
        """Initialise the Improvement Axiom system.

        Args:
            web_client: Optional WebClient for internet access.  Enables
                Defence Layers 2 (Artifact Verification) and 5
                (Evidence-Based Extrapolation).  If None, the system
                operates in offline/degraded mode using the three local
                defence layers.  Use AgentWebClient when an LLM agent
                is available for superior web understanding.
            storage: Optional StorageBackend for trajectory persistence.
                Without this, all data is in-memory only (lost on restart).
                Use SupabaseStorage for production persistence.
        """
        self._storage = storage

        # Core components
        self.vector_tracker = VectorTracker(storage=storage)
        self.intention_classifier = IntentionClassifier()
        self.quality_assessor = QualityAssessor()
        self.resonance_tracker = ResonanceTracker()
        self.validator = ResonanceValidator()
        self.temporal_evaluator = TemporalEvaluator()
        self.propagation_tracker = PropagationTracker()
        self.question_engine = QuestionEngine()

        # Safety & explainability (ExternalValidator gets web access)
        self.external_validator = ExternalValidator(web_client)
        self.ouroboros_anchor = OuroborosAnchor()
        self.constraints = SafetyConstraints()
        self.explainer = ExplainableResonance()

        # Pending questions store
        self.pending_questions: list[PendingQuestion] = []

    @classmethod
    def from_env(cls) -> "ResonanceAlignmentSystem":
        """Create a configured system from environment variables.

        Reads SUPABASE_URL/SUPABASE_KEY for storage.  Convenience wrapper
        around ``resonance_alignment.config.from_env()``.
        """
        from resonance_alignment.config import from_env as _from_env
        return _from_env()

    @property
    def has_web_access(self) -> bool:
        """True if the system has internet access for external verification."""
        return self.external_validator.has_web_access

    # ------------------------------------------------------------------
    # Entry Point 1: New Experience
    # ------------------------------------------------------------------

    def process_experience(
        self,
        user_id: str,
        experience_description: str,
        user_rating: float,
        context: str,
    ) -> AssessmentResult:
        """Process a new experience.  Returns a PROVISIONAL assessment.

        At t=0, the system:
        1. Records the experience and computes a provisional vector.
        2. Measures quality and resonance (these are more immediately
           assessable than intention).
        3. Classifies intention *provisionally* with LOW confidence.
        4. Generates follow-up questions for later.
        5. Returns everything with explicit confidence markers.
        """
        # 1. Record experience and get provisional vector
        experience = self.vector_tracker.record_experience(
            user_id=user_id,
            description=experience_description,
            context=context,
            user_rating=user_rating,
        )
        trajectory = self.vector_tracker.get_trajectory(user_id)

        # 2. Quality assessment (evidence-aware; at t=0 uses self-report)
        quality_score, dimensions = self.quality_assessor.assess_quality(
            experience, trajectory
        )
        experience.quality_score = quality_score
        experience.quality_dimensions = dimensions

        # 3. Resonance measurement (raw signal; validated later)
        resonance_score = self.resonance_tracker.measure_resonance(experience)
        experience.resonance_score = resonance_score

        # 4. Intention classification (vector-aware, provisional)
        signal, confidence = self.intention_classifier.classify(
            experience, trajectory
        )
        experience.provisional_intention = signal
        experience.intention_confidence = confidence

        # 5. Temporal evaluation (most horizons will be 'pending')
        horizon_assessments = self.temporal_evaluator.evaluate(
            experience, trajectory
        )
        experience.horizon_assessments = horizon_assessments

        # 6. Validate resonance
        validated_resonance = self.validator.validate(
            experience, trajectory, horizon_assessments
        )
        experience.resonance_score = validated_resonance

        # 7. Matrix position (provisional)
        experience.matrix_position = self._calculate_matrix_position(
            quality_score, signal
        )

        # 8. Drift check (against trajectory, not static lists)
        drift_valid, drift_msg = self.ouroboros_anchor.validate_classification(
            experience, trajectory
        )

        # 9. Ouroboros health check
        cycle_healthy, cycle_msg = self.ouroboros_anchor.check_ouroboros_health(
            trajectory
        )

        # 10. Generate follow-up questions
        questions = self.question_engine.generate_questions(experience, trajectory)
        self.pending_questions.extend(questions)

        # 11. Generate recommendations
        recommendations = self._generate_recommendations(
            experience, trajectory, drift_valid, cycle_healthy
        )

        # 12. Build explanation
        explanation = self._build_explanation(
            experience, trajectory, horizon_assessments,
            drift_valid, drift_msg, cycle_healthy, cycle_msg,
        )

        # 13. Determine arc trend
        arc_trend = self.temporal_evaluator.compute_arc_trend(horizon_assessments)

        # 14. Evidence-based extrapolation (Defence Layer 5, requires internet)
        trajectory_evidence = self.external_validator.extrapolate(
            experience, trajectory
        )

        # 15. Agent-mediated evidence (quality + vector probability)
        quality_evidence = None
        vector_probability = None
        quality_resp = self.external_validator.assess_external_quality(experience)
        if quality_resp is not None and quality_resp.success:
            quality_evidence = {
                "score": quality_resp.quality_score,
                "dimensions": quality_resp.quality_dimensions,
                "confidence": quality_resp.confidence,
                "sources": quality_resp.source_urls,
                "summary": quality_resp.summary,
            }
        vector_resp = self.external_validator.assess_vector_probability(experience)
        if vector_resp is not None and vector_resp.success:
            vector_probability = {
                "creative_probability": vector_resp.creative_probability,
                "consumptive_probability": vector_resp.consumptive_probability,
                "key_factors": vector_resp.key_factors,
                "resolution_horizon": vector_resp.resolution_horizon,
                "confidence": vector_resp.confidence,
                "sources": vector_resp.source_urls,
            }

        return AssessmentResult(
            experience=experience,
            trajectory=trajectory,
            pending_questions=questions,
            arc_trend=arc_trend,
            recommendations=recommendations,
            explanation=explanation,
            trajectory_evidence=trajectory_evidence,
            quality_evidence=quality_evidence,
            vector_probability=vector_probability,
        )

    # ------------------------------------------------------------------
    # Entry Point 2: Follow-Up
    # ------------------------------------------------------------------

    def process_follow_up(
        self,
        user_id: str,
        experience_id: str,
        follow_up: FollowUp,
    ) -> AssessmentResult | None:
        """Process follow-up evidence for a previously recorded experience.

        This is how the vector reveals itself.  Each follow-up raises
        confidence and may shift the classification.

        Args:
            user_id: The user who had the experience.
            experience_id: ID of the original experience.
            follow_up: The follow-up observation.

        Returns:
            Updated AssessmentResult, or None if experience not found.
        """
        # 1. Record follow-up in VectorTracker (updates vector)
        experience = self.vector_tracker.record_follow_up(
            user_id, experience_id, follow_up
        )
        if experience is None:
            return None

        trajectory = self.vector_tracker.get_trajectory(user_id)

        # 2. If creation happened, record in PropagationTracker
        if follow_up.created_something:
            self.propagation_tracker.record_creation_event(
                user_id=user_id,
                description=follow_up.creation_description,
                inspired_by_experience_id=experience_id,
            )
            # Update trajectory propagation rate
            trajectory.propagation_rate = (
                self.propagation_tracker.compute_propagation_rate(trajectory)
            )

        # 3. Re-assess quality with new evidence (follow-ups change
        #    signal depth, recursiveness, durability, etc.)
        quality_score, dimensions = self.quality_assessor.assess_quality(
            experience, trajectory
        )
        experience.quality_score = quality_score
        experience.quality_dimensions = dimensions

        # 4. Re-measure resonance with evidence (depth of action
        #    calibrates the raw self-report signal)
        resonance_score = self.resonance_tracker.measure_resonance(experience)
        experience.resonance_score = resonance_score

        # 5. Reclassify intention with new evidence
        signal, confidence = self.intention_classifier.classify(
            experience, trajectory
        )
        experience.provisional_intention = signal
        experience.intention_confidence = confidence

        # 6. Re-evaluate temporal horizons
        horizon_assessments = self.temporal_evaluator.evaluate(
            experience, trajectory
        )
        experience.horizon_assessments = horizon_assessments

        # 7. Revalidate resonance with temporal + propagation evidence
        validated_resonance = self.validator.validate(
            experience, trajectory, horizon_assessments
        )
        experience.resonance_score = validated_resonance

        # 8. Update matrix position
        experience.matrix_position = self._calculate_matrix_position(
            experience.quality_score, signal
        )

        # 9. Drift + health checks
        drift_valid, drift_msg = self.ouroboros_anchor.validate_classification(
            experience, trajectory
        )
        cycle_healthy, cycle_msg = self.ouroboros_anchor.check_ouroboros_health(
            trajectory
        )

        # 10. Updated recommendations
        recommendations = self._generate_recommendations(
            experience, trajectory, drift_valid, cycle_healthy
        )

        explanation = self._build_explanation(
            experience, trajectory, horizon_assessments,
            drift_valid, drift_msg, cycle_healthy, cycle_msg,
        )

        arc_trend = self.temporal_evaluator.compute_arc_trend(horizon_assessments)

        return AssessmentResult(
            experience=experience,
            trajectory=trajectory,
            pending_questions=[],  # no new questions on follow-up
            arc_trend=arc_trend,
            recommendations=recommendations,
            explanation=explanation,
        )

    # ------------------------------------------------------------------
    # Entry Point 3: Artifact Submission (Defence Layer 2)
    # ------------------------------------------------------------------

    def submit_artifact(
        self,
        user_id: str,
        experience_id: str,
        url: str,
        user_claim: str = "",
        platform: str = "",
    ) -> ArtifactVerification:
        """Submit an externally-hosted artifact as evidence of creation.

        This is PORTFOLIO-BASED verification: the user presents a URL
        to something they created (blog post, X thread, GitHub repo,
        Grokipedia edit, etc.) and the system verifies it exists, is
        substantive, has a plausible timestamp, and relates to the
        claimed experience.

        Requires internet access.  Returns 'inaccessible' if the system
        has no web client configured.

        Args:
            user_id: The user submitting the artifact.
            experience_id: The experience this artifact evidences.
            url: The URL to verify.
            user_claim: What the user says this artifact is.
            platform: The platform (auto-detected if empty).

        Returns:
            ArtifactVerification with status and detailed checks.
        """
        # Find the experience
        trajectory = self.vector_tracker.get_trajectory(user_id)
        if trajectory is None:
            return ArtifactVerification(
                status="inaccessible",
                notes="User has no recorded experiences.",
            )

        experience = self.vector_tracker._find_experience(
            trajectory, experience_id
        )
        if experience is None:
            return ArtifactVerification(
                status="inaccessible",
                notes=f"Experience {experience_id} not found.",
            )

        artifact = Artifact(
            experience_id=experience_id,
            user_id=user_id,
            url=url,
            platform=platform,
            user_claim=user_claim,
        )

        verification = self.external_validator.verify_artifact(
            artifact, experience
        )

        # If verified, record as a propagation event (creation evidence)
        if verification.status == "verified":
            experience.propagated = True
            experience.propagation_events.append(
                f"[Artifact verified] {url}: {user_claim}"
            )
            # Update trajectory propagation rate
            trajectory.propagation_rate = (
                self.propagation_tracker.compute_propagation_rate(trajectory)
            )

        return verification

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_matrix_position(quality: float, signal: IntentionSignal) -> str:
        quality_level = "High" if quality > 0.5 else "Low"
        intention_level = {
            IntentionSignal.CREATIVE: "Creative",
            IntentionSignal.CONSUMPTIVE: "Consumptive",
            IntentionSignal.MIXED: "Mixed",
            IntentionSignal.PENDING: "Pending",
        }.get(signal, "Pending")

        return QUADRANTS.get(
            (quality_level, intention_level),
            f"Pending ({quality_level} Quality, Vector Unknown)",
        )

    def _generate_recommendations(
        self,
        experience: Experience,
        trajectory: UserTrajectory,
        drift_valid: bool,
        cycle_healthy: bool,
    ) -> list[str]:
        """Context-aware recommendations."""
        recs: list[str] = []
        pos = experience.matrix_position

        # If classification is still pending, the primary recommendation
        # is to wait for evidence.
        if experience.provisional_intention == IntentionSignal.PENDING:
            recs.append(
                "Your intention vector is still forming.  "
                "Check back after some time to see what this experience leads to."
            )
            return recs

        if experience.intention_confidence < 0.3:
            recs.append(
                "Confidence is low -- the system is still watching.  "
                "Follow-up observations will sharpen the picture."
            )

        # Position-based recommendations
        if "Optimal" in pos:
            recs.append("This experience aligns with high quality creative intent.  Keep going.")
            if trajectory.propagation_rate > 0.5:
                recs.append("Your pattern of creating after resonance is strong.  Share your process.")
        elif "Hedonism" in pos:
            recs.append("High quality, but the vector leans consumptive.  Could you add a creative element?")
            recs.append("Set a time boundary and use the experience as fuel for something you make.")
        elif "Slop" in pos:
            recs.append("Creative intent is there, but quality could be higher.  Seek feedback.")
            recs.append("Study the masters in this area.  Iteration with intent raises the bar.")
        elif "Junk Food" in pos:
            recs.append("This experience leans consumptive and low quality.")
            recs.append("Try channelling even a small part of this into something you create.")
        elif "Transitional" in pos:
            recs.append("Lean into the creative elements of this experience.")

        # Drift warning
        if not drift_valid:
            recs.append(
                "[Drift detected] The system's classification may not match "
                "evidence.  Follow-up data will clarify."
            )

        # Ouroboros health warning
        if not cycle_healthy:
            recs.append(
                "[Cycle health] Your recent pattern leans heavily toward "
                "consumption.  Consider introducing small creative acts -- "
                "even mundane tasks done with care and intent count."
            )

        return recs

    @staticmethod
    def _build_explanation(
        experience: Experience,
        trajectory: UserTrajectory,
        horizon_assessments: list,
        drift_valid: bool,
        drift_msg: str,
        cycle_healthy: bool,
        cycle_msg: str,
    ) -> dict:
        """Build a comprehensive explanation dict."""
        # Count how many horizons have evidence
        horizons_with_data = sum(
            1 for a in horizon_assessments if a.score is not None
        )

        return {
            "intention": {
                "signal": experience.provisional_intention.value,
                "confidence": round(experience.intention_confidence, 3),
                "is_provisional": experience.intention_confidence < 0.5,
                "note": (
                    "Classification is provisional; follow-up evidence will "
                    "sharpen it."
                    if experience.intention_confidence < 0.5
                    else "Classification has reasonable confidence based on evidence."
                ),
            },
            "quality": {
                "score": round(experience.quality_score, 3),
                "dimensions": {k: round(v, 3) for k, v in experience.quality_dimensions.items()},
            },
            "resonance": {
                "validated_score": round(experience.resonance_score, 3),
            },
            "vector": {
                "direction": round(trajectory.current_vector.direction, 3),
                "magnitude": round(trajectory.current_vector.magnitude, 3),
                "confidence": round(trajectory.current_vector.confidence, 3),
                "compounding": round(trajectory.compounding_direction, 3),
                "creation_rate": round(trajectory.creation_rate, 3),
            },
            "temporal": {
                "horizons_with_data": horizons_with_data,
                "total_horizons": len(horizon_assessments),
                "note": (
                    f"Only {horizons_with_data}/{len(horizon_assessments)} "
                    f"horizons have evidence.  The long arc needs time."
                ),
            },
            "drift_check": {
                "valid": drift_valid,
                "message": drift_msg,
            },
            "ouroboros_health": {
                "healthy": cycle_healthy,
                "message": cycle_msg,
            },
            "matrix_position": experience.matrix_position,
        }
