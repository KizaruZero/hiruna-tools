# Contributing — adding a provider (or a tool)

## Adding a new platform provider

Adding support for a new site (e.g. Vimeo, Dailymotion, SoundCloud) means
implementing **one file** plus two lines of registration. Nothing else
changes: the API, job system, frontend, and security layers talk only to
the `MediaProvider` interface.

### 1. Create `app/providers/<name>.py`

```python
from .base import (Capabilities, MediaFormat, MediaProvider, MediaResource,
                   UnsupportedError)

class VimeoProvider(MediaProvider):
    name = "vimeo"
    domains = ("vimeo.com", "player.vimeo.com")

    def resolve(self, url: str) -> MediaResource: ...
    def get_metadata(self, resource: MediaResource) -> dict: ...
    def get_available_formats(self, resource: MediaResource) -> list[MediaFormat]: ...
    def get_capabilities(self, resource: MediaResource) -> Capabilities: ...
    def download(self, resource, format, dest_path, progress=None) -> str: ...
```

Rules for the implementation:

- **Public content only.** If the platform needs a login, paid access, or
  private-account approval, raise `UnsupportedError("...")` with a
  human-readable explanation — like `instagram.py` does. Never add
  credential handling, session spoofing, or wall bypasses.
- **No `shell=True`, no subprocess with user input.** Prefer a Python API
  (like yt-dlp's). If you must shell out, use `subprocess.run([...])`
  with a fixed argument list and a sanitized output path.
- **Reuse `_ytdlp_opts()`** from `youtube.py` if the site is supported by
  yt-dlp — you get timeouts, no-playlist, and safe output templates free.
- **Map errors to the right exception:** `UnsupportedError` (private /
  login-walled / removed-by-platform-policy), `NotFoundError` (dead link),
  `ProviderError` (anything else, message must be human-readable —
  it is shown to the user).
- `download()` must honor the `progress(downloaded, total)` callback and
  write **only** to `dest_path` (a UUID-based temp path the job system
  gives you).

### 2. Register it

In `app/providers/registry.py`, import the class and add an instance to
`_PROVIDERS` (order = detection priority).

### 3. Test it

Add cases to `tests/test_app.py`:
`TestProviderDetection.test_detect` parametrize list, plus invalid-URL and
SSRF cases if you add new host patterns. Run `pytest`.

### 4. Document limits

Add a section to `KNOWN_LIMITATIONS.md` describing what the platform
allows and what it doesn't. Honesty is a feature.

## Adding a generic media tool (Phase 3)

The planned `app/tools/` section (converters, compressors, metadata
viewer) should follow the same pattern: one module per tool exposing

```python
def describe() -> dict:   # name, inputs, options for the UI
def run(job, inputs, options, dest_path, progress) -> str: ...
```

and reuse `JobManager.submit()` + the temp-storage/expiry machinery.
Tools must validate inputs with `app.security.validate_public_url()` when
they fetch remote files, and enforce `MAX_FILE_MB` / `MAX_JOB_SECONDS`.

## Code style

- Keep it small and readable; no frameworks beyond FastAPI.
- Type hints on public functions.
- Human-readable errors everywhere; no stack traces to clients.
- No secrets in code, ever. Runtime config goes through env (see
  `.env.example`).
