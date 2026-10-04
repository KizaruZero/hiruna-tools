"""HTTP API: analyze → download (as job) → poll → fetch file.

Flow:
    POST /api/analyze   {url}            -> metadata + formats + capabilities
    POST /api/download  {url, format_id} -> {job_id}  (background worker)
    GET  /api/jobs/{id}                  -> status / progress
    GET  /api/files/{job_id}            -> the finished file (until expiry)
"""
from __future__ import annotations

import os
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import settings
from app.jobs.manager import DONE, FAILED, manager
from app.providers.base import (
    Capabilities,
    MediaFormat,
    MediaResource,
    ProviderError,
    UnsupportedError,
)
from app.providers.registry import detect_provider, list_providers, validate_user_url
from app.providers.youtube import YouTubeProvider
from app.security import RateLimiter, SecurityError

router = APIRouter(prefix="/api")

_limiter = RateLimiter(
    per_minute=settings.rate_limit_per_minute, burst=settings.rate_limit_burst
)


def _client_ip(request: Request) -> str:
    # Local-first: trust direct remote address only (no proxy headers).
    return request.client.host if request.client else "unknown"


def rate_limited(request: Request) -> None:
    allowed, retry_after = _limiter.check(_client_ip(request))
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests — try again in {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )


def _provider_error(e: ProviderError) -> HTTPException:
    if isinstance(e, UnsupportedError):
        return HTTPException(status_code=422, detail=str(e))
    return HTTPException(status_code=502, detail=str(e))


# -- models ---------------------------------------------------------------
class AnalyzeRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    format_id: str


# -- endpoints -------------------------------------------------------------
@router.get("/health")
def health() -> dict:
    return {"ok": True, "providers": [p["name"] for p in list_providers()]}


@router.get("/providers")
def providers() -> dict:
    return {"providers": list_providers()}


@router.post("/analyze", dependencies=[Depends(rate_limited)])
def analyze(body: AnalyzeRequest) -> dict:
    try:
        url = validate_user_url(body.url)
    except (ValueError, SecurityError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    try:
        provider = detect_provider(url)
    except UnsupportedError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    try:
        resource = provider.resolve(url)
        metadata = provider.get_metadata(resource)
        capabilities = provider.get_capabilities(resource)
        formats = provider.get_available_formats(resource)
    except ProviderError as e:
        raise _provider_error(e) from e

    thumbnails: list[MediaFormat] = []
    if isinstance(provider, YouTubeProvider):
        thumbnails = provider.thumbnail_formats(resource)

    return {
        "provider": provider.name,
        "resource": _public_resource(resource),
        "metadata": metadata,
        "capabilities": asdict(capabilities),
        "formats": [asdict(f) for f in formats],
        "thumbnails": [asdict(f) for f in thumbnails],
    }


@router.post("/download", dependencies=[Depends(rate_limited)])
def download(body: DownloadRequest) -> dict:
    try:
        url = validate_user_url(body.url)
    except (ValueError, SecurityError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not body.format_id or len(body.format_id) > 128:
        raise HTTPException(status_code=400, detail="Invalid format selected.")
    try:
        provider = detect_provider(url)
    except UnsupportedError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    # Resolve + validate the format choice NOW (fast fail on bad input);
    # the actual bytes download in the background worker.
    try:
        resource = provider.resolve(url)
        fmt = _find_format(provider, resource, body.format_id)
    except ProviderError as e:
        raise _provider_error(e) from e
    if fmt is None:
        raise HTTPException(status_code=400, detail="Unknown format for this media.")

    label = (resource.title or "download")[:80]
    filename = f"{label}.{fmt.ext}"

    def work(dest_path: str, progress) -> None:
        # Re-resolve inside the worker: providers are stateless.
        res = provider.resolve(url)
        f2 = _find_format(provider, res, body.format_id)
        if f2 is None:
            raise ProviderError("Format no longer available.")
        provider.download(res, f2, dest_path, progress)

    job = manager.submit("download", label, filename, work)
    return {"job_id": job.id, "status": job.status}


@router.get("/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired.")
    return job.to_dict()


@router.get("/files/{job_id}")
def get_file(job_id: str):
    job = manager.get(job_id)
    if not job or job.status != DONE:
        raise HTTPException(status_code=404, detail="File not ready or expired.")
    if not job.file_path or not os.path.exists(job.file_path):
        raise HTTPException(status_code=404, detail="File expired and was cleaned up.")
    import mimetypes

    media_type = mimetypes.guess_type(job.filename)[0] or "application/octet-stream"
    return FileResponse(
        job.file_path, media_type=media_type, filename=job.filename
    )


@router.get("/admin/stats")
def admin_stats(request: Request) -> dict:
    if not settings.enable_admin:
        raise HTTPException(status_code=404, detail="Not found.")
    token = request.headers.get("x-admin-token", "")
    if not settings.admin_token or token != settings.admin_token:
        raise HTTPException(status_code=403, detail="Forbidden.")
    return {
        "jobs": manager.stats(),
        "providers": [p["name"] for p in list_providers()],
        "rate_limit_per_minute": settings.rate_limit_per_minute,
    }


@router.post("/admin/cleanup")
def admin_cleanup(request: Request) -> dict:
    if not settings.enable_admin:
        raise HTTPException(status_code=404, detail="Not found.")
    token = request.headers.get("x-admin-token", "")
    if not settings.admin_token or token != settings.admin_token:
        raise HTTPException(status_code=403, detail="Forbidden.")
    removed = manager.sweep()
    return {"removed_files": removed}


# -- helpers ---------------------------------------------------------------
def _public_resource(r: MediaResource) -> dict:
    return {
        "provider": r.provider,
        "url": r.url,
        "resource_id": r.resource_id,
        "title": r.title,
        "author": r.author,
        "duration": r.duration,
        "thumbnail_url": r.thumbnail_url,
        "webpage_url": r.webpage_url,
    }


def _find_format(provider, resource: MediaResource, format_id: str):
    for f in provider.get_available_formats(resource):
        if f.format_id == format_id:
            return f
    if isinstance(provider, YouTubeProvider):
        for f in provider.thumbnail_formats(resource):
            if f.format_id == format_id:
                return f
    # Audio-extraction shortcuts offered by the API even if not in the
    # raw format list (e.g. user picked "mp3" from the audio section).
    if format_id.startswith("audio:"):
        codec = format_id.split(":", 1)[1]
        if codec in ("mp3", "m4a", "wav", "opus"):
            return MediaFormat(
                format_id=format_id, label=f"Audio {codec.upper()}",
                ext=codec, kind="audio",
            )
    return None
