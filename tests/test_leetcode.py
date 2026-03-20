from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.errors import AppError
from app.platforms.leetcode import Problem, extract_slug, fetch_problem, strip_html


def test_extract_slug_valid():
    slug = extract_slug("https://leetcode.com/problems/two-sum/")
    assert slug == "two-sum"


def test_extract_slug_invalid():
    with pytest.raises(AppError):
        extract_slug("https://google.com")


def test_strip_html():
    result = strip_html("<p>Hello <code>world</code></p>")
    assert result == "Hello world"


@pytest.mark.anyio
async def test_fetch_problem_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "questionTitle": "Two Sum",
        "difficulty": "Easy",
        "question": "<p>Given an array</p>",
        "topicTags": [{"name": "Array"}, {"name": "Hash Table"}],
    }

    with patch("app.platforms.leetcode.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )
        problem = await fetch_problem("https://leetcode.com/problems/two-sum/")
    assert isinstance(problem, Problem)
    assert problem.title == "Two Sum"
    assert problem.difficulty == "Easy"
    assert problem.description == "Given an array"
    assert problem.tags == ["Array", "Hash Table"]


@pytest.mark.anyio
async def test_fetch_problem_api_failure():
    mock_response = AsyncMock()
    mock_response.status_code = 500

    with patch("app.platforms.leetcode.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )
        with pytest.raises(AppError):
            await fetch_problem("https://leetcode.com/problems/two-sum/")


@pytest.mark.anyio
async def test_fetch_problem_network_failure():
    with patch("app.platforms.leetcode.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            side_effect=httpx.RequestError("network down")
        )
        with pytest.raises(AppError) as exc:
            await fetch_problem("https://leetcode.com/problems/two-sum/")

    assert exc.value.status_code == 502
