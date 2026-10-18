from typing import Any, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.config.logging import setup_logging
from app.config.settings import settings
from app.core.exception_handlers import register_exception_handlers
from app.core.rate_limit import IPRateLimiter, IPRateLimitMiddleware

setup_logging()

app = FastAPI(
    title="AlgoBridge API",
    description="Transforms coding problems into real-world engineering insights",
    version="1.0.0",
)

register_exception_handlers(app)

app.add_middleware(
    IPRateLimitMiddleware,
    limiter=IPRateLimiter(
        requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
        max_ips=settings.rate_limit_max_ips,
    ),
)

cors_options: dict[str, Any] = {
    "allow_origin_regex": r"^(chrome-extension://[a-z]{32}|moz-extension://[0-9a-fA-F-]+)$",
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
    "expose_headers": ["Retry-After"],
}

app.add_middleware(
    cast(Any, CORSMiddleware),
    **cors_options,
)

app.include_router(v1_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
