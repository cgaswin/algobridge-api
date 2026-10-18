import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api.v1.routes.problems import router
from app.config.settings import Settings
from app.core.exception_handlers import register_exception_handlers
from app.core.rate_limit import IPRateLimiter, IPRateLimitMiddleware


@pytest.fixture
def limited_app(monkeypatch):
    now = [100.0]
    limiter = IPRateLimiter(2, 60, 3, clock=lambda: now[0])
    service = AsyncMock(return_value={"use_case": "test"})
    monkeypatch.setattr("app.api.v1.routes.problems.analyze_problem", service)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.add_middleware(IPRateLimitMiddleware, limiter=limiter)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app, now, service


def post(client, **kwargs):
    return client.post(
        "/api/v1/problems",
        json={"url": "https://leetcode.com/problems/two-sum/"},
        **kwargs,
    )


def test_same_ip_different_ports_and_different_ips(limited_app):
    app, now, service = limited_app
    with TestClient(app, client=("192.0.2.1", 1000)) as client:
        assert post(client).status_code == 200
        assert post(client).status_code == 200
    now[0] += 0.1
    with TestClient(app, client=("192.0.2.1", 2000)) as client:
        response = post(client)
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "60"
        assert response.json() == {
            "success": False,
            "data": None,
            "error": {
                "code": "RATE_LIMITED",
                "message": "Too many requests. Please retry later.",
                "details": {},
            },
        }
        # Rejection short circuits before any service/DB/LeetCode/Gemini work.
        assert service.await_count == 2
        now[0] = 159.1
        assert post(client).headers["Retry-After"] == "1"
        assert client.get("/health").status_code == 200
        assert client.options("/api/v1/problems").status_code == 405
    with TestClient(app, client=("192.0.2.2", 1000)) as client:
        assert post(client).status_code == 200
    now[0] = 160.0
    with TestClient(app, client=("192.0.2.1", 1000)) as client:
        assert post(client).status_code == 200
    assert service.await_count == 4


def test_invalid_requests_count_and_health_does_not(limited_app):
    app, _, service = limited_app
    with TestClient(app) as client:
        for _ in range(4):
            assert client.get("/health").status_code == 200
        assert (
            client.post(
                "/api/v1/problems",
                content="{",
                headers={"Content-Type": "application/json"},
            ).status_code
            == 422
        )
        assert client.post("/api/v1/problems", json={}).status_code == 422
        assert post(client).status_code == 429
        assert client.post("/api/v1/problems/", json={}).status_code == 429
    service.assert_not_awaited()


def test_untrusted_forwarding_cannot_change_ip(limited_app):
    app, _, service = limited_app
    # Same middleware as Uvicorn: only the configured proxy network is trusted.
    wrapped = ProxyHeadersMiddleware(app, trusted_hosts="10.1.0.0/24")
    with TestClient(wrapped, client=("192.0.2.1", 1234)) as client:
        for i in range(2):
            assert (
                post(client, headers={"X-Forwarded-For": f"198.51.100.{i}"}).status_code
                == 200
            )
        assert (
            post(client, headers={"X-Forwarded-For": "198.51.100.3"}).status_code == 429
        )
    assert service.await_count == 2


def test_verified_proxy_uses_rightmost_untrusted_address(limited_app):
    app, _, service = limited_app
    wrapped = ProxyHeadersMiddleware(app, trusted_hosts="10.1.0.0/24")
    with TestClient(wrapped, client=("10.1.0.1", 1234)) as client:
        # Proxy appends real client; changing a spoofed prefix cannot reset quota.
        for i in range(2):
            assert (
                post(
                    client,
                    headers={"X-Forwarded-For": f"203.0.113.{i}, 192.0.2.1, 10.1.0.2"},
                ).status_code
                == 200
            )
        assert (
            post(
                client, headers={"X-Forwarded-For": "203.0.113.3, 192.0.2.1, 10.1.0.2"}
            ).status_code
            == 429
        )
        assert post(client, headers={"X-Forwarded-For": "192.0.2.2"}).status_code == 200
    assert service.await_count == 3


def test_no_trusted_proxies_by_default(limited_app):
    app, _, _ = limited_app
    wrapped = ProxyHeadersMiddleware(app, trusted_hosts="")
    with TestClient(wrapped, client=("127.0.0.1", 1234)) as client:
        for i in range(2):
            assert (
                post(client, headers={"X-Forwarded-For": f"192.0.2.{i}"}).status_code
                == 200
            )
        assert post(client, headers={"X-Forwarded-For": "192.0.2.3"}).status_code == 429


def test_rejection_precedes_body_parsing_and_preserves_cors(limited_app):
    from fastapi.middleware.cors import CORSMiddleware

    from app.main import cors_options

    app, _, service = limited_app
    app.add_middleware(CORSMiddleware, **cors_options)
    origin = "chrome-extension://" + "a" * 32
    with TestClient(app) as client:
        preflight = client.options(
            "/api/v1/problems",
            headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
        )
        assert preflight.status_code == 200
        assert post(client).status_code == 200
        assert post(client).status_code == 200
        response = client.post(
            "/api/v1/problems", content=b"not json", headers={"Origin": origin}
        )
        assert response.status_code == 429
        assert response.headers["Access-Control-Allow-Origin"] == origin
        assert response.headers["Access-Control-Expose-Headers"] == "Retry-After"
        assert response.headers["Retry-After"] == "60"
    assert service.await_count == 2


def test_ipv6_spellings_share_a_quota(limited_app):
    app, _, service = limited_app
    with TestClient(app, client=("2001:db8::1", 1)) as client:
        assert post(client).status_code == 200
        assert post(client).status_code == 200
    with TestClient(app, client=("2001:0db8:0:0:0:0:0:1", 2)) as client:
        assert post(client).status_code == 429
    assert service.await_count == 2


def test_unknown_peers_share_a_quota(limited_app):
    app, _, _ = limited_app
    with TestClient(app, client=None) as client:
        assert post(client).status_code == 200
        assert post(client).status_code == 200
        assert post(client).status_code == 429


def test_bounded_state_fails_closed_without_evicting_live_quotas():
    now = [0.0]
    limiter = IPRateLimiter(1, 60, 2, clock=lambda: now[0])
    assert limiter.retry_after("one") == 0
    now[0] = 10.0
    assert limiter.retry_after("two") == 0
    for i in range(100):
        assert limiter.retry_after(f"new-{i}") == 50
    assert len(limiter._windows) == 2
    assert limiter.retry_after("one") == 50
    now[0] = 60.0
    assert limiter.retry_after("new") == 0
    assert len(limiter._windows) == 2
    assert limiter.retry_after("two") == 10
    now[0] = 120.0
    assert limiter.retry_after("fresh") == 0
    assert len(limiter._windows) == 1


def test_concurrent_requests_cannot_overspend_quota():
    limiter = IPRateLimiter(5, 60, 10)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(limiter.retry_after, ["same"] * 100))
    assert results.count(0) == 5


@pytest.mark.parametrize(
    "field", ["rate_limit_requests", "rate_limit_window_seconds", "rate_limit_max_ips"]
)
@pytest.mark.parametrize("value", [0, -1, "invalid", 1.5])
def test_invalid_configuration(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, gemini_api_key="test-placeholder", **{field: value})


def test_configuration_from_environment(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "7")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "30")
    monkeypatch.setenv("RATE_LIMIT_MAX_IPS", "100")
    settings = Settings(_env_file=None, gemini_api_key="test-placeholder")
    assert (
        settings.rate_limit_requests,
        settings.rate_limit_window_seconds,
        settings.rate_limit_max_ips,
    ) == (7, 30, 100)


@pytest.mark.parametrize(
    "value", ["*", "0.0.0.0/0", "::/0", "garbage", "10.1.2.3/24", "10.1.2.3,"]
)
def test_invalid_proxy_configuration(value):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None, gemini_api_key="test-placeholder", forwarded_allow_ips=value
        )


@pytest.mark.parametrize("value", ["", "10.1.2.3", "10.1.2.0/24, ::1"])
def test_valid_proxy_configuration(value):
    assert (
        Settings(
            _env_file=None, gemini_api_key="test-placeholder", forwarded_allow_ips=value
        ).forwarded_allow_ips
        == value
    )


def test_start_script_proxy_default_and_explicit_values(tmp_path):
    # Stub migrations/server; never connect to a DB or run a real server.
    for command in ("alembic", "uvicorn"):
        executable = tmp_path / command
        executable.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
        executable.chmod(0o755)
    script = Path(__file__).resolve().parents[1] / "scripts/start.sh"
    env = {"PATH": f"{tmp_path}:/usr/bin:/bin"}
    for value in (None, "10.1.2.3,10.2.0.0/16"):
        configured = env.copy()
        if value is not None:
            configured["FORWARDED_ALLOW_IPS"] = value
        result = subprocess.run(
            ["sh", str(script)], env=configured, capture_output=True, text=True
        )
        assert result.returncode == 0
        assert f"--forwarded-allow-ips={value or ''}\n" in result.stdout
    result = subprocess.run(
        ["sh", str(script)],
        env={**env, "FORWARDED_ALLOW_IPS": "*"},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "upgrade" not in result.stdout


def test_real_app_has_limiter_inside_cors():
    from fastapi.middleware.cors import CORSMiddleware

    from app.main import app

    classes = [middleware.cls for middleware in app.user_middleware]
    assert classes.index(CORSMiddleware) < classes.index(IPRateLimitMiddleware)
