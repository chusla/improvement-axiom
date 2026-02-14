"""Portfolio-based artifact verification -- Defence Layer 2.

Breaks the circular self-validation problem: instead of validating
self-reported data against more self-reported data, the system checks
externally-hosted, independently-timestamped artifacts that the user
voluntarily presents as evidence of creation.

DESIGN PRINCIPLES:

1. USER-INITIATED: The person presents → the system confirms.
   NOT surveillance: the system watches → the person.

2. VOLUNTARY: Users choose which artifacts to present.  No monitoring,
   no scraping, no background checking.

3. SUBSTANCE OVER VANITY: The system checks for real creative content,
   not engagement metrics.  A thoughtful blog post with 3 readers
   carries as much weight as a viral tweet.

4. DEPTH OVER BREADTH: Consistent with the quality framework --
   a few substantive artifacts over months > many trivial posts.

5. TIMESTAMP PLAUSIBILITY: The artifact's creation date must make
   sense relative to the claimed experience timeline.

6. GRACEFUL DEGRADATION: If the URL is inaccessible or the internet
   is down, the verification returns 'unavailable' and the system
   continues with other defence layers at lower confidence.

The long arc is the ultimate defence: genuine creation builds a
portfolio over time that is exponentially expensive to fake.
AI-generated slop, plagiarism, and purchased engagement all collapse
under sustained temporal scrutiny.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from resonance_alignment.core.models import (
    Artifact,
    ArtifactVerification,
    Experience,
)
from resonance_alignment.core.web_client import WebClient, WebPage


class ArtifactVerifier:
    """Verifies externally-hosted artifacts as evidence of creation.

    Given a URL the user presents, the verifier:
    1. Fetches the page and checks accessibility.
    2. Extracts content and assesses substance (not trivial/empty).
    3. Checks timestamp plausibility vs. experience timeline.
    4. Estimates relevance to the claimed experience.
    5. Returns a verification result with overall status.

    Requires a WebClient for internet access.  In tests, use
    MockWebClient.  In production, use HttpxWebClient.
    """

    # Minimum word count to consider content 'substantive'
    _MIN_SUBSTANTIVE_WORDS = 50

    # Maximum time gap between experience and artifact publication
    # that is considered 'plausible' (artifact can predate or follow)
    _PLAUSIBILITY_WINDOW = timedelta(days=365)

    # Relevance scoring: minimum keyword overlap to consider relevant
    _MIN_RELEVANCE_OVERLAP = 0.10

    def __init__(self, web_client: WebClient) -> None:
        self._web = web_client

    def verify(
        self,
        artifact: Artifact,
        experience: Experience,
    ) -> ArtifactVerification:
        """Verify an artifact against the claimed experience.

        Args:
            artifact: The user-submitted artifact with URL and claim.
            experience: The experience this artifact allegedly evidences.

        Returns:
            ArtifactVerification with status and detailed checks.
        """
        # Step 1: Fetch the page
        page = self._web.fetch_page(artifact.url)

        if not page.accessible:
            return ArtifactVerification(
                artifact_id=artifact.id,
                url_accessible=False,
                status="inaccessible",
                notes=f"Could not access URL: {page.error or 'unknown error'}",
            )

        # Step 2: Assess substance
        is_substantive = self._assess_substance(page)

        # Step 3: Check timestamp plausibility
        timestamp_ok = self._check_timestamp(page, experience, artifact)

        # Step 4: Estimate relevance
        relevance = self._estimate_relevance(
            page, experience, artifact.user_claim
        )

        # Step 5: Determine overall status
        status = self._determine_status(
            is_substantive, timestamp_ok, relevance
        )

        return ArtifactVerification(
            artifact_id=artifact.id,
            url_accessible=True,
            content_summary=self._summarise_content(page),
            content_substantive=is_substantive,
            timestamp_plausible=timestamp_ok,
            relevance_score=relevance,
            verified_at=datetime.now(timezone.utc),
            status=status,
            notes=self._build_notes(
                page, is_substantive, timestamp_ok, relevance
            ),
        )

    def verify_batch(
        self,
        artifacts: list[Artifact],
        experience: Experience,
    ) -> list[ArtifactVerification]:
        """Verify multiple artifacts for the same experience."""
        return [self.verify(a, experience) for a in artifacts]

    # ------------------------------------------------------------------
    # Assessment methods
    # ------------------------------------------------------------------

    def _assess_substance(self, page: WebPage) -> bool:
        """Is the content substantive -- real creative output?

        Checks:
        - Minimum word count (not a trivial one-liner)
        - Not obviously boilerplate / auto-generated filler

        Note: detecting AI-generated content is an evolving challenge.
        The long arc is the primary defence -- sustained faking is
        exponentially harder than one-off generation.  But we apply
        basic heuristics here as a first pass.
        """
        if page.word_count < self._MIN_SUBSTANTIVE_WORDS:
            return False

        # Basic boilerplate detection: if the content is extremely
        # repetitive, it's likely filler.
        words = page.content_text.lower().split()
        if words:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.20:
                return False  # Very repetitive → likely filler

        return True

    def _check_timestamp(
        self,
        page: WebPage,
        experience: Experience,
        artifact: Artifact,
    ) -> bool:
        """Is the artifact's timestamp plausible?

        The artifact should have been created within a reasonable window
        of the experience it claims to evidence.  A blog post about
        a workshop should appear within weeks/months, not years before.

        If no timestamp is detectable, we give benefit of the doubt but
        note the limitation.
        """
        if not page.publish_date:
            # No timestamp found -- can't verify, but don't reject
            return True

        try:
            # Try common date formats
            for fmt in (
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d",
                "%B %d, %Y",
            ):
                try:
                    pub = datetime.strptime(
                        page.publish_date.strip()[:25], fmt
                    )
                    # Ensure timezone-aware for comparison
                    if pub.tzinfo is None:
                        pub = pub.replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue
            else:
                return True  # Unparseable date → benefit of the doubt

            delta = abs(pub - experience.timestamp)
            return delta <= self._PLAUSIBILITY_WINDOW

        except Exception:
            return True  # On any parsing error, benefit of the doubt

    def _estimate_relevance(
        self,
        page: WebPage,
        experience: Experience,
        user_claim: str,
    ) -> float:
        """How relevant is the artifact content to the claimed experience?

        Uses keyword overlap between the artifact content and the
        experience description + user claim.  Simple but effective as
        a first pass; production systems could use embeddings.

        Returns 0.0-1.0 relevance score.
        """
        # Build a reference word set from experience + claim
        reference_words = set()
        for text in (experience.description, experience.context, user_claim):
            if text:
                reference_words.update(
                    w.lower().strip(".,!?;:\"'()[]")
                    for w in text.split()
                    if len(w) > 2  # skip tiny words
                )

        if not reference_words:
            return 0.5  # No reference to compare against

        # Content word set
        content_words = set(
            w.lower().strip(".,!?;:\"'()[]")
            for w in page.content_text.split()
            if len(w) > 2
        )

        if not content_words:
            return 0.0

        # Keyword overlap (Jaccard-like but weighted toward reference)
        overlap = reference_words & content_words
        if not overlap:
            return 0.0

        # Score: what fraction of reference words appear in content?
        recall = len(overlap) / len(reference_words)

        # Boost if the title also matches
        title_words = set(
            w.lower().strip(".,!?;:\"'()[]")
            for w in page.title.split()
            if len(w) > 2
        )
        title_overlap = reference_words & title_words
        title_bonus = min(len(title_overlap) * 0.05, 0.15)

        return min(recall + title_bonus, 1.0)

    def _determine_status(
        self,
        is_substantive: bool,
        timestamp_ok: bool,
        relevance: float,
    ) -> str:
        """Determine overall verification status."""
        if not is_substantive:
            return "unverified"  # Content too thin to confirm

        if relevance < self._MIN_RELEVANCE_OVERLAP:
            return "unverified"  # Content doesn't relate to claim

        if not timestamp_ok:
            return "suspicious"  # Timestamp doesn't fit

        if relevance >= 0.3:
            return "verified"
        elif relevance >= 0.15:
            return "unverified"  # Weak relevance
        return "unverified"

    @staticmethod
    def _summarise_content(page: WebPage) -> str:
        """Create a brief summary of the page content."""
        words = page.content_text.split()
        if len(words) <= 30:
            return page.content_text
        return " ".join(words[:30]) + "..."

    @staticmethod
    def _build_notes(
        page: WebPage,
        is_substantive: bool,
        timestamp_ok: bool,
        relevance: float,
    ) -> str:
        """Build human-readable verification notes."""
        parts: list[str] = []

        parts.append(f"Platform: {page.platform}")
        parts.append(f"Word count: {page.word_count}")

        if not is_substantive:
            parts.append(
                "Content does not meet minimum substance threshold."
            )
        else:
            parts.append("Content is substantive.")

        if page.publish_date:
            parts.append(f"Published: {page.publish_date}")
            if not timestamp_ok:
                parts.append(
                    "WARNING: Publication date outside plausibility window."
                )
        else:
            parts.append("No publication date detected.")

        parts.append(f"Relevance to claim: {relevance:.0%}")

        return "  ".join(parts)
