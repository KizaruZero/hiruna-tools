"""Instagram provider — honest about platform limits.

As of 2024+, Instagram requires authentication for essentially all media
access (including public posts, stories, and reels) and aggressively
rate-limits anonymous clients. There is no legitimate unauthenticated
way to fetch Instagram media that we are willing to ship:

- We will not use fake sessions, session hijacking, or credential stuffing.
- We will not scrape behind login walls or bypass rate limits.
- Private accounts, stories of non-followed users, etc. are out of scope.

So this provider detects Instagram URLs and returns a clear, actionable
UnsupportedError explaining the situation, instead of pretending to work
and failing mysteriously. If Instagram ever restores a public anonymous
API (or the user configures their own authenticated session — out of
scope for v1), this is the single file to replace.
"""
from __future__ import annotations

from typing import Optional

from .base import (
    Capabilities,
    MediaFormat,
    MediaProvider,
    MediaResource,
    ProgressCallback,
    UnsupportedError,
)

_UNSUPPORTED_MSG = (
    "Instagram requires a logged-in session for media access, and this tool "
    "does not use Instagram accounts or bypass login walls. "
    "Public posts, stories, and reels cannot be fetched anonymously. "
    "If you own the content, download it from the Instagram app "
    "(Share → Download, where available) instead."
)


class InstagramProvider(MediaProvider):
    name = "instagram"
    domains = ("instagram.com", "instagr.am")

    def resolve(self, url: str) -> MediaResource:
        raise UnsupportedError(_UNSUPPORTED_MSG)

    def get_metadata(self, resource: MediaResource) -> dict:
        raise UnsupportedError(_UNSUPPORTED_MSG)

    def get_available_formats(self, resource: MediaResource) -> list[MediaFormat]:
        raise UnsupportedError(_UNSUPPORTED_MSG)

    def get_capabilities(self, resource: MediaResource) -> Capabilities:
        # Capabilities are only reachable after resolve(); resolve() always
        # raises, so this is defensive.
        return Capabilities()

    def download(
        self,
        resource: MediaResource,
        format: MediaFormat,
        dest_path: str,
        progress: Optional[ProgressCallback] = None,
    ) -> str:
        raise UnsupportedError(_UNSUPPORTED_MSG)
