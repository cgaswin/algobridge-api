from fastapi import FastAPI

from app.config.logging import setup_logging
from app.core.exception_handlers import register_exception_handlers

setup_logging()

app = FastAPI(
    title="AlgoBridge API",
    description="Transforms coding problems into real-world engineering insights",
    version="1.0.0",
)

register_exception_handlers(app)


@app.get("/health")
async def health():
    return {"status": "ok"}
