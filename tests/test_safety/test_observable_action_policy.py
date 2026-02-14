"""Tests for ObservableActionPolicy -- the identity-blindness invariant.

These tests codify the principle: ALL evaluation is based on observable
actions and outcomes.  NEVER by identity attributes.
"""

import pytest

from resonance_alignment.safety.observable_action_policy import (
    ObservableActionPolicy,
    FORBIDDEN_IDENTITY_ATTRIBUTES,
    PERMITTED_CONTEXTUAL_DIMENSIONS,
)
from resonance_alignment.safety.external_validator import ExternalValidator


class TestContextValidation:
    """Context data must not contain identity attributes."""

    def test_clean_context_passes(self):
        policy = ObservableActionPolicy()
        # Action-based context is fine
        policy.validate_context({
            "geographic_environment": "Great Barrier Reef",
            "action_duration": "2 hours",
            "tool_or_medium": "snorkel gear",
        })

    def test_race_in_context_raises(self):
        policy = ObservableActionPolicy()
        with pytest.raises(ValueError, match="identity attributes"):
            policy.validate_context({"race": "any_value"})

    def test_religion_in_context_raises(self):
        policy = ObservableActionPolicy()
        with pytest.raises(ValueError, match="identity attributes"):
            policy.validate_context({"religion": "any_value"})

    def test_gender_in_context_raises(self):
        policy = ObservableActionPolicy()
        with pytest.raises(ValueError, match="identity attributes"):
            policy.validate_context({"gender": "any_value"})

    def test_multiple_violations_detected(self):
        policy = ObservableActionPolicy()
        with pytest.raises(ValueError):
            policy.validate_context({
                "race": "x",
                "religion": "y",
                "geographic_environment": "mountain",  # this one is fine
            })


class TestComparisonBasisValidation:
    """Comparisons must be action-based, not identity-based."""

    def test_action_based_comparison_passes(self):
        policy = ObservableActionPolicy()
        policy.validate_comparison_basis({
            "action_type", "action_duration", "creation_output",
        })

    def test_demographic_comparison_raises(self):
        policy = ObservableActionPolicy()
        with pytest.raises(ValueError, match="identity dimensions"):
            policy.validate_comparison_basis({"age_group", "action_type"})

    def test_socioeconomic_comparison_raises(self):
        policy = ObservableActionPolicy()
        with pytest.raises(ValueError, match="identity dimensions"):
            policy.validate_comparison_basis({"socioeconomic_class"})


class TestGroupingValidation:
    """Grouping must be by shared actions, not shared identity."""

    def test_action_based_grouping_passes(self):
        policy = ObservableActionPolicy()
        # Valid: group by what people DID
        policy.validate_grouping({
            "action_type": "played_video_games",
            "outcome": "started_creating",
        })

    def test_identity_based_grouping_raises(self):
        policy = ObservableActionPolicy()
        # Invalid: group by who people ARE
        with pytest.raises(ValueError, match="identity dimensions"):
            policy.validate_grouping({
                "gender": "male",
                "age_group": "teens",
                "action_type": "played_video_games",
            })


class TestSimilarityDimensions:
    """Similarity search dimensions must be action-based."""

    def test_action_dimensions_are_valid(self):
        policy = ObservableActionPolicy()
        assert policy.is_action_based_similarity("action_type") is True
        assert policy.is_action_based_similarity("creation_output") is True
        assert policy.is_action_based_similarity("geographic_environment") is True

    def test_identity_dimensions_are_invalid(self):
        policy = ObservableActionPolicy()
        assert policy.is_action_based_similarity("race") is False
        assert policy.is_action_based_similarity("religion") is False
        assert policy.is_action_based_similarity("nationality") is False


class TestExternalValidatorEnforcement:
    """ExternalValidator must reject identity-polluted context."""

    def test_external_validator_rejects_identity_data(self):
        validator = ExternalValidator()
        with pytest.raises(ValueError, match="identity attributes"):
            validator.validate_against_external(
                ai_assessment={"quality": 0.7},
                observable_context={"ethnicity": "any_value"},
            )

    def test_external_validator_accepts_clean_data(self):
        validator = ExternalValidator()
        status, checks = validator.validate_against_external(
            ai_assessment={"quality": 0.5},
            observable_context={"geographic_environment": "urban park"},
        )
        assert status in ("Validated", "Validation failure")


class TestForbiddenSetCompleteness:
    """The forbidden set should cover standard protected categories."""

    def test_major_protected_categories_present(self):
        required = {
            "race", "ethnicity", "gender", "religion", "nationality",
            "sexual_orientation", "disability_status",
        }
        assert required.issubset(FORBIDDEN_IDENTITY_ATTRIBUTES)

    def test_contextual_dimensions_are_distinct(self):
        """Permitted and forbidden sets must not overlap."""
        overlap = FORBIDDEN_IDENTITY_ATTRIBUTES & PERMITTED_CONTEXTUAL_DIMENSIONS
        assert len(overlap) == 0, f"Overlap found: {overlap}"
