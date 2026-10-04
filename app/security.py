"""Security primitives: SSRF protection and per-IP rate limiting.

SSRF: every external URL is validated before any fetch. We resolve the
hostname and reject private, loopback, link-local, multicast, and
reserved ranges — including DNS-rebinding style answers where ANY
resolved address is non-public.
"""
from __future__ import annotations

import ipaddress
import socket
import time
from collections import deque
from threading import Lock
from urllib.parse import urlparse


class SecurityError(ValueError):
    """Raised for blocked/unsafe input. Message is safe to show to users."""


def _is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return (
        not addr.is_private
        and not addr.is_loopback
        and not addr.is_link_local
        and not addr.is_multicast
        and not addr.is_reserved
        and not addr.is_unspecified
    )


def _resolve_host(host: str) -> set[str]:
    """Resolve a hostname to its IP addresses (separate function so tests
    can stub DNS without touching socket globally)."""
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return {info[4][0] for info in infos}


def validate_public_url(url: str, allowed_hosts: tuple[str, ...] | None = None) -> str:
    """Validate a URL for safe server-side fetching.

    - scheme must be http/https
    - if allowed_hosts given, hostname must match the allowlist
    - hostname must resolve, and EVERY resolved IP must be public
    Returns the URL unchanged. Raises SecurityError otherwise.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SecurityError("Only http(s) URLs are allowed.")
    host = parsed.hostname
    if not host:
        raise SecurityError("URL has no hostname.")
    if allowed_hosts is not None:
        host_l = host.lower()
        if not any(host_l == h or host_l.endswith("." + h) for h in allowed_hosts):
            raise SecurityError(f"Host '{host}' is not allowed here.")
    try:
        ips = _resolve_host(host)
    except socket.gaierror:
        raise SecurityError(f"Could not resolve host '{host}'.") from None
    if not ips:
        raise SecurityError(f"Could not resolve host '{host}'.")
    for ip in ips:
        if not _is_public_ip(ip):
            raise SecurityError(
                "Refusing to fetch from a private/internal network address."
            )
    return url


class RateLimiter:
    """In-memory per-IP sliding-window rate limiter.

    Two tiers: a sustained per-minute rate and a short burst allowance.
    """

    def __init__(self, per_minute: int = 30, burst: int = 60):
        self.per_minute = per_minute
        self.burst = burst
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()

    def check(self, ip: str) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        now = time.monotonic()
        with self._lock:
            q = self._hits.setdefault(ip, deque())
            while q and q[0] <= now - 60:
                q.popleft()
            # Burst: no more than `burst` hits in the last 10 seconds.
            recent = sum(1 for t in q if t > now - 10)
            if recent >= self.burst or len(q) >= self.per_minute:
                retry = 1
                if q:
                    retry = max(1, int(q[0] + 60 - now))
                return False, retry
            q.append(now)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
