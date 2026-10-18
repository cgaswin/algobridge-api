import asyncio
from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import AppError, ErrorCode
from app.main import app
from app.platforms.leetcode import Problem
from app.services import problem_service as service


@pytest.mark.parametrize(
    "code,status",
    [
        (ErrorCode.GENERATION_PAUSED, 503),
        (ErrorCode.GENERATION_LIMIT_REACHED, 429),
        (ErrorCode.GENERATION_UNAVAILABLE, 503),
    ],
)
def test_denied_budget_never_calls_provider_and_preserves_envelope(code, status):
    error = AppError(code, "New generation unavailable. Try later.", status_code=status)

    async def run():
        with (
            patch.object(
                service, "get_cached_insights_by_key", AsyncMock(return_value=None)
            ),
            patch.object(
                service,
                "fetch_problem",
                AsyncMock(
                    return_value=Problem(
                        title="Test", difficulty="Easy", description="Test", tags=[]
                    )
                ),
            ),
            patch.object(service, "reserve_generation", AsyncMock(side_effect=error)),
            patch.object(service, "generate_insights", AsyncMock()) as generate,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/v1/problems",
                    json={"url": "https://leetcode.com/problems/test/"},
                )
            assert response.status_code == status
            assert response.json() == {
                "success": False,
                "data": None,
                "error": {"code": code.value, "message": error.message, "details": {}},
            }
            generate.assert_not_called()

    asyncio.run(run())


def test_cache_read_failure_never_calls_provider():
    async def run():
        with (
            patch.object(
                service,
                "get_cached_insights_by_key",
                AsyncMock(side_effect=SQLAlchemyError("offline")),
            ),
            patch.object(service, "reserve_generation", AsyncMock()) as reserve,
            patch.object(service, "generate_insights", AsyncMock()) as generate,
        ):
            with pytest.raises(AppError) as exc:
                await service.analyze_problem("https://leetcode.com/problems/test/")
            assert exc.value.code == ErrorCode.GENERATION_UNAVAILABLE
            reserve.assert_not_called()
            generate.assert_not_called()

    asyncio.run(run())
