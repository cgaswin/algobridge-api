from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.config.settings import settings
from app.core.errors import AppError, ErrorCode
from app.llm.prompts import GENERATION_SYSTEM, build_generation_prompt
from app.platforms.leetcode import Problem


client = genai.Client(api_key=settings.gemini_api_key)


class Insight(BaseModel):
    use_case: str
    system_examples: list[str]
    explanation: str


async def generate_insights(problem: Problem) -> dict:
    try:
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=build_generation_prompt(problem),
            config=types.GenerateContentConfig(
                system_instruction=GENERATION_SYSTEM,
                response_mime_type="application/json",
                response_schema=Insight,
            ),
        )
        if not response.text:
            raise AppError(
                code=ErrorCode.LLM_FAILURE,
                message="Gemini returned an empty response",
                status_code=502,
            )
        return Insight.model_validate_json(response.text).model_dump()
    except AppError:
        raise
    except ValidationError:
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
