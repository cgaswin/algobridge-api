from fastapi import APIRouter
from pydantic import BaseModel, HttpUrl

from app.core.response import success_response

router = APIRouter()


class ProblemRequest(BaseModel):
    url: HttpUrl


@router.post("/problems")
async def analyze_problem(request: ProblemRequest):
    return success_response({"url": str(request.url)})
