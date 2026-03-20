from unittest.mock import MagicMock, patch

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
    mock_response.text = '{"use_case": "caching", "system_examples": "Redis", "explanation": "hash maps are fast"}'

    with patch(
        "app.llm.gemini.client.models.generate_content", return_value=mock_response
    ):
        result = await generate_insights(fake_problem)

    assert result["use_case"] == "caching"
    assert result["system_examples"] == "Redis"
    assert result["explanation"] == "hash maps are fast"


@pytest.mark.anyio
async def test_generate_insights_invalid_json():
    mock_response = MagicMock()
    mock_response.text = "not valid json"

    with patch(
        "app.llm.gemini.client.models.generate_content", return_value=mock_response
    ):
        with pytest.raises(AppError):
            await generate_insights(fake_problem)
