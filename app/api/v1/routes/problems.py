from fastapi import APIRouter
from pydantic import BaseModel, HttpUrl

from app.core.response import success_response
from app.services.problem_service import analyze_problem

router = APIRouter()


class ProblemRequest(BaseModel):
    url: HttpUrl


@router.post("/problems")
async def analyze(request: ProblemRequest):
    insights = await analyze_problem(str(request.url))
    return success_response(insights)
