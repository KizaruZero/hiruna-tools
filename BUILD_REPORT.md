# Build report — media-tools v1.0

Built 2026-10-04 in `~/workspace/media-tools/`. Local-first (no Docker):
`./start.sh` → http://127.0.0.1:8000.

## What was built

- **Universal URL input + platform detection** — paste any link, the app
  validates it (scheme/host/SSRF), detects YouTube / TikTok / Instagram,
  and shows applicable actions.
- **YouTube (fully working)** — metadata, format listing (video + native
  audio + explicit MP3/M4A/WAV extraction), 4 thumbnail resolutions,
  background downloads, file serving.
- **TikTok (implemented)** — metadata + video download via yt-dlp's
  normal public extraction; no watermark stripping, no bypasses.
- **Instagram (honest stub)** — detects IG URLs and returns a clear
  "requires login — not supported" message instead of failing obscurely.
- **Job system** — downloads run in a worker thread pool; progress
  polling; temp files auto-expire (default 2h) with a sweeper thread.
- **Security** — SSRF protection (DNS resolve + private/loopback/
  link-local/multicast/reserved rejection), per-IP rate limiting
  (env-configurable), sanitized filenames, UUID temp paths, no shell
  usage, human-readable errors (no stack traces to clients).
- **Frontend** — single clean page matching the spec mockup (paste URL →
  Analyze → preview + format table → Download → progress → link).
- **Docs** — README, ARCHITECTURE, API, KNOWN_LIMITATIONS, CONTRIBUTING
  (new-provider guide), .env.example, start.sh/start.bat, requirements.txt.

## What was tested

- **pytest: 36/36 pass** — URL validation, provider detection (6 URL
  shapes), invalid/unsupported URLs, SSRF blocks (localhost, 127.0.0.1,
  169.254.169.254, 10.x, 192.168.x, multicast, file://), host allowlist,
  rate limiter (limits + per-IP isolation), job lifecycle
  (success/failure/progress), expiry sweep deletes files + prunes jobs,
  filename sanitization, API error paths (400/404/422), admin disabled
  by default.
- **Live end-to-end** (uvicorn + curl, Big Buck Bunny 4K):
  - `POST /api/analyze` → metadata + 4 formats + 4 thumbnails ✓
  - `POST /api/download` (360p mp4) → poll → `done` → `GET /api/files`
    → 28 MB valid MP4 ✓
  - MP3 extraction (`audio:mp3`) → 15 MB, 192 kbps, ID3-tagged ✓
  - Thumbnail (`thumb:hqdefault`) → valid WebP served ✓
  - Frontend `/` → 200, correct page ✓
  - Age-restricted video → clean 422 "requires a YouTube login" (no
    stack trace) ✓
  - Instagram URL → clean 422 explanatory message ✓

## Test-environment notes (not app bugs)

- This sandbox resolves external DNS to 198.18/15 proxy addresses and
  MITMs TLS with a custom CA. The app's SSRF check correctly rejects
  those; for tests, DNS was stubbed to a public documentation IP
  (test-only fixture) and the proxy CA was appended to the venv's
  certifi bundle. On a normal machine none of this is needed.
- YouTube served "sign in to confirm you're not a bot" to this sandbox's
  egress IP on the web player client. The app now prefers the Android
  player client first (official public API surface, no auth) with web
  fallback — documented in code. If the wall appears for a user, the
  error message says exactly that.

## Known limitations (see KNOWN_LIMITATIONS.md)

- Instagram: unsupported by design (login wall, no bypasses).
- TikTok: implemented but **not live-tested** here (no test URL handy in
  the sandbox); uses the same yt-dlp machinery as YouTube.
- YouTube age-restricted/private/members-only: not supported (no accounts).
- Playlists rejected (single videos only).
- No generic converter tools yet (architecture ready, see CONTRIBUTING.md).

## Not done (parent handles)

- GitHub repo creation + push — intentionally left to the parent agent.
