# API reference

Base URL: `http://127.0.0.1:8000`. All request/response bodies are JSON
unless noted. Errors use `{"detail": "<human-readable message>"}` —
never stack traces.

Rate limiting applies to `POST /api/analyze` and `POST /api/download`
(429 with `Retry-After` when exceeded).

---

## GET /api/health

```json
{ "ok": true, "providers": ["youtube", "tiktok", "instagram"] }
```

## GET /api/providers

```json
{ "providers": [{"name": "youtube", "domains": ["youtube.com", "youtu.be", ...]}] }
```

## POST /api/analyze

```json
{ "url": "https://www.youtube.com/watch?v=..." }
```

Response:

```json
{
  "provider": "youtube",
  "resource": { "provider": "youtube", "resource_id": "...", "title": "...",
                "author": "...", "duration": 635.0, "thumbnail_url": "...",
                "webpage_url": "...", "url": "..." },
  "metadata": { "title": "...", "author": "...", "duration": 635.0,
                "view_count": 123, "upload_date": "20160405",
                "description": "...", "thumbnail_url": "...", "webpage_url": "..." },
  "capabilities": { "can_download_video": true, "can_download_audio": true,
                    "can_download_thumbnail": true, "can_view_metadata": true },
  "formats": [
    { "format_id": "18", "label": "360p", "ext": "mp4", "kind": "video",
      "width": 640, "height": 360, "filesize": 28526904,
      "abr": null, "vbr": null, "note": "with audio" },
    { "format_id": "audio:mp3", "label": "Audio MP3 (converted)", "ext": "mp3",
      "kind": "audio", "note": "converted from best available audio", ... }
  ],
  "thumbnails": [
    { "format_id": "thumb:maxresdefault", "label": "Thumbnail 1920x1080",
      "ext": "jpg", "kind": "thumbnail", ... }
  ]
}
```

Errors: `400` invalid URL / SSRF-blocked, `422` unsupported site or
content (e.g. private video, Instagram), `502` provider failure.

## POST /api/download

```json
{ "url": "https://www.youtube.com/watch?v=...", "format_id": "18" }
```

Use a `format_id` from the analyze response. Starts a background job:

```json
{ "job_id": "1379a00bf5c94e27b8017f3246b54fd4", "status": "queued" }
```

## GET /api/jobs/{job_id}

```json
{
  "id": "...", "kind": "download", "label": "Big Buck Bunny ...",
  "status": "running", "progress": 0.43,
  "downloaded_bytes": 12257280, "total_bytes": 28526904,
  "filename": "Big Buck Bunny ....mp4", "error": "",
  "created_at": "...", "finished_at": null, "expires_at": null
}
```

`status` is `queued` | `running` | `done` | `failed`. On `failed`,
`error` holds the human-readable reason.

## GET /api/files/{job_id}

Downloads the finished file (`200`, correct `Content-Type` and filename).
`404` while the job isn't done or after the file expired.

## Admin (optional)

Disabled unless `ENABLE_ADMIN=true` and `ADMIN_TOKEN` is set; pass the
token as `X-Admin-Token` header.

- `GET /api/admin/stats` — job counts by status, tmpdir disk usage.
- `POST /api/admin/cleanup` — run the expiry sweeper now.
