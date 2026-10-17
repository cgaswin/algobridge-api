import html
import re
from dataclasses import dataclass

import httpx

from app.config.settings import settings
from app.core.errors import AppError, ErrorCode


@dataclass
class Problem:
    title: str
    difficulty: str
    description: str
    tags: list[str]


def extract_slug(url: str) -> str:
    match = re.match(
        r"^https?://(?:www\.)?leetcode\.com/problems/([a-z0-9-]+)(?:/|$)",
        url.strip(),
    )
    if not match:
        raise AppError(
            code=ErrorCode.INVALID_INPUT,
            message="Could not extract problem slug from URL",
            status_code=422,
        )
    return match.group(1)


def strip_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


QUESTION_QUERY = """
query question($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    title
    difficulty
    isPaidOnly
    content
    topicTags { name }
  }
}
"""

# LeetCode's public GraphQL endpoint (the one its own site uses) rejects
# requests that don't look like they come from a browser on leetcode.com.
REQUEST_HEADERS = {
    "Content-Type": "application/json",
    "Referer": "https://leetcode.com/",
    "Origin": "https://leetcode.com",
    "User-Agent": "Mozilla/5.0 (compatible; AlgoBridge/1.0; +https://github.com/cgaswin/algobridge)",
}


def _leetcode_unavailable(message: str, **details: object) -> AppError:
    return AppError(
        code=ErrorCode.INTERNAL_ERROR,
        message=message,
        details=details,
        status_code=502,
    )


async def fetch_problem(url: str) -> Problem:
    slug = extract_slug(url)

    try:
        async with httpx.AsyncClient(timeout=10.0, headers=REQUEST_HEADERS) as client:
            response = await client.post(
                settings.leetcode_graphql_url,
                json={
                    "operationName": "question",
                    "query": QUESTION_QUERY,
                    "variables": {"titleSlug": slug},
                },
            )
    except httpx.RequestError as exc:
        raise _leetcode_unavailable(
            "Failed to reach LeetCode", reason=str(exc)
        ) from exc

    if response.status_code != 200:
        raise _leetcode_unavailable(
            "Failed to fetch problem from LeetCode", status_code=response.status_code
        )

    try:
        payload = response.json()
    except ValueError as exc:
        # Usually a Cloudflare challenge page instead of JSON.
        raise _leetcode_unavailable("Invalid response from LeetCode") from exc

    question = (payload.get("data") or {}).get("question")
    if question is None:
        raise AppError(
            code=ErrorCode.INVALID_INPUT,
            message="Problem not found on LeetCode",
            details={"slug": slug},
            status_code=404,
        )

    if not question.get("content"):
        # LeetCode withholds the statement of premium problems from anonymous requests.
        message = (
            "Premium LeetCode problems aren't supported yet"
            if question.get("isPaidOnly")
            else "LeetCode returned no description for this problem"
        )
        raise AppError(
            code=ErrorCode.UNSUPPORTED_PLATFORM,
            message=message,
            details={"slug": slug},
            status_code=422,
        )

    return Problem(
        title=question["title"],
        difficulty=question["difficulty"],
        description=strip_html(question["content"]),
        tags=[tag["name"] for tag in question.get("topicTags") or [] if "name" in tag],
    )
