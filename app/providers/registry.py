"""Provider registry: URL → provider selection and validation.

All user-supplied URLs pass through here before any provider touches them:
  1. validate_user_url()  — scheme, host, SSRF checks.
  2. detect_provider()     — host allowlist matching, in priority order.
"""
from __future__ import annotations

from urllib.parse import urlparse

from app.security import validate_public_url

from .base import MediaProvider, UnsupportedError
from .instagram import InstagramProvider
from .tiktok import TikTokProvider
from .youtube import YouTubeProvider

_PROVIDERS: list[MediaProvider] = [
    YouTubeProvider(),
    TikTokProvider(),
    InstagramProvider(),
]


def validate_user_url(url: str) -> str:
    """Normalize + security-validate a user-pasted URL.

    Returns the normalized URL. Raises ValueError with a human-readable
    message on any problem.
    """
    url = (url or "").strip()
    if not url:
        raise ValueError("Please paste a URL first.")
    if len(url) > 2048:
        raise ValueError("That URL is too long.")
    # Be forgiving about missing scheme.
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http(s) URLs are supported.")
    if not parsed.hostname:
        raise ValueError("That doesn't look like a valid URL.")
    # SSRF: block private/internal/link-local/loopback targets.
    validate_public_url(url)
    return url


def detect_provider(url: str) -> MediaProvider:
    """Return the provider handling this URL, or raise UnsupportedError."""
    for provider in _PROVIDERS:
        if provider.matches(url):
            return provider
    raise UnsupportedError(
        "This website isn't supported yet. "
        "Currently: YouTube, TikTok, and Instagram links."
    )


def list_providers() -> list[dict]:
    return [{"name": p.name, "domains": list(p.domains)} for p in _PROVIDERS]
