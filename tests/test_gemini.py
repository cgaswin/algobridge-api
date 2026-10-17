from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.errors import AppError
from app.llm.gemini import generate_insights
from app.platforms.leetcode import Problem

fake_problem = Problem(
    title="Two Sum",
    difficulty="Easy",
    description="Given an array of integers",
    tags=["Array", "Hash Table"],
)


@pytest.mark.anyio
async def test_generate_insights_success():
    mock_response = MagicMock()
    mock_response.text = '{"use_case": "caching", "system_examples": ["Redis — key lookup"], "explanation": "hash maps are fast"}'

    with patch(
        "app.llm.gemini.client.aio.models.generate_content",
        AsyncMock(return_value=mock_response),
    ):
        result = await generate_insights(fake_problem)

    assert result["use_case"] == "caching"
    assert result["system_examples"] == ["Redis — key lookup"]
    assert result["explanation"] == "hash maps are fast"


@pytest.mark.anyio
async def test_generate_insights_invalid_json():
    mock_response = MagicMock()
    mock_response.text = "not valid json"

    with patch(
        "app.llm.gemini.client.aio.models.generate_content",
        AsyncMock(return_value=mock_response),
    ):
        with pytest.raises(AppError):
            await generate_insights(fake_problem)


@pytest.mark.anyio
async def test_generate_insights_rejects_wrong_shape():
    mock_response = MagicMock()
    mock_response.text = (
        '{"use_case": "caching", "system_examples": "Redis", "explanation": "fast"}'
    )

    with patch(
        "app.llm.gemini.client.aio.models.generate_content",
        AsyncMock(return_value=mock_response),
    ):
        with pytest.raises(AppError):
            await generate_insights(fake_problem)
