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
    return re.sub(r"<[^>]+>", "", text).strip()


async def fetch_problem(url: str) -> Problem:
    slug = extract_slug(url)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.leetcode_endpoint}/select",
                params={"titleSlug": slug},
            )
    except httpx.RequestError as exc:
        raise AppError(
            code=ErrorCode.INTERNAL_ERROR,
            message="Failed to reach LeetCode service",
            details={"reason": str(exc)},
            status_code=502,
        ) from exc

    if response.status_code != 200:
        raise AppError(
            code=ErrorCode.INTERNAL_ERROR,
            message="Failed to fetch problem from LeetCode",
            details={"status_code": response.status_code},
            status_code=502,
        )

    data = response.json()

    required_fields = ("questionTitle", "difficulty", "question", "topicTags")
    missing = [field for field in required_fields if field not in data]
    if missing:
        raise AppError(
            code=ErrorCode.INTERNAL_ERROR,
            message="Invalid response from LeetCode service",
            details={"missing_fields": missing},
            status_code=502,
        )

    return Problem(
        title=data["questionTitle"],
        difficulty=data["difficulty"],
        description=strip_html(data["question"]),
        tags=[tag["name"] for tag in data["topicTags"] if "name" in tag],
    )
