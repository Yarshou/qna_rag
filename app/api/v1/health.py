from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.schemas.common import ErrorResponse, StatusResponse

router = APIRouter(tags=["health"])

ERROR_RESPONSES = {
    503: {"model": ErrorResponse, "description": "Service is not ready."},
}


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


@router.get("/healthz", response_model=StatusResponse)
async def healthz() -> StatusResponse:
    return StatusResponse(status="ok")
