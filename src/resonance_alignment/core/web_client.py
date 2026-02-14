"""Web access abstraction for external evidence gathering.

The Improvement Axiom requires two internet-dependent capabilities:

1. ARTIFACT VERIFICATION -- Given a URL the user presents as evidence
   of creation, fetch and analyse the page to confirm it exists, is
   substantive, has a plausible timestamp, and relates to the claimed
   experience.

2. EVIDENCE SEARCH -- Given an action description, search public
   sources for documented evidence about what similar actions typically
   lead to over time (the Extrapolation Model).

This module provides the WebClient abstraction so these capabilities
can be backed by different implementations:
- HttpxWebClient for production (real HTTP)
- MockWebClient for testing (canned responses)
- Any future backend (search APIs, LLM-assisted, curated DB)

GRACEFUL DEGRADATION:
If internet access is unavailable, the system continues to function
with the other three defence layers (Vector Tracking, Temporal
Evaluation, Propagation Tracking).  Artifact verification and
extrapolation simply return 'unavailable' status, and the system
reports lower confidence in its assessment.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


# ---------------------------------------------------------------------------
# Data classes returned by the web client
# ---------------------------------------------------------------------------

@dataclass
class WebPage:
    """Content fetched from a URL."""

    url: str = ""
    status_code: int = 0
    title: str = ""
    content_text: str = ""         # Extracted text content
    content_length: int = 0        # Rough byte length
    publish_date: str | None = None  # Publication date if detectable
    platform: str = "unknown"      # Detected platform (x, github, medium, etc.)
    accessible: bool = False
    error: str | None = None

    @property
    def is_substantive(self) -> bool:
        """Is there meaningful textual content (not just boilerplate)?"""
        # Heuristic: at least 50 words of actual content
        words = len(self.content_text.split())
        return words >= 50

    @property
    def word_count(self) -> int:
        return len(self.content_text.split())


@dataclass
class SearchResult:
    """A single result from a web search."""

    title: str = ""
    url: str = ""
    snippet: str = ""
    source: str = ""     # domain / publication name
    date: str | None = None


# ---------------------------------------------------------------------------
# Abstract WebClient interface
# ---------------------------------------------------------------------------

class WebClient(ABC):
    """Abstract web access layer.

    Concrete implementations provide real HTTP or mocked responses.
    """

    @abstractmethod
    def fetch_page(self, url: str) -> WebPage:
        """Fetch a web page and extract its content.

        Returns a WebPage with accessible=False on any failure.
        """

    @abstractmethod
    def search(
        self, query: str, num_results: int = 10
    ) -> list[SearchResult]:
        """Search the public web for a query.

        Returns a list of SearchResult (may be empty on failure).
        """


# ---------------------------------------------------------------------------
# Real implementation using httpx
# ---------------------------------------------------------------------------

class HttpxWebClient(WebClient):
    """Production web client using httpx for real HTTP access.

    Requires: pip install httpx
    """

    def __init__(
        self,
        timeout: float = 15.0,
        search_endpoint: str | None = None,
        search_api_key: str | None = None,
    ) -> None:
        try:
            import httpx  # noqa: F401
            self._httpx = httpx
            self._client = httpx.Client(
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": "ImprovementAxiom/0.2 (ArtifactVerifier)"},
            )
        except ImportError:
            raise ImportError(
                "httpx is required for web access.  "
                "Install it with: pip install httpx"
            )
        self._search_endpoint = search_endpoint
        self._search_api_key = search_api_key

    def fetch_page(self, url: str) -> WebPage:
        """Fetch a URL and extract textual content."""
        try:
            resp = self._client.get(url)
            content = resp.text

            title = self._extract_title(content)
            text = self._extract_text(content)
            pub_date = self._extract_date(content)
            platform = self._detect_platform(url)

            return WebPage(
                url=str(resp.url),
                status_code=resp.status_code,
                title=title,
                content_text=text,
                content_length=len(resp.content),
                publish_date=pub_date,
                platform=platform,
                accessible=(200 <= resp.status_code < 400),
            )
        except Exception as exc:
            return WebPage(
                url=url,
                accessible=False,
                error=str(exc),
            )

    def search(
        self, query: str, num_results: int = 10
    ) -> list[SearchResult]:
        """Search the web using the configured search endpoint.

        In production, this should be backed by a search API
        (Google Custom Search, Bing, Brave Search, etc.) or by
        an LLM with web-search tool access.

        If no search endpoint is configured, returns empty results
        with a note that search requires configuration.
        """
        if not self._search_endpoint:
            return []

        try:
            resp = self._client.get(
                self._search_endpoint,
                params={
                    "q": query,
                    "count": num_results,
                    "key": self._search_api_key or "",
                },
            )
            if resp.status_code != 200:
                return []

            data = resp.json()
            results: list[SearchResult] = []

            # Generic JSON structure -- adapt to your search API
            for item in data.get("results", data.get("items", []))[:num_results]:
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", item.get("link", "")),
                    snippet=item.get("snippet", item.get("description", "")),
                    source=item.get("source", ""),
                    date=item.get("date"),
                ))
            return results

        except Exception:
            return []

    # ------------------------------------------------------------------
    # HTML extraction helpers (lightweight; production should use
    # trafilatura, readability-lxml, or similar)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_title(html: str) -> str:
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _extract_text(html: str) -> str:
        """Rough text extraction from HTML."""
        # Remove script and style blocks
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _extract_date(html: str) -> str | None:
        """Try to find a publication date in HTML meta tags."""
        patterns = [
            r'<meta[^>]*property="article:published_time"[^>]*content="([^"]+)"',
            r'<meta[^>]*name="date"[^>]*content="([^"]+)"',
            r'<meta[^>]*name="DC\.date"[^>]*content="([^"]+)"',
            r'<time[^>]*datetime="([^"]+)"',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _detect_platform(url: str) -> str:
        """Detect the platform from the URL domain."""
        url_lower = url.lower()
        if "x.com" in url_lower or "twitter.com" in url_lower:
            return "x"
        elif "github.com" in url_lower:
            return "github"
        elif "medium.com" in url_lower:
            return "medium"
        elif "wikipedia.org" in url_lower or "grokipedia" in url_lower:
            return "wiki"
        elif "youtube.com" in url_lower or "youtu.be" in url_lower:
            return "youtube"
        elif "substack.com" in url_lower:
            return "substack"
        elif "linkedin.com" in url_lower:
            return "linkedin"
        elif "reddit.com" in url_lower:
            return "reddit"
        return "web"


# ---------------------------------------------------------------------------
# Mock implementation for testing
# ---------------------------------------------------------------------------

class MockWebClient(WebClient):
    """Mock web client returning canned responses for tests.

    Set up responses before use:
        mock = MockWebClient()
        mock.add_page("https://example.com/post", WebPage(...))
        mock.add_search_results("query", [SearchResult(...)])
    """

    def __init__(self) -> None:
        self._pages: dict[str, WebPage] = {}
        self._search_results: dict[str, list[SearchResult]] = {}

    def add_page(self, url: str, page: WebPage) -> None:
        self._pages[url] = page

    def add_search_results(
        self, query: str, results: list[SearchResult]
    ) -> None:
        self._search_results[query] = results

    def fetch_page(self, url: str) -> WebPage:
        if url in self._pages:
            return self._pages[url]
        return WebPage(url=url, accessible=False, error="Mock: URL not configured")

    def search(
        self, query: str, num_results: int = 10
    ) -> list[SearchResult]:
        # Try exact match first
        if query in self._search_results:
            return self._search_results[query][:num_results]

        # Flexible matching: word overlap (like a real search engine)
        query_words = set(query.lower().split())
        best_match: list[SearchResult] | None = None
        best_overlap = 0
        for key, results in self._search_results.items():
            key_words = set(key.lower().split())
            overlap = len(query_words & key_words)
            # Match if at least half the key's words appear in query
            if overlap > best_overlap and overlap >= max(len(key_words) * 0.5, 1):
                best_overlap = overlap
                best_match = results
        if best_match is not None:
            return best_match[:num_results]
        return []
