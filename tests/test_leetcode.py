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


def test_strip_html_decodes_entities():
    assert strip_html("<p>1 &lt;= n&nbsp;&amp; k</p>") == "1 <= n\xa0& k"


def _graphql_response(question, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = {"data": {"question": question}}
    return response


def _patch_post(**kwargs):
    patcher = patch("app.platforms.leetcode.httpx.AsyncClient")
    mock_client = patcher.start()
    post = AsyncMock(**kwargs)
    mock_client.return_value.__aenter__.return_value.post = post
    return patcher, post


TWO_SUM = {
    "title": "Two Sum",
    "difficulty": "Easy",
    "isPaidOnly": False,
    "content": "<p>Given an array</p>",
    "topicTags": [{"name": "Array"}, {"name": "Hash Table"}],
}


@pytest.mark.anyio
async def test_fetch_problem_success():
    patcher, post = _patch_post(return_value=_graphql_response(TWO_SUM))
    try:
        problem = await fetch_problem("https://leetcode.com/problems/two-sum/")
    finally:
        patcher.stop()

    assert isinstance(problem, Problem)
    assert problem.title == "Two Sum"
    assert problem.difficulty == "Easy"
    assert problem.description == "Given an array"
    assert problem.tags == ["Array", "Hash Table"]
    assert post.call_args.kwargs["json"]["variables"] == {"titleSlug": "two-sum"}


@pytest.mark.anyio
async def test_fetch_problem_not_found():
    patcher, _ = _patch_post(return_value=_graphql_response(None))
    try:
        with pytest.raises(AppError) as exc:
            await fetch_problem("https://leetcode.com/problems/no-such-problem/")
    finally:
        patcher.stop()

    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_fetch_problem_paid_only():
    question = {**TWO_SUM, "isPaidOnly": True, "content": None}
    patcher, _ = _patch_post(return_value=_graphql_response(question))
    try:
        with pytest.raises(AppError) as exc:
            await fetch_problem("https://leetcode.com/problems/two-sum/")
    finally:
        patcher.stop()

    assert exc.value.status_code == 422
    assert "Premium" in exc.value.message


@pytest.mark.anyio
async def test_fetch_problem_non_json_response():
    response = MagicMock()
    response.status_code = 200
    response.json.side_effect = ValueError("not json")
    patcher, _ = _patch_post(return_value=response)
    try:
        with pytest.raises(AppError) as exc:
            await fetch_problem("https://leetcode.com/problems/two-sum/")
    finally:
        patcher.stop()

    assert exc.value.status_code == 502


@pytest.mark.anyio
async def test_fetch_problem_api_failure():
    patcher, _ = _patch_post(return_value=_graphql_response(None, status_code=403))
    try:
        with pytest.raises(AppError) as exc:
            await fetch_problem("https://leetcode.com/problems/two-sum/")
    finally:
        patcher.stop()

    assert exc.value.status_code == 502


@pytest.mark.anyio
async def test_fetch_problem_network_failure():
    patcher, _ = _patch_post(side_effect=httpx.RequestError("network down"))
    try:
        with pytest.raises(AppError) as exc:
            await fetch_problem("https://leetcode.com/problems/two-sum/")
    finally:
        patcher.stop()

    assert exc.value.status_code == 502
