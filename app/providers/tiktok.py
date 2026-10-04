"""TikTok provider backed by yt-dlp's Python API (no subprocess, no shell).

Public videos only. What you get is whatever TikTok's public endpoints
return through yt-dlp's normal extraction — we do not strip watermarks,
spoof clients, or bypass any access control. Availability varies with
TikTok's anti-bot posture; failures surface as clear errors, never hacks.
"""
from __future__ import annotations

from typing import Optional

from .base import (
    Capabilities,
    MediaFormat,
    MediaProvider,
    MediaResource,
    NotFoundError,
    ProgressCallback,
    ProviderError,
    UnsupportedError,
)
from .youtube import _ytdlp_opts


class TikTokProvider(MediaProvider):
    name = "tiktok"
    domains = ("tiktok.com", "vt.tiktok.com", "vm.tiktok.com")

    def resolve(self, url: str) -> MediaResource:
        info = self._extract(url, download=False)
        if not info or info.get("_type") == "playlist":
            raise NotFoundError("No TikTok video found at this URL.")
        return MediaResource(
            provider=self.name,
            url=url,
            resource_id=str(info.get("id", "")),
            title=str(info.get("title") or info.get("description") or "TikTok video"),
            author=str(info.get("uploader") or info.get("creator") or ""),
            duration=info.get("duration"),
            thumbnail_url=str(info.get("thumbnail") or ""),
            webpage_url=str(info.get("webpage_url") or url),
        )

    def get_metadata(self, resource: MediaResource) -> dict:
        info = self._extract(resource.webpage_url, download=False)
        return {
            "title": info.get("title") or info.get("description"),
            "author": info.get("uploader") or info.get("creator"),
            "duration": info.get("duration"),
            "width": info.get("width"),
            "height": info.get("height"),
            "view_count": info.get("view_count"),
            "like_count": info.get("like_count"),
            "thumbnail_url": info.get("thumbnail"),
            "webpage_url": info.get("webpage_url"),
        }

    def get_available_formats(self, resource: MediaResource) -> list[MediaFormat]:
        info = self._extract(resource.webpage_url, download=False)
        formats: list[MediaFormat] = []
        seen: set[str] = set()
        for f in info.get("formats") or []:
            fid = str(f.get("format_id", ""))
            if not fid or fid in seen:
                continue
            seen.add(fid)
            vcodec = f.get("vcodec")
            if not vcodec or vcodec == "none":
                continue
            height = f.get("height")
            formats.append(
                MediaFormat(
                    format_id=fid,
                    label=f"{height}p" if height else (f.get("format_note") or "video"),
                    ext=str(f.get("ext", "mp4")),
                    kind="video",
                    width=f.get("width"),
                    height=height,
                    filesize=f.get("filesize") or f.get("filesize_approx"),
                    note=f.get("format_note") or "",
                )
            )
        # Also offer the "best" merged stream as the first, simplest choice.
        if formats:
            best = max(formats, key=lambda x: (x.height or 0))
            formats.insert(
                0,
                MediaFormat(
                    format_id="best",
                    label=f"Best quality ({best.label})",
                    ext=best.ext,
                    kind="video",
                    width=best.width,
                    height=best.height,
                ),
            )
        return formats

    def get_capabilities(self, resource: MediaResource) -> Capabilities:
        return Capabilities(
            can_download_video=True,
            can_download_audio=False,
            can_download_thumbnail=False,
            can_view_metadata=True,
        )

    def download(
        self,
        resource: MediaResource,
        format: MediaFormat,
        dest_path: str,
        progress: Optional[ProgressCallback] = None,
    ) -> str:
        import os

        import yt_dlp

        tmp_base = dest_path + ".part"

        def hook(d: dict) -> None:
            if progress and d.get("status") == "downloading":
                progress(d.get("downloaded_bytes") or 0, d.get("total_bytes"))

        opts = _ytdlp_opts(
            {
                "format": format.format_id,
                "outtmpl": tmp_base + ".%(ext)s",
                "progress_hooks": [hook],
            }
        )
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([resource.webpage_url])
        except Exception as e:  # noqa: BLE001
            raise self._normalize_error(e, resource.url) from e
        produced: Optional[str] = None
        for cand in os.listdir(os.path.dirname(tmp_base) or "."):
            if cand.startswith(os.path.basename(tmp_base) + "."):
                produced = os.path.join(os.path.dirname(tmp_base), cand)
                break
        if not produced:
            raise ProviderError("Download finished but no file was produced.")
        os.replace(produced, dest_path)
        return dest_path

    # -- internals -------------------------------------------------------
    def _extract(self, url: str, download: bool):
        import yt_dlp

        try:
            with yt_dlp.YoutubeDL(_ytdlp_opts()) as ydl:
                return ydl.extract_info(url, download=download)
        except Exception as e:  # noqa: BLE001
            raise self._normalize_error(e, url) from e

    @staticmethod
    def _normalize_error(e: Exception, url: str) -> ProviderError:
        msg = str(e).lower()
        if "private" in msg or "login" in msg or "sign in" in msg:
            return UnsupportedError(
                "This TikTok content requires login or is private — not supported."
            )
        if "not available" in msg or "removed" in msg or "deleted" in msg:
            return NotFoundError("This TikTok video is unavailable or was removed.")
        if "unsupported url" in msg:
            return NotFoundError("This URL is not a supported TikTok link.")
        return ProviderError(f"TikTok error: {str(e)[:200]}")
