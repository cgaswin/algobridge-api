from unittest.mock import AsyncMock, patch

import pytest

from app.core.errors import AppError, ErrorCode
from app.platforms.leetcode import Problem
from app.services.problem_service import analyze_problem

fake_problem = Problem(
    title="Two Sum",
    difficulty="Easy",
    description="Given an array of integers",
    tags=["Array", "Hash Table"],
)

fake_insights = {
    "use_case": "caching",
    "system_examples": "Redis",
    "explanation": "hash maps are fast",
}


@pytest.mark.anyio
async def test_analyze_problem_success():
    with patch(
        "app.services.problem_service.get_cached_insights_by_key",
        AsyncMock(return_value=None),
    ):
        with patch(
            "app.services.problem_service.upsert_problem_insights",
            AsyncMock(),
        ):
            with patch(
                "app.services.problem_service.fetch_problem",
                AsyncMock(return_value=fake_problem),
            ):
                with patch(
                    "app.services.problem_service.generate_insights",
                    AsyncMock(return_value=fake_insights),
                ):
                    result = await analyze_problem(
                        "https://leetcode.com/problems/two-sum/"
                    )

    assert result == fake_insights


@pytest.mark.anyio
async def test_analyze_problem_unsupported_platform():
    with pytest.raises(AppError) as exc_info:
        await analyze_problem("https://hackerrank.com/problems/two-sum/")

    assert exc_info.value.code == ErrorCode.UNSUPPORTED_PLATFORM


@pytest.mark.anyio
async def test_analyze_problem_fetch_failure():
    with patch(
        "app.services.problem_service.get_cached_insights_by_key",
        AsyncMock(return_value=None),
    ):
        with patch(
            "app.services.problem_service.fetch_problem",
            AsyncMock(
                side_effect=AppError(code=ErrorCode.INTERNAL_ERROR, message="fetch failed")
            ),
        ):
            with pytest.raises(AppError):
                await analyze_problem("https://leetcode.com/problems/two-sum/")


@pytest.mark.anyio
async def test_analyze_problem_cache_hit_skips_external_calls():
    with patch(
        "app.services.problem_service.get_cached_insights_by_key",
        AsyncMock(return_value=fake_insights),
    ):
        with patch(
            "app.services.problem_service.fetch_problem",
            AsyncMock(),
        ) as mock_fetch_problem:
            with patch(
                "app.services.problem_service.generate_insights",
                AsyncMock(),
            ) as mock_generate_insights:
                with patch(
                    "app.services.problem_service.upsert_problem_insights",
                    AsyncMock(),
                ) as mock_upsert_problem_insights:
                    result = await analyze_problem(
                        "https://leetcode.com/problems/two-sum/"
                    )

    assert result == fake_insights
    mock_fetch_problem.assert_not_called()
    mock_generate_insights.assert_not_called()
    mock_upsert_problem_insights.assert_not_called()
