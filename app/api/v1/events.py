import asyncio
import logging
import time
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.common_types import ChatEvent
from app.schemas.common import ErrorResponse
from app.schemas.events import EventListResponse, EventResponse
from app.services import ChatService, NotificationService

router = APIRouter(tags=["events"])
logger = logging.getLogger(__name__)
SSE_POLL_INTERVAL_SECONDS = 0.5
SSE_HEARTBEAT_INTERVAL_SECONDS = 15.0
SSE_BATCH_SIZE = 100

ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Chat not found."},
    500: {"model": ErrorResponse, "description": "Internal server error."},
}


def get_chat_service() -> ChatService:
    return ChatService()


def get_notification_service() -> NotificationService:
    return NotificationService()


def _event_to_response(event: ChatEvent) -> EventResponse:
    return EventResponse(
        id=event.id,
        chat_id=event.chat_id,
        event_type=event.event_type.value,
        payload=event.payload,
        created_at=event.created_at,
    )


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


def _format_sse_message(event: ChatEvent) -> str:
    data = _event_to_response(event).model_dump_json(exclude_none=True)
    return f"id: {event.id}\nevent: {event.event_type.value}\ndata: {data}\n\n"


async def _resolve_stream_cursor(
    *,
    request: Request,
    chat_id: str,
    notification_service: NotificationService,
) -> tuple[str | None, str | None]:
    last_event_id = request.headers.get("last-event-id")
    if last_event_id:
        cursor_event = await notification_service.get_event(chat_id=chat_id, event_id=last_event_id)
        if cursor_event is None:
            logger.warning("sse_cursor_event_not_found", extra={"chat_id": chat_id, "last_event_id": last_event_id})
            return None, None
        return cursor_event.created_at.isoformat(), cursor_event.id

    latest_event = await notification_service.get_latest_event(chat_id)
    if latest_event is None:
        return None, None
    return latest_event.created_at.isoformat(), latest_event.id


async def _event_stream(
    *,
    request: Request,
    chat_id: str,
    notification_service: NotificationService,
    cursor_created_at: str | None,
    cursor_id: str | None,
):
    last_delivery_at = time.monotonic()
    logger.info("sse_subscribe", extra={"chat_id": chat_id, "cursor_id": cursor_id})

    try:
        while True:
            if await request.is_disconnected():
                break

            events = await notification_service.list_events_after(
                chat_id=chat_id,
                after_created_at=cursor_created_at,
                after_id=cursor_id,
                limit=SSE_BATCH_SIZE,
            )

            if events:
                for event in events:
                    if await request.is_disconnected():
                        return

                    logger.info(
                        "sse_event_delivered",
                        extra={"chat_id": chat_id, "event_id": event.id, "event_type": event.event_type.value},
                    )
                    yield _format_sse_message(event)
                    cursor_created_at = event.created_at.isoformat()
                    cursor_id = event.id
                    last_delivery_at = time.monotonic()
                continue

            if time.monotonic() - last_delivery_at >= SSE_HEARTBEAT_INTERVAL_SECONDS:
                yield ": keepalive\n\n"
                last_delivery_at = time.monotonic()

            await asyncio.sleep(SSE_POLL_INTERVAL_SECONDS)
    finally:
        logger.info("sse_disconnect", extra={"chat_id": chat_id, "cursor_id": cursor_id})


@router.get(
    "/chats/{chat_id}/events",
    response_model=EventListResponse,
    response_model_exclude_none=True,
    responses=ERROR_RESPONSES,
)
async def list_events(
    chat_id: str,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    notification_service: Annotated[NotificationService, Depends(get_notification_service)],
    since: Annotated[datetime | None, Query(description="Return events created at or after this timestamp.")] = None,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
) -> EventListResponse | JSONResponse:
    try:
        chat = await chat_service.get_chat(chat_id)
        if chat is None:
            return _error_response(status.HTTP_404_NOT_FOUND, "chat_not_found", f"Chat '{chat_id}' was not found.")

        events = await notification_service.list_events(
            chat_id,
            since=since.isoformat() if since is not None else None,
            limit=limit,
        )
    except Exception:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "Failed to list events.")

    return EventListResponse(items=[_event_to_response(event) for event in events])


@router.get(
    "/chats/{chat_id}/events/stream",
    response_model=None,
    responses=ERROR_RESPONSES,
)
async def stream_events(
    chat_id: str,
    request: Request,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    notification_service: Annotated[NotificationService, Depends(get_notification_service)],
) -> StreamingResponse | JSONResponse:
    try:
        chat = await chat_service.get_chat(chat_id)
        if chat is None:
            return _error_response(status.HTTP_404_NOT_FOUND, "chat_not_found", f"Chat '{chat_id}' was not found.")
        cursor_created_at, cursor_id = await _resolve_stream_cursor(
            request=request,
            chat_id=chat_id,
            notification_service=notification_service,
        )
    except Exception as e:
        logger.exception("stream_events", extra={"chat_id": chat_id, "cursor_id": cursor_id, "exception": e})
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "Failed to open event stream.")

    return StreamingResponse(
        _event_stream(
            request=request,
            chat_id=chat_id,
            notification_service=notification_service,
            cursor_created_at=cursor_created_at,
            cursor_id=cursor_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
