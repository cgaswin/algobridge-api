import asyncio
from unittest.mock import AsyncMock, patch

from google import genai
from google.genai import types
import httpx
import pytest

from app.core.errors import AppError
from app.llm import gemini
from app.platforms.leetcode import Problem

PROBLEM = Problem(title="Test", difficulty="Easy", description="Test", tags=[])


def test_finite_generation_timeout(monkeypatch):
    async def hang(**kwargs):
        await asyncio.sleep(10)

    monkeypatch.setattr(gemini.settings, "ai_generation_timeout_seconds", 0.01)
    with patch.object(
        gemini.client.aio.models, "generate_content", AsyncMock(side_effect=hang)
    ) as generate:
        with pytest.raises(AppError) as exc:
            asyncio.run(gemini.generate_insights(PROBLEM))
    assert exc.value.status_code == 504
    generate.assert_awaited_once()


def test_sdk_does_not_retry_retryable_provider_failure():
    calls = []

    async def respond(request):
        calls.append(request)
        return httpx.Response(
            503,
            json={
                "error": {
                    "code": 503,
                    "message": "unavailable",
                    "status": "UNAVAILABLE",
                }
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            # Use the production retry/timeout configuration with a fake transport.
            options = gemini.client._api_client._http_options.model_copy(
                update={"httpx_async_client": http}
            )
            assert options.retry_options == types.HttpRetryOptions(attempts=1)
            assert options.timeout == 30_000
            test_client = genai.Client(api_key="test", http_options=options)
            try:
                with patch.object(gemini, "client", test_client):
                    with pytest.raises(AppError) as exc:
                        await gemini.generate_insights(PROBLEM)
                assert exc.value.status_code == 502
            finally:
                await test_client.aio.aclose()

    asyncio.run(run())
    assert len(calls) == 1
