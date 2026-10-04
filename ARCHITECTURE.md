# Architecture

media-tools is a small, modular monolith. Local-first: everything runs in
one Python process, no database, no Redis, no Docker.

```
Browser (single-page UI: app/static/index.html)
   │  JSON over HTTP
   ▼
FastAPI (app/main.py, app/api/routes.py)
   │
   ├─► Provider registry (app/providers/registry.py)
   │     validate URL → SSRF check → detect platform
   │         │
   │         ▼
   │     MediaProvider interface (app/providers/base.py)
   │       ├── YouTubeProvider   (yt-dlp, video/audio/thumbnail)
   │       ├── TikTokProvider    (yt-dlp, video)
   │       └── InstagramProvider (honest "login required" stub)
   │
   ├─► JobManager (app/jobs/manager.py)
   │     ThreadPoolExecutor workers → temp files in DATA_DIR/tmp
   │     sweeper thread → expiry + cleanup
   │
   └─► Security (app/security.py)
         SSRF validation, per-IP sliding-window rate limiter
```

## Why this shape

- **Provider abstraction.** Social sites change their internals constantly.
  All platform knowledge lives behind `MediaProvider`
  (`resolve / get_metadata / get_available_formats / download`), so fixing
  YouTube never touches TikTok code or the API layer. See CONTRIBUTING.md.
- **Jobs, not blocking requests.** Downloads stream for minutes; the HTTP
  request only creates a job and returns an id. The browser polls
  `GET /api/jobs/{id}` and fetches `GET /api/files/{job_id}` when done.
- **Temp storage with expiry.** Files land in `DATA_DIR/tmp/<uuid>-<name>`,
  get a timestamped expiry (`FILE_RETENTION_HOURS`), and a sweeper thread
  deletes them. A second pass removes stray files older than 2× retention.
- **No shell.** yt-dlp is used via its Python API; ffmpeg only runs through
  yt-dlp's postprocessor interface. Filenames are sanitized and temp paths
  are UUID-based, so there is no command-injection or path-traversal
  surface from user input.
- **Defense in depth on URLs.** Scheme check → per-provider host allowlist
  → DNS resolution → reject non-public IPs (private, loopback, link-local,
  multicast, reserved). Thumbnail fetches re-validate against an even
  tighter host allowlist.

## Request flows

**Analyze** (fast, synchronous):
`POST /api/analyze {url}` → validate → detect provider → `resolve()` →
`get_metadata()` + `get_available_formats()` (+ thumbnails for YouTube) →
JSON. Any provider failure becomes a 4xx/502 with a human-readable
message; stack traces never reach the client.

**Download** (background):
`POST /api/download {url, format_id}` → validate → re-resolve + verify the
format id exists → `JobManager.submit()` → `{job_id}` → worker thread
downloads → `done`/`failed`. Client polls `GET /api/jobs/{id}`, then
`GET /api/files/{job_id}` (FileResponse, correct MIME + filename).

## Configuration

Everything is env-driven (`app/config.py`, see `.env.example`). Notable
knobs: `FILE_RETENTION_HOURS`, `MAX_FILE_MB`, `MAX_JOB_SECONDS`,
`RATE_LIMIT_PER_MINUTE` / `RATE_LIMIT_BURST`, `DATA_DIR`, and the optional
admin dashboard (`ENABLE_ADMIN` + `ADMIN_TOKEN` → `GET /api/admin/stats`,
`POST /api/admin/cleanup`).

## What was deliberately left out (v1)

- No user accounts, no database — nothing needs to persist.
- No distributed queue — one machine, one process, thread pool of 2.
- No video/audio *conversion* tools beyond yt-dlp's audio extraction;
  the module layout (`providers/`, `jobs/`) is ready for a future
  `app/tools/` section (see Phase 3 in the original spec).
