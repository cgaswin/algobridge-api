from core.errors import AppError, ErrorCode
from llm.gemini import generate_insights
from platforms.leetcode import fetch_problem


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

    problem = await fetch_problem(url)
    insights = await generate_insights(problem)
    return insights
