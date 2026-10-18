from enum import Enum
from typing import Any

from fastapi import HTTPException


class ErrorCode(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"
    UNSUPPORTED_PLATFORM = "UNSUPPORTED_PLATFORM"
    LLM_FAILURE = "LLM_FAILURE"
    GENERATION_PAUSED = "GENERATION_PAUSED"
    GENERATION_LIMIT_REACHED = "GENERATION_LIMIT_REACHED"
    GENERATION_UNAVAILABLE = "GENERATION_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(HTTPException):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
        status_code: int = 400,
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(status_code=status_code, detail=message)
