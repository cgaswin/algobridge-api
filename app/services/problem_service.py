from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ErrorCode
from app.db.repository import get_cached_insights_by_key, upsert_problem_insights
from app.db.session import AsyncSessionLocal
from app.config.settings import settings
from app.llm.gemini import generate_insights
from app.llm.prompts import PROMPT_VERSION
from app.platforms.leetcode import extract_slug, fetch_problem


# Cached rows from another model, prompt or payload shape are regenerated.
SOURCE_VERSION = f"{settings.gemini_model}:{PROMPT_VERSION}"


async def analyze_problem(url: str) -> dict:
    if not (
        url.startswith("https://leetcode.com/problems/")
        or url.startswith("http://leetcode.com/problems/")
        or url.startswith("https://www.leetcode.com/problems/")
        or url.startswith("http://www.leetcode.com/problems/")
    ):
        raise AppError(
            code=ErrorCode.UNSUPPORTED_PLATFORM,
            message="Only LeetCode problems are supported",
        )

    canonical_key = extract_slug(url)

    async with AsyncSessionLocal() as session:
        session: AsyncSession
        cached_insights = await get_cached_insights_by_key(
            session,
            canonical_key=canonical_key,
            source_version=SOURCE_VERSION,
        )
        if cached_insights is not None:
            return cached_insights

        problem = await fetch_problem(url)
        insights = {
            "problem": {
                "slug": canonical_key,
                "title": problem.title,
                "difficulty": problem.difficulty.lower(),
                "tags": problem.tags,
            },
            **await generate_insights(problem),
        }

        await upsert_problem_insights(
            session,
            canonical_key=canonical_key,
            raw_url=url,
            insights_json=insights,
            source_version=SOURCE_VERSION,
        )
        return insights
