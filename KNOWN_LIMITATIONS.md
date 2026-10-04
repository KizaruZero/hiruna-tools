# Known limitations — read this before expecting magic

This tool is honest about what platforms allow. Anything below is a
platform or legal constraint, not a bug.

## YouTube

- **Bot checks.** YouTube increasingly shows "Sign in to confirm you're not
  a bot" to datacenter/VPN IPs. The app prefers the Android player client
  (an official public API surface, no credentials) which usually works, and
  surfaces a clear error when it doesn't. On a normal home connection this
  is rare.
- **Age-restricted / private / members-only videos** are not supported —
  they require a login, and this tool does not use YouTube accounts.
- **Format availability varies.** YouTube serves different formats per
  video/client; the app shows exactly what the platform returns, never
  upscaled or mislabeled qualities.
- **Playlists** are rejected — paste a single video URL.

## TikTok

- Public videos download via yt-dlp's normal extraction. What you get is
  whatever TikTok's public endpoints return; the app does not strip
  watermarks, spoof devices, or bypass any access control.
- Availability fluctuates with TikTok's anti-bot measures. Private,
  friends-only, or login-walled content returns a clear "not supported"
  error.
- No story viewer: TikTok stories are ephemeral and auth-gated.

## Instagram

- **Not supported, by design.** Since 2024 Instagram requires a logged-in
  session for essentially all media (posts, reels, stories) and
  aggressively rate-limits anonymous access. This tool does not use
  Instagram accounts, session cookies, or scrapers that bypass login
  walls, so every Instagram URL returns a clear explanatory error instead
  of failing mysteriously. If you own the content, use the Instagram
  app's own download/share options.

## General

- **No DRM / paywall circumvention**, ever. If content needs an account,
  purchase, or subscription, the app says so instead of trying to get
  around it.
- **Copyright is your responsibility.** This is a personal-utility tool:
  download content you own or are allowed to keep.
- **No video/audio conversion tools yet** beyond YouTube audio extraction
  (MP3/M4A/WAV). The architecture is ready for a future tools section.
- **Single machine.** No multi-user auth, no clustering — it's designed
  for one person on one machine.
- **Thumbnails** come from the platform's own thumbnail URLs at the
  resolutions the platform publishes.
