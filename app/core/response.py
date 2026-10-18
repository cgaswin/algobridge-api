from fastapi.responses import JSONResponse

from app.core.errors import AppError


def error_response(exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "success": False,
            "data": None,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        },
    )


def success_response(data: dict) -> JSONResponse:
    return JSONResponse(content={"success": True, "data": data, "error": None})
