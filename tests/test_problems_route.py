from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

fake_insights = {
    "use_case": "caching",
    "system_examples": ["Redis — key lookup"],
    "explanation": "hash maps are fast",
}


@pytest.mark.anyio
async def test_analyze_problem_valid_url():
    with patch(
        "app.api.v1.routes.problems.analyze_problem",
        AsyncMock(return_value=fake_insights),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/problems",
                json={"url": "https://leetcode.com/problems/two-sum/"},
            )
    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.anyio
async def test_analyze_problem_missing_url():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/v1/problems", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "INVALID_INPUT"
    assert body["error"]["message"] == "Request validation failed"
    assert isinstance(body["error"]["details"], list)


@pytest.mark.anyio
async def test_analyze_problem_invalid_url():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/problems",
            json={"url": "not-a-url"},
        )
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "INVALID_INPUT"
    assert body["error"]["message"] == "Request validation failed"
    assert isinstance(body["error"]["details"], list)


@pytest.mark.anyio
async def test_analyze_problem_url_normalization():
    with patch(
        "app.api.v1.routes.problems.analyze_problem",
        AsyncMock(
            return_value={
                "url": "https://leetcode.com/problems/two-sum",
                "use_case": "caching",
                "system_examples": ["Redis — key lookup"],
                "explanation": "hash maps are fast",
            }
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/problems",
                json={"url": "https://leetcode.com/problems/two-sum"},
            )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["url"] == "https://leetcode.com/problems/two-sum"
    assert body["error"] is None
