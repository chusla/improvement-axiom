"""External validation layer -- cross-references AI assessments with
independently observable evidence.

IMPORTANT CONSTRAINT -- Observable Actions Only:

All external validation must be grounded in *observable actions and
their outcomes*.  The system NEVER groups, compares, or profiles
individuals by creed, race, ethnicity, gender, religion, political
affiliation, or any other identity attribute.

This module integrates three sources of external evidence:

1. ARTIFACT VERIFICATION (Defence Layer 2)
   User-presented artifacts verified via web access.

2. TRAJECTORY CONSISTENCY
   AI's assessment checked against the individual's own action history
   (via VectorTracker data).

3. EVIDENCE-BASED EXTRAPOLATION (Defence Layer 5)
   Public web evidence about what similar actions typically lead to.

If web access is unavailable, the validator degrades gracefully --
it still checks trajectory consistency using local data, and reports
lower confidence for the web-dependent layers.
"""

from __future__ import annotations

from resonance_alignment.core.models import (
    Artifact,
    ArtifactVerification,
    Experience,
    TrajectoryEvidence,
    UserTrajectory,
)
from resonance_alignment.core.web_client import WebClient
from resonance_alignment.safety.artifact_verifier import ArtifactVerifier
from resonance_alignment.core.extrapolation_model import ExtrapolationModel


class ExternalValidator:
    """Checks AI assessments against external *observable* measures.

    Detects gaming, divergence, or systematic bias by comparing the
    AI's scores against independently verifiable evidence.

    All checks are action-based and outcome-based.  No demographic,
    identity, or group-membership comparisons are permitted.
    """

    DIVERGENCE_THRESHOLD = 0.3

    # Explicitly forbidden comparison dimensions.
    FORBIDDEN_DIMENSIONS = frozenset({
        "race", "ethnicity", "gender", "sex", "religion", "creed",
        "political_affiliation", "nationality", "age_group",
        "socioeconomic_class", "sexual_orientation", "disability_status",
    })

    def __init__(self, web_client: WebClient | None = None) -> None:
        """Initialise with optional web access.

        Args:
            web_client: WebClient for internet access.  If None,
                web-dependent layers (artifact verification and
                extrapolation) are disabled; the validator operates
                in offline/degraded mode.
        """
        self._web = web_client
        self._artifact_verifier: ArtifactVerifier | None = None
        self._extrapolation_model: ExtrapolationModel | None = None

        if web_client is not None:
            self._artifact_verifier = ArtifactVerifier(web_client)
            self._extrapolation_model = ExtrapolationModel(web_client)

    @property
    def has_web_access(self) -> bool:
        return self._web is not None

    # ------------------------------------------------------------------
    # Primary API
    # ------------------------------------------------------------------

    def validate_against_external(
        self, ai_assessment: dict, observable_context: dict
    ) -> tuple[str, dict]:
        """Check AI assessments against external observable measures.

        Args:
            ai_assessment: Dict with the AI's scores and classifications.
            observable_context: Dict with *observable action data* only.
                Must not contain identity attributes.

        Returns:
            Tuple of (status, external_checks).

        Raises:
            ValueError: If observable_context contains forbidden dimensions.
        """
        self._enforce_no_identity_attributes(observable_context)

        external_checks = {
            "action_outcome_consistency": self._check_action_outcomes(
                observable_context
            ),
            "creation_output_evidence": self._check_creation_output(
                observable_context
            ),
            "trajectory_consistency": self._check_trajectory_consistency(
                observable_context
            ),
            "environmental_context": self._check_environmental_context(
                observable_context
            ),
            "web_access_available": self.has_web_access,
        }

        if self._detect_divergence(ai_assessment, external_checks):
            return "Validation failure", external_checks

        return "Validated", external_checks

    # ------------------------------------------------------------------
    # Artifact Verification (Defence Layer 2)
    # ------------------------------------------------------------------

    def verify_artifact(
        self,
        artifact: Artifact,
        experience: Experience,
    ) -> ArtifactVerification:
        """Verify an externally-hosted artifact.

        Requires web access.  Returns 'inaccessible' verification
        if web client is not configured.
        """
        if self._artifact_verifier is None:
            return ArtifactVerification(
                artifact_id=artifact.id,
                url_accessible=False,
                status="inaccessible",
                notes="Web access not configured.  Artifact verification "
                      "requires internet access.",
            )

        return self._artifact_verifier.verify(artifact, experience)

    def verify_artifacts_batch(
        self,
        artifacts: list[Artifact],
        experience: Experience,
    ) -> list[ArtifactVerification]:
        """Verify multiple artifacts for an experience."""
        return [self.verify_artifact(a, experience) for a in artifacts]

    # ------------------------------------------------------------------
    # Evidence-Based Extrapolation (Defence Layer 5)
    # ------------------------------------------------------------------

    def extrapolate(
        self,
        experience: Experience,
        trajectory: UserTrajectory | None = None,
    ) -> TrajectoryEvidence:
        """Generate evidence-based hypotheses about the experience's trajectory.

        Requires web access.  Returns empty TrajectoryEvidence with
        a degradation note if web client is not configured.
        """
        if self._extrapolation_model is None:
            return TrajectoryEvidence(
                query=experience.description,
                note="Web access not configured.  Evidence-based "
                     "extrapolation requires internet access.  The system "
                     "continues with other defence layers at lower confidence.",
            )

        return self._extrapolation_model.hypothesise(experience, trajectory)

    # ------------------------------------------------------------------
    # Internal checks (work with or without web access)
    # ------------------------------------------------------------------

    def _enforce_no_identity_attributes(self, context: dict) -> None:
        """Guard: reject any context that includes identity-based dimensions."""
        present = self.FORBIDDEN_DIMENSIONS & set(context.keys())
        if present:
            raise ValueError(
                f"Observable context must not contain identity attributes.  "
                f"Found forbidden dimensions: {present}.  "
                f"The Improvement Axiom evaluates actions and outcomes, "
                f"never individuals by identity."
            )

    def _detect_divergence(
        self, ai_assessment: dict, external_checks: dict
    ) -> bool:
        """Detect if AI assessment diverges significantly from external signals."""
        ai_score = ai_assessment.get("quality", 0.5)
        external_scores = [
            v for v in external_checks.values()
            if isinstance(v, (int, float))
        ]
        if not external_scores:
            return False
        avg_external = sum(external_scores) / len(external_scores)
        return abs(ai_score - avg_external) > self.DIVERGENCE_THRESHOLD

    def _check_action_outcomes(self, context: dict) -> float:
        """Check observable outcomes of the action itself.

        Uses follow-up evidence from context if available; otherwise
        returns a neutral score pending more data.
        """
        follow_ups = context.get("follow_ups", [])
        if not follow_ups:
            return 0.5

        created = sum(1 for f in follow_ups if f.get("created_something"))
        return min(0.5 + created * 0.15, 1.0)

    def _check_creation_output(self, context: dict) -> float:
        """Check for evidence of creative output following the action."""
        propagation_events = context.get("propagation_events", [])
        if not propagation_events:
            return 0.5
        return min(0.5 + len(propagation_events) * 0.1, 1.0)

    def _check_trajectory_consistency(self, context: dict) -> float:
        """Check whether the action is consistent with the individual's
        own trajectory of observable actions."""
        direction = context.get("vector_direction", 0.0)
        confidence = context.get("vector_confidence", 0.0)

        if confidence < 0.1:
            return 0.5  # Not enough history to assess

        # Consistency: does the current action align with trajectory?
        # Higher confidence in a clear direction = more consistent
        return 0.5 + direction * confidence * 0.3

    def _check_environmental_context(self, context: dict) -> float:
        """Check environmental context as it affects the action.

        Geography is relevant ONLY insofar as it modifies the action
        itself, never as a proxy for identity.
        """
        # Environmental context modifies action quality expectations
        # (professional kitchen vs. campfire → different quality baselines)
        return 0.5  # Neutral unless specific environmental data provided
