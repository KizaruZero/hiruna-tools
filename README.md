# media-tools — one for all

A single, clean, self-hosted web app that replaces scattered third-party
downloader/viewer sites: paste a URL, get metadata, pick a format, download.
No ads, no popups, no countdowns, no premium walls.

**Supported today**

| Paste a…       | You get…                                              |
|----------------|-------------------------------------------------------|
| YouTube URL    | metadata, video formats, audio extract (MP3/M4A/WAV), thumbnails |
| TikTok URL     | metadata + video download (public videos)             |
| Instagram URL  | clear message: requires login — not supported         |

Runs locally on your own machine. Nothing is uploaded anywhere; downloaded
files live in a temp folder and auto-delete after a couple of hours.

---

## Quick start

Requirements: Python 3.10+, `ffmpeg` (only needed for MP3/M4A/WAV extraction).

```bash
# macOS / Linux
./start.sh

# Windows
start.bat
```

Then open **http://127.0.0.1:8000**.

Manual equivalent:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m app
```

To expose on your LAN (e.g. phone on the same Wi-Fi): `HOST=0.0.0.0 PORT=8000 ./start.sh`
— only do this on networks you trust.

Optional configuration: copy `.env.example` to `.env` and edit
(retention time, size limits, rate limits, admin dashboard).

---

## Usage

1. Paste a URL into the box → **Analyze**.
2. The app detects the platform and shows title, author, duration, thumbnail,
   and every available format with sizes.
3. Pick a format → **Download**. Big files run as a background job with a
   progress bar; when it's ready you get a download link.
4. Links expire automatically (default: 2 hours, see `FILE_RETENTION_HOURS`).

Tips:

- For YouTube audio choose one of the explicit **Audio MP3 / M4A / WAV
  (converted)** rows. Plain audio rows download the source container as-is.
- Thumbnails are listed at the bottom of the format table.

---

## Troubleshooting

**"Sign in to confirm you're not a bot" / login-required errors**
YouTube sometimes walls off datacenter/VPN IPs. On a normal home connection
this rarely happens. The app prefers the Android player client first to
reduce this. If it persists, try again later or from another network.

**Audio extraction fails with "ffmpeg not found"**
Install ffmpeg: `sudo apt install ffmpeg` (Debian/Ubuntu),
`brew install ffmpeg` (macOS), or from https://ffmpeg.org (Windows),
then restart the app.

**Downloads are slow**
That's your connection + the platform's throttling. The job system keeps
the UI responsive; just leave the tab open.

**Port already in use**
`PORT=8080 ./start.sh` (or edit `.env`).

**"This website isn't supported yet"**
Only YouTube, TikTok, and Instagram URLs are recognized. See
CONTRIBUTING.md to add a provider.

**Instagram links always say "not supported"**
Correct — Instagram requires a logged-in session for all media access and
this tool deliberately does not use Instagram accounts or bypass login
walls. See KNOWN_LIMITATIONS.md.

---

## Project layout

```
app/
  main.py            FastAPI app + static frontend
  config.py          env-based settings
  security.py        SSRF protection, per-IP rate limiting
  providers/
    base.py          MediaProvider interface (implement this to add a site)
    registry.py      URL validation + platform detection
    youtube.py       yt-dlp backed (video/audio/thumbnail)
    tiktok.py        yt-dlp backed (video)
    instagram.py     honest "requires login" stub
  jobs/manager.py    background jobs, temp storage, auto-expiry
  api/routes.py      /api/analyze, /api/download, /api/jobs/*, /api/files/*
  static/index.html  single-page UI (no build step)
tests/               pytest suite (36 tests)
```

Docs: `ARCHITECTURE.md` (design), `API.md` (endpoints),
`KNOWN_LIMITATIONS.md` (honest limits), `CONTRIBUTING.md` (add a provider),
`BUILD_REPORT.md` (what was tested).

---

## Security & privacy

- Every pasted URL is validated: http(s) only, hostname allowlisted per
  provider, and SSRF-guarded (private/loopback/link-local IPs are refused
  after DNS resolution).
- No shell commands with user input — downloads go through yt-dlp's Python
  API; filenames are sanitized; temp paths are UUID-based.
- Per-IP rate limiting (configurable via env).
- No accounts, no tracking, no permanent media storage. Temp files expire
  automatically. Logs contain no media URLs.
- Public content only: no auth bypass, no private-account access, no DRM
  circumvention. See KNOWN_LIMITATIONS.md.
