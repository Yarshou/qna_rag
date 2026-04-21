import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.db.connection import open_connection
from app.schemas.common import ErrorResponse, StatusResponse

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)

ERROR_RESPONSES = {
    503: {"model": ErrorResponse, "description": "Service is not ready."},
}


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


@router.get("/healthz", response_model=StatusResponse)
async def healthz() -> StatusResponse:
    try:
        connection = await open_connection()
        await connection.execute("SELECT 1")
        await connection.close()
    except Exception as exc:
        logger.warning("readiness_check_failed", extra={"error_type": exc.__class__.__name__})
        return _error_response(503, "db_unavailable", "Database is not accessible.")

    return StatusResponse(status="ok")


@router.get("/readyz", response_model=StatusResponse, responses=ERROR_RESPONSES)
async def readyz() -> StatusResponse | JSONResponse:
    try:
        connection = await open_connection()
        await connection.execute("SELECT 1")
        await connection.close()
    except Exception as exc:
        logger.warning("readiness_check_failed", extra={"error_type": exc.__class__.__name__})
        return _error_response(503, "db_unavailable", "Database is not accessible.")

    return StatusResponse(status="ok")
