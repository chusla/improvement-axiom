"""Environment-based configuration for the Improvement Axiom framework.

Reads settings from environment variables (or a .env file via
python-dotenv if available).  Provides factory methods for creating
configured storage backends and the full system.

Environment variables:
    SUPABASE_URL       -- Supabase project URL (enables SupabaseStorage)
    SUPABASE_KEY       -- Supabase service-role key
    ANTHROPIC_API_KEY  -- Anthropic API key (enables agent integration)
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from resonance_alignment.storage.base import StorageBackend
    from resonance_alignment.system import ResonanceAlignmentSystem


def _load_dotenv() -> None:
    """Try to load .env file; no-op if python-dotenv not installed."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def get_supabase_url() -> str | None:
    """Return Supabase URL from environment, or None."""
    _load_dotenv()
    return os.environ.get("SUPABASE_URL")


def get_supabase_key() -> str | None:
    """Return Supabase service-role key from environment, or None."""
    _load_dotenv()
    return os.environ.get("SUPABASE_KEY")


def get_anthropic_key() -> str | None:
    """Return Anthropic API key from environment, or None."""
    _load_dotenv()
    return os.environ.get("ANTHROPIC_API_KEY")


def get_storage() -> "StorageBackend":
    """Create a storage backend based on environment configuration.

    Returns SupabaseStorage if SUPABASE_URL and SUPABASE_KEY are set,
    otherwise returns InMemoryStorage.
    """
    from resonance_alignment.storage.memory import InMemoryStorage

    url = get_supabase_url()
    key = get_supabase_key()

    if url and key:
        try:
            from resonance_alignment.storage.supabase_storage import SupabaseStorage
            return SupabaseStorage(supabase_url=url, supabase_key=key)
        except ImportError:
            import warnings
            warnings.warn(
                "Supabase credentials found but supabase package not installed.  "
                "Install with: pip install 'resonance-alignment-framework[supabase]'.  "
                "Falling back to InMemoryStorage.",
                stacklevel=2,
            )

    return InMemoryStorage()


def from_env() -> "ResonanceAlignmentSystem":
    """Create a fully configured ResonanceAlignmentSystem from environment.

    Reads SUPABASE_URL/SUPABASE_KEY for storage and sets up the system.
    If ANTHROPIC_API_KEY is set, an AgentWebClient can be constructed
    separately by the caller.

    Returns:
        A configured ResonanceAlignmentSystem ready for use.
    """
    from resonance_alignment.system import ResonanceAlignmentSystem

    storage = get_storage()

    return ResonanceAlignmentSystem(
        storage=storage,
    )
