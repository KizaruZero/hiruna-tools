"""Provider abstraction.

Every platform (YouTube, TikTok, Instagram, future ones) implements
MediaProvider. The API layer and frontend only talk to this interface,
so a provider can be replaced or upgraded without touching the rest
of the app — important because these sites change their internals often.

See CONTRIBUTING.md for a step-by-step guide to adding a provider.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Optional


class ProviderError(Exception):
    """Base error for provider failures."""


class UnsupportedError(ProviderError):
    """The requested content/action is not legitimately available.

    Used for private content, auth-gated endpoints, removed features, etc.
    Carries a human-readable message safe to show to the user.
    """


class NotFoundError(ProviderError):
    """The URL did not resolve to any media."""


@dataclass
class MediaFormat:
    """One downloadable variant of a media resource."""
    format_id: str          # provider-native id, passed back to download()
    label: str              # e.g. "1080p", "Audio M4A"
    ext: str                # e.g. "mp4", "m4a", "mp3", "jpg"
    kind: str               # "video" | "audio" | "image" | "thumbnail"
    width: Optional[int] = None
    height: Optional[int] = None
    filesize: Optional[int] = None   # bytes, when known
    abr: Optional[float] = None      # audio bitrate kbps
    vbr: Optional[float] = None      # video bitrate kbps
    note: str = ""


@dataclass
class MediaResource:
    """A resolved media item, independent of any platform."""
    provider: str           # provider name, e.g. "youtube"
    url: str                # original URL the user pasted
    resource_id: str        # provider-native id (video id, etc.)
    title: str = ""
    author: str = ""
    duration: Optional[float] = None   # seconds
    thumbnail_url: str = ""
    webpage_url: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class Capabilities:
    """What actions the frontend should offer for a resource."""
    can_download_video: bool = False
    can_download_audio: bool = False
    can_download_thumbnail: bool = False
    can_view_metadata: bool = True


# Progress callback: (downloaded_bytes, total_bytes_or_None)
ProgressCallback = Callable[[int, Optional[int]], None]


class MediaProvider(ABC):
    """Interface every platform provider must implement."""

    name: str = "base"
    # Host suffixes this provider claims, e.g. ("youtube.com", "youtu.be").
    domains: tuple[str, ...] = ()

    # -- discovery -----------------------------------------------------
    def matches(self, url: str) -> bool:
        """True if this provider handles the given URL (host allowlist)."""
        from urllib.parse import urlparse

        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return False
        return any(host == d or host.endswith("." + d) for d in self.domains)

    # -- core operations ----------------------------------------------
    @abstractmethod
    def resolve(self, url: str) -> MediaResource:
        """Validate + normalize a URL into a MediaResource.

        Must NOT download media. Raise UnsupportedError / NotFoundError
        with a human-readable message when the content is not available.
        """

    @abstractmethod
    def get_metadata(self, resource: MediaResource) -> dict:
        """Return a JSON-safe dict of metadata for display."""

    @abstractmethod
    def get_available_formats(self, resource: MediaResource) -> list[MediaFormat]:
        """List downloadable variants (may be empty)."""

    @abstractmethod
    def get_capabilities(self, resource: MediaResource) -> Capabilities:
        """Which actions the UI should offer."""

    @abstractmethod
    def download(
        self,
        resource: MediaResource,
        format: MediaFormat,
        dest_path: str,
        progress: Optional[ProgressCallback] = None,
    ) -> str:
        """Download the chosen format to dest_path. Returns dest_path.

        Must raise ProviderError (with human-readable message) on failure.
        Must never use shell=True / shell out with unsanitized input.
        """
