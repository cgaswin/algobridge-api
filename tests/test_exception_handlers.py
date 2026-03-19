from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import AppError, ErrorCode
from app.core.exception_handlers import register_exception_handlers


def test_app_error_status_code_and_envelope():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom():
        raise AppError(
            code=ErrorCode.INVALID_INPUT,
            message="invalid payload",
            details={"field": "problem_url"},
            status_code=422,
        )

    client = TestClient(app)
    response = client.get("/boom")

    assert response.status_code == 422

    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == ErrorCode.INVALID_INPUT
    assert body["error"]["message"] == "invalid payload"
    assert body["error"]["details"] == {"field": "problem_url"}
