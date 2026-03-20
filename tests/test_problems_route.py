import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.anyio
async def test_analyze_problem_valid_url():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/problems",
            json={"url": "https://leetcode.com/problems/two-sum/"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["url"] == "https://leetcode.com/problems/two-sum/"
    assert body["error"] is None


@pytest.mark.anyio
async def test_analyze_problem_missing_url():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/v1/problems", json={})
    assert response.status_code == 422


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


@pytest.mark.anyio
async def test_analyze_problem_url_normalization():
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
