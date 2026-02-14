"""Observable Action Policy -- a system-wide invariant.

This module codifies the foundational constraint of the Improvement
Axiom:

    ALL evaluation, comparison, classification, and grouping must be
    based on OBSERVABLE ACTIONS and their EVIDENCED OUTCOMES.

    NEVER by creed, race, ethnicity, gender, religion, political
    affiliation, socioeconomic class, or any other identity attribute.

    Geography ONLY as contextual modifier on the action itself --
    'swimming in the Great Barrier Reef' is a different action than
    'swimming in a backyard pool' because the environment changes
    what the action IS, not who the person is.

Why this matters:

The power of the Improvement Axiom is that it evaluates the VECTOR
of actions and outcomes on a first-principles basis.  It does not
rely on statistical comparisons between groups, historical anecdotes
about types of people, or religious/moral templates mapped onto
individuals.

The question is always: 'What did this action lead to?  Did creation
follow?  Did the outcome persist over the long arc?'  These are
observable, evidence-based questions that apply universally regardless
of who the actor is.

Any system that groups by identity opens the door to:
  - Statistical stereotyping ('people like you tend to...')
  - Proxy discrimination (using geography or language as identity proxy)
  - Template morality (judging actions by the group the actor belongs to)
  - Preference collapse (assuming group-level patterns apply to individuals)

The Axiom rejects all of these.  Each individual's vector is their own,
revealed by their own actions and outcomes over time.
"""

from __future__ import annotations


# Attributes that must NEVER be used for comparison, grouping,
# classification, or prediction.
FORBIDDEN_IDENTITY_ATTRIBUTES: frozenset[str] = frozenset({
    "race",
    "ethnicity",
    "gender",
    "sex",
    "religion",
    "creed",
    "faith",
    "political_affiliation",
    "political_party",
    "nationality",
    "national_origin",
    "age_group",
    "generation",
    "socioeconomic_class",
    "income_bracket",
    "sexual_orientation",
    "disability_status",
    "marital_status",
    "family_status",
    "language_group",
    "tribal_affiliation",
    "caste",
})

# Contextual dimensions that ARE permitted, but ONLY when they modify
# the observable action itself -- never as identity proxies.
PERMITTED_CONTEXTUAL_DIMENSIONS: frozenset[str] = frozenset({
    "geographic_environment",    # reef vs. pool, mountain vs. plain
    "temporal_context",          # season, time of day (affects the action)
    "physical_environment",      # indoor vs. outdoor, urban vs. rural
    "tool_or_medium",            # digital vs. analog, instrument type
    "skill_level_observable",    # observable proficiency in the action
    "action_duration",           # how long the action lasted
    "action_frequency",          # how often the action recurs
    "collaborative_context",     # solo vs. group action (action-level, not identity)
})


class ObservableActionPolicy:
    """Enforces the observable-action-only invariant across the system.

    This is a guard that can be called by any component to verify that
    data being processed does not contain or rely on identity attributes.
    """

    @staticmethod
    def validate_context(context: dict) -> None:
        """Raise if context contains forbidden identity attributes.

        Args:
            context: Any dict of contextual data being passed through
                the system.

        Raises:
            ValueError: If forbidden attributes are detected.
        """
        if not isinstance(context, dict):
            return

        violations = FORBIDDEN_IDENTITY_ATTRIBUTES & set(context.keys())
        if violations:
            raise ValueError(
                f"Observable Action Policy violation: context contains "
                f"forbidden identity attributes {violations}.  "
                f"The Improvement Axiom evaluates actions and outcomes, "
                f"never individuals by identity."
            )

    @staticmethod
    def validate_comparison_basis(comparison_keys: set[str] | list[str]) -> None:
        """Raise if a comparison is based on identity attributes.

        Call this before performing any grouping, similarity search,
        or benchmark comparison to ensure the comparison dimensions
        are action-based.

        Args:
            comparison_keys: The dimensions being used for comparison.

        Raises:
            ValueError: If any comparison dimension is identity-based.
        """
        keys = set(comparison_keys) if not isinstance(comparison_keys, set) else comparison_keys
        violations = FORBIDDEN_IDENTITY_ATTRIBUTES & keys
        if violations:
            raise ValueError(
                f"Observable Action Policy violation: comparison uses "
                f"forbidden identity dimensions {violations}.  "
                f"Compare actions and outcomes, not people or groups."
            )

    @staticmethod
    def validate_grouping(grouping_criteria: dict) -> None:
        """Raise if grouping criteria use identity attributes.

        When aggregating data across individuals, the grouping must
        be by observable action characteristics (what they DID), not
        by who they ARE.

        Valid grouping: 'people who played video games and later created something'
        Invalid grouping: 'young males who play video games'

        Args:
            grouping_criteria: Dict describing how individuals are grouped.

        Raises:
            ValueError: If grouping uses identity attributes.
        """
        if not isinstance(grouping_criteria, dict):
            return

        violations = FORBIDDEN_IDENTITY_ATTRIBUTES & set(grouping_criteria.keys())
        if violations:
            raise ValueError(
                f"Observable Action Policy violation: grouping uses "
                f"forbidden identity dimensions {violations}.  "
                f"Group by shared actions and observable outcomes only."
            )

    @staticmethod
    def is_action_based_similarity(dimension: str) -> bool:
        """Check if a similarity dimension is action-based.

        Returns True for dimensions that describe what someone DID
        (action type, duration, tools used, creation output).
        Returns False for dimensions that describe who someone IS.
        """
        action_dimensions = {
            "action_type", "action_description", "action_duration",
            "action_frequency", "creation_output", "tool_used",
            "medium", "skill_demonstrated", "outcome_observed",
            "propagation_observed", "resonance_reported",
            "quality_dimensions", "follow_up_evidence",
            "geographic_environment", "temporal_context",
        }
        if dimension in action_dimensions or dimension in PERMITTED_CONTEXTUAL_DIMENSIONS:
            return True
        if dimension in FORBIDDEN_IDENTITY_ATTRIBUTES:
            return False
        # Unknown dimension -- allow but log for review
        return True

    @staticmethod
    def describe_policy() -> str:
        """Return a human-readable description of the policy."""
        return (
            "The Improvement Axiom evaluates actions and outcomes on a "
            "first-principles basis.  All comparison, classification, "
            "and grouping is based on observable actions and their "
            "evidenced outcomes over time.  The system never uses "
            "identity attributes (race, creed, gender, religion, etc.) "
            "for any purpose.  Geography is used only as environmental "
            "context that modifies the action itself.  Each individual's "
            "vector is their own, revealed by their own actions."
        )
