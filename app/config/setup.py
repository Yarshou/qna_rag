import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse
from starlette.responses import HTMLResponse

from app.config.logging import configure_logging

logger = logging.getLogger(__name__)


def setup_docs(app: FastAPI) -> None:
    @app.get("/docs", include_in_schema=False)
    async def docs() -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title="QNA-RAG Documentation",
            swagger_ui_parameters={"tryItOutEnabled": "false"},
        )

    @app.get("/redoc", include_in_schema=False)
    async def redoc() -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title="QNA-RAG Documentation",
            swagger_ui_parameters={"tryItOutEnabled": "false"},
        )


def _get_request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str) and request_id:
        return request_id
    return "unknown"


def setup_request_logging(app: FastAPI) -> None:
    @app.middleware("http")
    async def log_request_lifecycle(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        start_time = perf_counter()

        logger.info(
            "request_started",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "client_ip": request.client.host if request.client is not None else None,
            },
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            handler = app.exception_handlers.get(Exception)
            if handler is None:
                raise
            response = await handler(request, exc)

        duration_ms = round((perf_counter() - start_time) * 1000, 3)
        response.headers["X-Request-ID"] = request_id

        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response


def setup_exception_logging(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled_exception",
            extra={
                "request_id": _get_request_id(request),
                "method": request.method,
                "path": request.url.path,
                "error_type": exc.__class__.__name__,
            },
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": {"code": "internal_error", "message": "Internal server error."}},
            headers={"X-Request-ID": _get_request_id(request)},
        )


def setup(app: FastAPI) -> None:
    configure_logging()
    setup_docs(app=app)
    setup_request_logging(app=app)
    setup_exception_logging(app=app)
