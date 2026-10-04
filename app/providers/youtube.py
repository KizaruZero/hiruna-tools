"""YouTube provider backed by yt-dlp's Python API (no subprocess, no shell).

Public videos only. Playlists resolve to their first entry being rejected —
paste a single video URL (playlist URLs are rejected with a clear message).
"""
from __future__ import annotations

import os
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

AUDIO_CODECS = {"mp3", "m4a", "wav", "opus"}


def _ytdlp_opts(extra: Optional[dict] = None) -> dict:
    from app.config import settings

    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": settings.ytdlp_socket_timeout,
        # Prefer the Android player client first: YouTube serves bot-check
        # walls to datacenter IPs on the web client, while the Android
        # client (an official public API surface, no auth involved) works.
        # Falls back to web client automatically.
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        # Never write anything except where we tell it to.
        "outtmpl": os.path.join(settings.data_dir, "tmp", "%(id)s.%(ext)s"),
    }
    if extra:
        opts.update(extra)
    return opts


class YouTubeProvider(MediaProvider):
    name = "youtube"
    domains = ("youtube.com", "youtu.be", "music.youtube.com", "youtube-nocookie.com")

    # -- resolve ------------------------------------------------------
    def resolve(self, url: str) -> MediaResource:
        import yt_dlp

        try:
            with yt_dlp.YoutubeDL(_ytdlp_opts()) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:  # noqa: BLE001 - normalized below
            raise self._normalize_error(e, url) from e
        if not info:
            raise NotFoundError("No media found at this URL.")
        if info.get("_type") == "playlist":
            raise UnsupportedError(
                "Playlist URLs are not supported — paste a single video URL."
            )
        return MediaResource(
            provider=self.name,
            url=url,
            resource_id=str(info.get("id", "")),
            title=str(info.get("title") or "Untitled"),
            author=str(info.get("uploader") or info.get("channel") or ""),
            duration=info.get("duration"),
            thumbnail_url=str(info.get("thumbnail") or ""),
            webpage_url=str(info.get("webpage_url") or url),
            extra={"raw_id": info.get("id")},
        )

    # -- metadata / formats -------------------------------------------
    def _extract(self, resource: MediaResource) -> dict:
        import yt_dlp

        try:
            with yt_dlp.YoutubeDL(_ytdlp_opts()) as ydl:
                info = ydl.extract_info(resource.webpage_url, download=False)
        except Exception as e:  # noqa: BLE001
            raise self._normalize_error(e, resource.url) from e
        if not info or info.get("_type") == "playlist":
            raise NotFoundError("This video is no longer available.")
        return info

    def get_metadata(self, resource: MediaResource) -> dict:
        info = self._extract(resource)
        return {
            "title": info.get("title"),
            "author": info.get("uploader") or info.get("channel"),
            "duration": info.get("duration"),
            "view_count": info.get("view_count"),
            "upload_date": info.get("upload_date"),
            "description": (info.get("description") or "")[:2000],
            "thumbnail_url": info.get("thumbnail"),
            "webpage_url": info.get("webpage_url"),
        }

    def get_available_formats(self, resource: MediaResource) -> list[MediaFormat]:
        info = self._extract(resource)
        formats: list[MediaFormat] = []
        seen: set[str] = set()
        for f in info.get("formats") or []:
            fid = str(f.get("format_id", ""))
            if not fid or fid in seen:
                continue
            vcodec = f.get("vcodec")
            acodec = f.get("acodec")
            has_video = vcodec and vcodec != "none"
            has_audio = acodec and acodec != "none"
            ext = str(f.get("ext", "mp4"))
            height = f.get("height")
            if has_video:
                label = f"{height}p" if height else (f.get("format_note") or ext)
                kind = "video"
            elif has_audio:
                abr = f.get("abr")
                label = f"Audio {ext.upper()}" + (f" {abr:.0f}k" if abr else "")
                kind = "audio"
            else:
                continue
            # Prefer combined (audio+video) mp4 streams for one-click download.
            seen.add(fid)
            formats.append(
                MediaFormat(
                    format_id=fid,
                    label=label,
                    ext=ext,
                    kind=kind,
                    width=f.get("width"),
                    height=height,
                    filesize=f.get("filesize") or f.get("filesize_approx"),
                    abr=f.get("abr"),
                    note="with audio" if (has_video and has_audio) else "",
                )
            )
        # Best-first: video by height desc, then audio by bitrate desc.
        videos = sorted(
            [x for x in formats if x.kind == "video"],
            key=lambda x: (x.height or 0, x.filesize or 0),
            reverse=True,
        )
        audios = sorted(
            [x for x in formats if x.kind == "audio"],
            key=lambda x: (x.abr or 0),
            reverse=True,
        )
        # Explicit extraction options: transcode best audio to a chosen
        # container ONLY when the user picks one of these.
        for codec in ("mp3", "m4a", "wav"):
            audios.append(
                MediaFormat(
                    format_id=f"audio:{codec}",
                    label=f"Audio {codec.upper()} (converted)",
                    ext=codec,
                    kind="audio",
                    note="converted from best available audio",
                )
            )
        return videos + audios

    def get_capabilities(self, resource: MediaResource) -> Capabilities:
        return Capabilities(
            can_download_video=True,
            can_download_audio=True,
            can_download_thumbnail=bool(resource.thumbnail_url),
            can_view_metadata=True,
        )

    def thumbnail_formats(self, resource: MediaResource) -> list[MediaFormat]:
        """Available thumbnail resolutions (derived from thumbnail URL)."""
        base = resource.thumbnail_url
        if not base:
            return []
        out: list[MediaFormat] = []
        # YouTube thumbnail URL patterns: .../hqdefault.jpg etc.
        import re

        m = re.search(r"/(hqdefault|mqdefault|sddefault|maxresdefault)(\.\w+)$", base)
        variants = [
            ("maxresdefault", "1920x1080"),
            ("sddefault", "640x480"),
            ("hqdefault", "480x360"),
            ("mqdefault", "320x180"),
        ]
        if m:
            stem, ext = base[: m.start()], m.group(2)
            for name, label in variants:
                out.append(
                    MediaFormat(
                        format_id=f"thumb:{name}",
                        label=f"Thumbnail {label}",
                        ext=ext.lstrip(".") or "jpg",
                        kind="thumbnail",
                        note=base,
                    )
                )
        else:
            out.append(
                MediaFormat(
                    format_id="thumb:orig",
                    label="Thumbnail (original)",
                    ext="jpg",
                    kind="thumbnail",
                    note=base,
                )
            )
        return out

    # -- download ------------------------------------------------------
    def download(
        self,
        resource: MediaResource,
        format: MediaFormat,
        dest_path: str,
        progress: Optional[ProgressCallback] = None,
    ) -> str:
        if format.kind == "thumbnail":
            return self._download_thumbnail(format, dest_path)
        return self._download_media(resource, format, dest_path, progress)

    def _download_media(
        self,
        resource: MediaResource,
        format: MediaFormat,
        dest_path: str,
        progress: Optional[ProgressCallback] = None,
    ) -> str:
        import yt_dlp

        ext = format.ext
        postprocessors: list[dict] = []
        ytdlp_format = format.format_id
        # Explicit audio extraction ("audio:mp3" etc.): take best audio and
        # transcode to the requested container. Native format ids are
        # downloaded as-is (source quality, no conversion).
        if format.format_id.startswith("audio:"):
            codec = format.format_id.split(":", 1)[1]
            if codec not in AUDIO_CODECS:
                raise ProviderError(f"Unsupported audio format: {codec}")
            ext = codec
            ytdlp_format = "bestaudio/best"
            postprocessors.append(
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": codec,
                    "preferredquality": "192",
                }
            )

        def hook(d: dict) -> None:
            if progress and d.get("status") == "downloading":
                progress(d.get("downloaded_bytes") or 0, d.get("total_bytes"))

        # yt-dlp decides the real extension; download to a temp name then move.
        tmp_base = dest_path + ".part"
        opts = _ytdlp_opts(
            {
                "format": ytdlp_format,
                "outtmpl": tmp_base + ".%(ext)s",
                "postprocessors": postprocessors,
                "progress_hooks": [hook],
            }
        )
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([resource.webpage_url])
        except Exception as e:  # noqa: BLE001
            raise self._normalize_error(e, resource.url) from e

        # Find the produced file (extension may differ after post-processing).
        produced: Optional[str] = None
        for cand in os.listdir(os.path.dirname(tmp_base) or "."):
            if cand.startswith(os.path.basename(tmp_base) + "."):
                produced = os.path.join(os.path.dirname(tmp_base), cand)
                break
        if not produced:
            raise ProviderError("Download finished but no file was produced.")
        os.replace(produced, dest_path)
        return dest_path

    def _download_thumbnail(self, format: MediaFormat, dest_path: str) -> str:
        import urllib.request

        from app.security import validate_public_url

        url = format.note  # thumbnail_formats() stores the URL in note
        if not url:
            raise ProviderError("No thumbnail URL available.")
        if format.format_id.startswith("thumb:"):
            name = format.format_id.split(":", 1)[1]
            import re

            url = re.sub(r"/(hqdefault|mqdefault|sddefault|maxresdefault)(\.\w+)$",
                         f"/{name}\\2", url)
        validate_public_url(url, allowed_hosts=("i.ytimg.com", "img.youtube.com"))
        req = urllib.request.Request(url, headers={"User-Agent": "media-tools/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp, open(dest_path, "wb") as f:
            f.write(resp.read())
        return dest_path

    # -- errors ---------------------------------------------------------
    @staticmethod
    def _normalize_error(e: Exception, url: str) -> ProviderError:
        msg = str(e).lower()
        if "private" in msg:
            return UnsupportedError("This video is private and cannot be accessed.")
        if "login" in msg or "sign in" in msg or "cookies" in msg:
            return UnsupportedError(
                "This video requires a YouTube login — not supported."
            )
        if "age" in msg and "confirm" in msg:
            return UnsupportedError(
                "This video is age-restricted and requires login — not supported."
            )
        if "unavailable" in msg or "not available" in msg or "removed" in msg:
            return NotFoundError("This video is unavailable or was removed.")
        if "unsupported url" in msg:
            return NotFoundError("This URL is not a supported YouTube link.")
        return ProviderError(f"YouTube error: {str(e)[:200]}")
