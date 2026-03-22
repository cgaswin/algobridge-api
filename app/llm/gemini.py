import json

from google import genai

from app.config.settings import settings
from app.core.errors import AppError, ErrorCode
from app.platforms.leetcode import Problem


client = genai.Client(api_key=settings.gemini_api_key)


def build_prompt(problem: Problem) -> str:
    return f"""
You are a senior software engineer. Given the following coding problem, explain how it appears in real-world engineering systems.

Problem: {problem.title}
Difficulty: {problem.difficulty}
Tags: {", ".join(problem.tags)}
Description: {problem.description}

Respond ONLY with a valid JSON object in this exact format, no explanation or markdown:
{{
    "use_case": "A concise real-world use case where this problem appears",
    "system_examples": "Specific systems or products that use this pattern",
    "explanation": "Why this problem matters in production engineering"
}}
"""


async def generate_insights(problem: Problem) -> dict:
    try:
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=build_prompt(problem),
        )
        if not response.text:
            raise AppError(
                code=ErrorCode.LLM_FAILURE,
                message="Gemini returned an empty response",
                status_code=502,
            )
        text = response.text.strip()
        return json.loads(text)
    except AppError:
        raise
    except json.JSONDecodeError:
        raise AppError(
            code=ErrorCode.LLM_FAILURE,
            message="Gemini returned an invalid response",
            status_code=502,
        )
    except Exception:
        raise AppError(
            code=ErrorCode.LLM_FAILURE,
            message="Failed to generate insights",
            status_code=502,
        )
