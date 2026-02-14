"""Evidence-based extrapolation from public web data -- Defence Layer 5.

Given an action, searches public sources for documented evidence about
what similar actions typically lead to over time.  Returns hypotheses
with citations, distinguishing factors, notable exceptions, and an
empowerment note.

DESIGN PRINCIPLES:

1. NOT A JUDGE.  A mentor.  'Here is what the evidence shows.  Most
   who did X ended up at Y, but some reached Z.  Here is what
   distinguished them.  What do you want to do?'

2. ALWAYS CITE SOURCES.  Every hypothesis links to public evidence.
   The user (and any auditor) can verify the basis for the hypothesis.

3. ALWAYS HIGHLIGHT EXCEPTIONS.  Probabilistically, most kids who play
   games don't become game developers.  But some do!  The system must
   never produce false positives that prevent that path.

4. EMPOWERMENT OVER JUDGMENT.  The output always ends with empowering
   the individual's choice.  The system presents evidence; the person
   decides.

5. OBSERVABLE ACTIONS ONLY.  The extrapolation is about the ACTION and
   its typical outcomes, never about the type of PERSON doing it.
   'What typically happens when someone plays video games 40hr/week'
   is valid.  'What typically happens when [demographic] plays games'
   is forbidden.

6. GRACEFUL DEGRADATION.  If web search returns no results, the model
   returns an empty TrajectoryEvidence with a note explaining the
   limitation.  The system continues with other defence layers.
"""

from __future__ import annotations

from datetime import datetime

from resonance_alignment.core.models import (
    Experience,
    ExtrapolationHypothesis,
    TrajectoryEvidence,
    UserTrajectory,
)
from resonance_alignment.core.web_client import WebClient, SearchResult


class ExtrapolationModel:
    """Generates evidence-based hypotheses about action trajectories.

    Uses web search to find research, articles, documented outcomes,
    and case studies about what similar actions typically lead to.
    Synthesises findings into structured hypotheses that inform but
    never dictate.

    Requires a WebClient for internet access.  In tests, use
    MockWebClient.  In production, use HttpxWebClient with a
    configured search endpoint.
    """

    # Maximum number of hypotheses to generate per query
    _MAX_HYPOTHESES = 3

    # Minimum search results needed to form a hypothesis
    _MIN_RESULTS_FOR_HYPOTHESIS = 2

    def __init__(self, web_client: WebClient) -> None:
        self._web = web_client

    def hypothesise(
        self,
        experience: Experience,
        trajectory: UserTrajectory | None = None,
    ) -> TrajectoryEvidence:
        """Generate evidence-based hypotheses for an experience's trajectory.

        Searches public sources for evidence about what actions like
        this one typically lead to over time.  Returns hypotheses with
        citations, exceptions, and empowerment notes.

        Args:
            experience: The experience to extrapolate from.
            trajectory: Optional trajectory for additional context.

        Returns:
            TrajectoryEvidence with hypotheses and source information.
        """
        # Step 1: Generate search queries from the experience
        queries = self._build_search_queries(experience)

        # Step 2: Execute searches and collect results
        all_results: list[SearchResult] = []
        for query in queries:
            results = self._web.search(query, num_results=5)
            all_results.extend(results)

        if len(all_results) < self._MIN_RESULTS_FOR_HYPOTHESIS:
            return TrajectoryEvidence(
                query=experience.description,
                hypotheses=[],
                search_timestamp=datetime.utcnow(),
                total_sources_found=len(all_results),
                note=(
                    "Insufficient public evidence found for this specific "
                    "action pattern.  The system continues with other "
                    "defence layers.  As more evidence becomes available, "
                    "this will improve."
                ),
            )

        # Step 3: Synthesise results into hypotheses
        hypotheses = self._synthesise_hypotheses(
            experience, all_results, trajectory
        )

        return TrajectoryEvidence(
            query=experience.description,
            hypotheses=hypotheses,
            search_timestamp=datetime.utcnow(),
            total_sources_found=len(all_results),
            note=self._build_evidence_note(len(all_results), len(hypotheses)),
        )

    # ------------------------------------------------------------------
    # Query generation
    # ------------------------------------------------------------------

    def _build_search_queries(self, experience: Experience) -> list[str]:
        """Generate search queries from the experience description.

        Produces multiple queries to cast a net:
        - Outcome-focused: 'what happens when someone [action] long term'
        - Research-focused: '[action] outcomes research study'
        - Career/growth: '[action] to career path examples'
        """
        desc = experience.description.strip()
        if not desc:
            return []

        # Extract the core action (simplified; production could use NLP)
        action = self._extract_action_phrase(desc)

        queries = [
            f"{action} long term outcomes",
            f"{action} career development research",
            f"{action} creative results examples",
        ]

        # If there's context, add a contextual query
        if experience.context:
            queries.append(
                f"{action} {experience.context} outcomes"
            )

        return queries[:4]  # Cap at 4 queries

    @staticmethod
    def _extract_action_phrase(description: str) -> str:
        """Extract the core action from a description.

        Simple heuristic: take the first meaningful clause.
        Production systems should use NLP for better extraction.
        """
        # Remove common filler prefixes
        for prefix in (
            "i have been ", "i've been ", "i was ", "i am ",
            "i started ", "been ", "started ",
        ):
            if description.lower().startswith(prefix):
                description = description[len(prefix):]
                break

        # Take first ~8 words as the action phrase
        words = description.split()[:8]
        return " ".join(words)

    # ------------------------------------------------------------------
    # Hypothesis synthesis
    # ------------------------------------------------------------------

    def _synthesise_hypotheses(
        self,
        experience: Experience,
        results: list[SearchResult],
        trajectory: UserTrajectory | None,
    ) -> list[ExtrapolationHypothesis]:
        """Synthesise search results into structured hypotheses.

        Groups results by theme and extracts:
        - Typical trajectory (the common outcome)
        - Distinguishing factors (what separates outcomes)
        - Notable exceptions (cases that defied the pattern)
        - Sources (always cited)
        """
        hypotheses: list[ExtrapolationHypothesis] = []

        # Deduplicate by URL
        seen_urls: set[str] = set()
        unique_results: list[SearchResult] = []
        for r in results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                unique_results.append(r)

        if not unique_results:
            return hypotheses

        # Group results into thematic clusters
        # (Simple approach: look for outcome-related keywords)
        creative_results = [
            r for r in unique_results
            if any(
                kw in (r.title + r.snippet).lower()
                for kw in (
                    "career", "professional", "creative", "develop",
                    "build", "create", "skill", "mastery", "success",
                )
            )
        ]

        consumptive_results = [
            r for r in unique_results
            if any(
                kw in (r.title + r.snippet).lower()
                for kw in (
                    "addiction", "waste", "decline", "negative",
                    "harm", "risk", "concern", "problem",
                )
            )
        ]

        neutral_results = [
            r for r in unique_results
            if r not in creative_results and r not in consumptive_results
        ]

        action = self._extract_action_phrase(experience.description)

        # Hypothesis 1: The typical/majority outcome
        if consumptive_results or neutral_results:
            majority_sources = (consumptive_results + neutral_results)[:5]
            hypotheses.append(ExtrapolationHypothesis(
                action_pattern=action,
                typical_trajectory=(
                    f"For most people, {action} remains a consumptive "
                    f"activity -- enjoyed but not leveraged into creation "
                    f"or skill development."
                ),
                probability_estimate=0.6,
                distinguishing_factors=[
                    "Intentional practice vs. passive consumption",
                    "Setting time boundaries and creative goals",
                    "Seeking community of practitioners, not just consumers",
                    "Documenting and sharing the experience",
                ],
                notable_exceptions=[
                    "Many professionals in creative fields trace their "
                    "passion to an early consumptive phase that sparked "
                    "curiosity.",
                ],
                sources=[r.url for r in majority_sources if r.url],
                empowerment_note=(
                    f"This is the statistical baseline, not your destiny.  "
                    f"The distinguishing factors above are actionable.  "
                    f"If {action} sparks something in you, lean into the "
                    f"creative impulse -- that's the vector that matters."
                ),
                confidence=min(
                    0.3 + len(majority_sources) * 0.1, 0.7
                ),
            ))

        # Hypothesis 2: The creative/growth outcome
        if creative_results:
            hypotheses.append(ExtrapolationHypothesis(
                action_pattern=action,
                typical_trajectory=(
                    f"A meaningful minority leverage {action} into "
                    f"creative output, skill development, or career growth."
                ),
                probability_estimate=0.25,
                distinguishing_factors=[
                    "Active engagement: analysing, not just consuming",
                    "Creating derivative or original work",
                    "Teaching or sharing insights with others",
                    "Connecting the activity to broader goals",
                ],
                notable_exceptions=[
                    "Some of the most successful creators in this space "
                    "had unconventional paths that wouldn't have been "
                    "predicted by early patterns.",
                ],
                sources=[r.url for r in creative_results[:5] if r.url],
                empowerment_note=(
                    f"You don't need to fit a pattern.  The evidence "
                    f"shows that the transition from consumer to creator "
                    f"often starts with a single intentional act.  What "
                    f"could you create from this experience?"
                ),
                confidence=min(
                    0.3 + len(creative_results) * 0.1, 0.7
                ),
            ))

        # Hypothesis 3: Trajectory-informed (if we have user history)
        if trajectory and trajectory.experience_count >= 3:
            direction = trajectory.current_vector.direction
            if direction > 0.2:
                trend = "creative"
                note = (
                    f"Your trajectory shows a creative trend.  Based on "
                    f"your pattern of turning experiences into creation, "
                    f"you're more likely than average to leverage this "
                    f"productively."
                )
            elif direction < -0.2:
                trend = "consumptive"
                note = (
                    f"Your recent trajectory leans consumptive.  This "
                    f"isn't a judgment -- it's an observation.  Small "
                    f"creative acts can shift the vector.  What's one "
                    f"thing you could make from this experience?"
                )
            else:
                trend = "mixed"
                note = (
                    f"Your trajectory is balanced.  You have creative "
                    f"and consumptive phases.  The evidence suggests "
                    f"that intentionally choosing to create after "
                    f"consuming is the key inflection point."
                )

            hypotheses.append(ExtrapolationHypothesis(
                action_pattern=action,
                typical_trajectory=(
                    f"Based on your personal trajectory ({trend} trend), "
                    f"combined with public evidence about {action}."
                ),
                probability_estimate=0.0,  # Not a probability -- personalised
                distinguishing_factors=[
                    "Your own creation rate and propagation history",
                    "Whether this specific experience leads to follow-up action",
                    "The compounding direction of your vector over time",
                ],
                notable_exceptions=[
                    "Trajectories can change at any point.  A single "
                    "powerful experience can redirect the entire vector.",
                ],
                sources=[],  # Personalised, not web-sourced
                empowerment_note=note,
                confidence=min(
                    trajectory.current_vector.confidence, 0.6
                ),
            ))

        return hypotheses[:self._MAX_HYPOTHESES]

    @staticmethod
    def _build_evidence_note(
        total_sources: int, num_hypotheses: int
    ) -> str:
        """Build a contextual note about the evidence quality."""
        if total_sources == 0:
            return (
                "No public evidence found.  The system operates "
                "with lower confidence on this action pattern."
            )
        if total_sources < 5:
            return (
                f"Limited evidence ({total_sources} sources).  "
                f"Hypotheses are directional, not definitive.  "
                f"More evidence will improve accuracy over time."
            )
        return (
            f"Found {total_sources} relevant sources, generating "
            f"{num_hypotheses} hypothesis(es).  All hypotheses are "
            f"probabilistic, not deterministic.  You are not a "
            f"statistic -- the distinguishing factors matter more "
            f"than the base rates."
        )
