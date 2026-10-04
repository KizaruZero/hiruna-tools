"""Tests for media-tools. No network-heavy tests here — provider internals
that need the network are covered by the manual end-to-end test (BUILD_REPORT.md).
"""
import ipaddress
import os
import time

import pytest

os.environ.setdefault("DATA_DIR", "/tmp/mt-test-data")

from app.providers import registry  # noqa: E402
from app.providers.base import UnsupportedError  # noqa: E402
from app.security import RateLimiter, SecurityError, validate_public_url  # noqa: E402
import app.security as _security  # noqa: E402


@pytest.fixture(autouse=True)
def _dns_stub(monkeypatch):
    """This sandbox resolves every external hostname to a 198.18/15 proxy
    address (not globally routable), which the SSRF check correctly rejects.
    For tests, pretend external names resolve to a public IP while keeping
    real DNS for localhost / IP literals so the SSRF-block tests stay honest.
    """
    real_resolve = _security._resolve_host

    def fake(host: str):
        try:
            ipaddress.ip_address(host)
            return real_resolve(host)  # IP literal: real resolution
        except ValueError:
            pass
        if host in ("localhost",):
            return real_resolve(host)
        return {"93.184.216.34"}  # documentation example IP (public)

    monkeypatch.setattr(_security, "_resolve_host", fake)


# -- URL validation / provider detection ---------------------------------
class TestUrlValidation:
    def test_empty_url(self):
        with pytest.raises(ValueError):
            registry.validate_user_url("")

    def test_bad_scheme(self):
        with pytest.raises(ValueError):
            registry.validate_user_url("ftp://example.com/x")

    def test_missing_scheme_gets_https(self):
        assert registry.validate_user_url("youtube.com/watch?v=abc").startswith("https://")

    def test_too_long(self):
        with pytest.raises(ValueError):
            registry.validate_user_url("https://x.com/" + "a" * 3000)

    def test_ssrf_localhost_blocked(self):
        with pytest.raises(SecurityError):
            registry.validate_user_url("http://localhost:8000/admin")

    def test_ssrf_loopback_blocked(self):
        with pytest.raises(SecurityError):
            registry.validate_user_url("http://127.0.0.1/secret")

    def test_ssrf_link_local_blocked(self):
        with pytest.raises(SecurityError):
            registry.validate_user_url("http://169.254.169.254/latest/meta-data/")

    def test_ssrf_private_range_blocked(self):
        with pytest.raises(SecurityError):
            registry.validate_user_url("http://10.0.0.5/")


class TestProviderDetection:
    @pytest.mark.parametrize("url,expected", [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
        ("https://youtu.be/dQw4w9WgXcQ", "youtube"),
        ("https://music.youtube.com/watch?v=abc", "youtube"),
        ("https://www.tiktok.com/@user/video/123", "tiktok"),
        ("https://vt.tiktok.com/abc123/", "tiktok"),
        ("https://www.instagram.com/p/abc/", "instagram"),
    ])
    def test_detect(self, url, expected):
        assert registry.detect_provider(url).name == expected

    def test_unsupported_site(self):
        with pytest.raises(UnsupportedError):
            registry.detect_provider("https://vimeo.com/12345")

    def test_instagram_resolve_raises_unsupported(self):
        provider = registry.detect_provider("https://www.instagram.com/p/abc/")
        with pytest.raises(UnsupportedError):
            provider.resolve("https://www.instagram.com/p/abc/")


# -- SSRF unit tests -------------------------------------------------------
class TestValidatePublicUrl:
    def test_allows_public_ip(self):
        # 8.8.8.8 is public; no fetch happens, only validation.
        assert validate_public_url("http://8.8.8.8/") == "http://8.8.8.8/"

    def test_blocks_private_ip_literal(self):
        with pytest.raises(SecurityError):
            validate_public_url("http://192.168.1.1/")

    def test_blocks_loopback_literal(self):
        with pytest.raises(SecurityError):
            validate_public_url("http://127.0.0.1/")

    def test_blocks_multicast(self):
        with pytest.raises(SecurityError):
            validate_public_url("http://224.0.0.1/")

    def test_rejects_non_http_scheme(self):
        with pytest.raises(SecurityError):
            validate_public_url("file:///etc/passwd")

    def test_host_allowlist(self):
        validate_public_url("https://i.ytimg.com/vi/abc/hqdefault.jpg",
                            allowed_hosts=("i.ytimg.com",))
        with pytest.raises(SecurityError):
            validate_public_url("https://evil.com/x.jpg",
                                allowed_hosts=("i.ytimg.com",))


# -- rate limiter -----------------------------------------------------------
class TestRateLimiter:
    def test_allows_under_limit(self):
        rl = RateLimiter(per_minute=5, burst=5)
        for _ in range(5):
            allowed, _ = rl.check("1.2.3.4")
            assert allowed

    def test_blocks_over_limit(self):
        rl = RateLimiter(per_minute=3, burst=3)
        for _ in range(3):
            rl.check("1.2.3.4")
        allowed, retry = rl.check("1.2.3.4")
        assert not allowed and retry >= 1

    def test_per_ip_isolation(self):
        rl = RateLimiter(per_minute=1, burst=1)
        rl.check("1.1.1.1")
        allowed, _ = rl.check("2.2.2.2")
        assert allowed


# -- job manager -------------------------------------------------------------
class TestJobManager:
    def _manager(self):
        from app.jobs.manager import JobManager
        return JobManager()

    def test_successful_job(self):
        mgr = self._manager()

        def work(dest, progress):
            with open(dest, "w") as f:
                f.write("hello")
            progress(5, 5)

        job = mgr.submit("download", "label", "test.txt", work)
        deadline = time.time() + 10
        while job.status not in ("done", "failed") and time.time() < deadline:
            time.sleep(0.05)
        assert job.status == "done"
        assert job.progress == 1.0
        assert os.path.exists(job.file_path)

    def test_failed_job(self):
        mgr = self._manager()

        def work(dest, progress):
            raise RuntimeError("boom")

        job = mgr.submit("download", "label", "x.bin", work)
        deadline = time.time() + 10
        while job.status not in ("done", "failed") and time.time() < deadline:
            time.sleep(0.05)
        assert job.status == "failed"
        assert "boom" in job.error

    def test_expiry_sweep_removes_file(self):
        from datetime import datetime, timedelta, timezone

        from app.jobs.manager import DONE

        mgr = self._manager()

        def work(dest, progress):
            with open(dest, "w") as f:
                f.write("x")

        job = mgr.submit("download", "label", "y.txt", work)
        deadline = time.time() + 10
        while job.status != DONE and time.time() < deadline:
            time.sleep(0.05)
        assert os.path.exists(job.file_path)
        # Force expiry into the past, then sweep.
        job.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        removed = mgr.sweep()
        assert removed >= 1
        assert not os.path.exists(job.file_path)
        assert mgr.get(job.id) is None

    def test_filename_sanitized(self):
        from app.jobs.manager import _safe_filename

        assert _safe_filename("../../etc/passwd") == "passwd"
        assert "/" not in _safe_filename("a/b\\c")
        assert len(_safe_filename("x" * 500)) <= 120


# -- API error paths (no network) --------------------------------------------
class TestApiErrors:
    def _client(self):
        from fastapi.testclient import TestClient

        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def test_analyze_empty_url_400(self):
        r = self._client().post("/api/analyze", json={"url": ""})
        assert r.status_code == 400

    def test_analyze_unsupported_site_422(self):
        r = self._client().post("/api/analyze", json={"url": "https://vimeo.com/123"})
        assert r.status_code == 422

    def test_analyze_instagram_unsupported_422(self):
        r = self._client().post(
            "/api/analyze", json={"url": "https://www.instagram.com/p/abc123/"})
        assert r.status_code == 422
        assert "Instagram" in r.json()["detail"]

    def test_analyze_ssrf_blocked_400(self):
        r = self._client().post("/api/analyze", json={"url": "http://127.0.0.1:9/"})
        assert r.status_code == 400

    def test_job_not_found_404(self):
        r = self._client().get("/api/jobs/doesnotexist")
        assert r.status_code == 404

    def test_health(self):
        r = self._client().get("/api/health")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_admin_disabled_by_default(self):
        r = self._client().get("/api/admin/stats")
        assert r.status_code == 404
