from unittest.mock import AsyncMock, patch

import pytest

from app.core.errors import AppError, ErrorCode
from app.platforms.leetcode import Problem
from app.services.problem_service import SOURCE_VERSION, analyze_problem

fake_problem = Problem(
    title="Two Sum",
    difficulty="Easy",
    description="Given an array of integers",
    tags=["Array", "Hash Table"],
)

fake_insights = {
    "use_case": "caching",
    "system_examples": ["Redis — key lookup"],
    "explanation": "hash maps are fast",
}

expected_payload = {
    "problem": {
        "slug": "two-sum",
        "title": "Two Sum",
        "difficulty": "easy",
        "tags": ["Array", "Hash Table"],
    },
    **fake_insights,
}


@pytest.fixture(autouse=True)
def mock_budget():
    with patch(
        "app.services.problem_service.reserve_generation", AsyncMock()
    ) as reserve:
        yield reserve


@pytest.mark.anyio
async def test_analyze_problem_success(mock_budget):
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

    assert result == expected_payload
    mock_budget.assert_awaited_once()


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
                side_effect=AppError(
                    code=ErrorCode.INTERNAL_ERROR, message="fetch failed"
                )
            ),
        ):
            with pytest.raises(AppError):
                await analyze_problem("https://leetcode.com/problems/two-sum/")


@pytest.mark.anyio
@pytest.mark.parametrize("limit", [0, 100])
async def test_analyze_problem_cache_hit_skips_external_calls(
    mock_budget, monkeypatch, limit
):
    from app.services.problem_service import settings

    monkeypatch.setattr(settings, "ai_daily_generation_limit", limit)
    mock_budget.side_effect = AppError(
        ErrorCode.GENERATION_PAUSED
        if limit == 0
        else ErrorCode.GENERATION_LIMIT_REACHED,
        "No new generation allowed",
        status_code=503 if limit == 0 else 429,
    )
    with patch(
        "app.services.problem_service.get_cached_insights_by_key",
        AsyncMock(return_value=expected_payload),
    ) as mock_get_cached:
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

    assert result == expected_payload
    assert mock_get_cached.call_args.kwargs["source_version"] == SOURCE_VERSION
    mock_budget.assert_not_called()
    mock_fetch_problem.assert_not_called()
    mock_generate_insights.assert_not_called()
    mock_upsert_problem_insights.assert_not_called()
