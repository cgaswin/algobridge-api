import json

from app.core.errors import AppError, ErrorCode
from app.core.response import success_response


def test_success_response_shape():
    result = success_response({"key": "value"})
    data = json.loads(bytes(result.body))
    assert data["success"] is True
    assert data["data"] == {"key": "value"}
    assert data["error"] is None


def test_success_response_empty_data():
    result = success_response({})
    data = json.loads(bytes(result.body))
    assert data["success"] is True
    assert data["data"] == {}


def test_error_code_values():
    assert ErrorCode.INVALID_INPUT == "INVALID_INPUT"
    assert ErrorCode.UNSUPPORTED_PLATFORM == "UNSUPPORTED_PLATFORM"
    assert ErrorCode.LLM_FAILURE == "LLM_FAILURE"
    assert ErrorCode.INTERNAL_ERROR == "INTERNAL_ERROR"


def test_app_error_fields():
    error = AppError(code=ErrorCode.INVALID_INPUT, message="bad input")
    assert error.code == ErrorCode.INVALID_INPUT
    assert error.message == "bad input"
    assert error.details == {}
