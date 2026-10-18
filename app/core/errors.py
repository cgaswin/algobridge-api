from enum import Enum
from typing import Any

from fastapi import HTTPException


class ErrorCode(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"
    UNSUPPORTED_PLATFORM = "UNSUPPORTED_PLATFORM"
    LLM_FAILURE = "LLM_FAILURE"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    RATE_LIMITED = "RATE_LIMITED"


class AppError(HTTPException):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
        status_code: int = 400,
        headers: dict[str, str] | None = None,
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(status_code=status_code, detail=message, headers=headers)
