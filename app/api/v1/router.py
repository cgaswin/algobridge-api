from fastapi import APIRouter

from app.api.v1.routes.problems import router as problems_router

router = APIRouter(prefix="/api/v1")
router.include_router(problems_router)
