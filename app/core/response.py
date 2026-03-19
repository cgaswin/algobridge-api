from fastapi.responses import JSONResponse


def success_response(data: dict) -> JSONResponse:
    return JSONResponse(content={"success": True, "data": data, "error": None})
