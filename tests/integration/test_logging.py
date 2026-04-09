import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config.setup import setup


def test_request_lifecycle_logging(caplog) -> None:
    app = FastAPI()
    setup(app)

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    with TestClient(app) as client:
        with caplog.at_level(logging.INFO):
            response = client.get("/ok", headers={"X-Request-ID": "req-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-123"

    events = [record.msg for record in caplog.records]
    assert "request_started" in events
    assert "request_completed" in events

    started = next(record for record in caplog.records if record.msg == "request_started")
    completed = next(record for record in caplog.records if record.msg == "request_completed")
    assert getattr(started, "request_id") == "req-123"
    assert getattr(completed, "request_id") == "req-123"
    assert getattr(completed, "status_code") == 200


def test_unhandled_exception_logging(caplog) -> None:
    app = FastAPI()
    setup(app)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("boom")

    with TestClient(app, raise_server_exceptions=False) as client:
        with caplog.at_level(logging.INFO):
            response = client.get("/boom", headers={"X-Request-ID": "req-500"})

    assert response.status_code == 500
    assert response.json() == {"error": {"code": "internal_error", "message": "Internal server error."}}
    assert response.headers["X-Request-ID"] == "req-500"

    events = [record.msg for record in caplog.records]
    assert events.count("unhandled_exception") == 1
    assert "request_started" in events
    assert "request_completed" in events

    unhandled = next(record for record in caplog.records if record.msg == "unhandled_exception")
    completed = next(record for record in caplog.records if record.msg == "request_completed")
    assert getattr(unhandled, "request_id") == "req-500"
    assert getattr(unhandled, "error_type") == "RuntimeError"
    assert getattr(completed, "status_code") == 500
