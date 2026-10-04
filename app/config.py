"""Central configuration, loaded from environment variables.

All values have safe defaults so the app runs with zero configuration:
    python -m app

Copy .env.example to .env to override.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    # Network
    host: str = os.environ.get("HOST", "127.0.0.1")
    port: int = _int("PORT", 8000)

    # Temp storage / job lifecycle
    data_dir: str = os.environ.get("DATA_DIR", os.path.expanduser("~/.media-tools"))
    file_retention_hours: float = _float("FILE_RETENTION_HOURS", 2.0)
    max_file_mb: int = _int("MAX_FILE_MB", 1024)
    max_job_seconds: int = _int("MAX_JOB_SECONDS", 1800)
    cleanup_interval_seconds: int = _int("CLEANUP_INTERVAL_SECONDS", 300)

    # Rate limiting (per IP, sliding window)
    rate_limit_per_minute: int = _int("RATE_LIMIT_PER_MINUTE", 30)
    rate_limit_burst: int = _int("RATE_LIMIT_BURST", 60)

    # External tooling
    ffmpeg_path: str = os.environ.get("FFMPEG_PATH", "ffmpeg")
    ytdlp_socket_timeout: int = _int("YTDLP_SOCKET_TIMEOUT", 30)

    # Admin/debug dashboard (optional, off by default)
    admin_token: str = os.environ.get("ADMIN_TOKEN", "")
    enable_admin: bool = os.environ.get("ENABLE_ADMIN", "false").lower() in ("1", "true", "yes")

    def __post_init__(self) -> None:
        os.makedirs(os.path.join(self.data_dir, "tmp"), exist_ok=True)


settings = Settings()
