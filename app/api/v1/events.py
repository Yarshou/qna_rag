import asyncio
import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.domain import ChatEvent
from app.events import EventBroker, get_event_broker
from app.schemas.common import ErrorResponse
from app.schemas.events import EventListResponse, EventResponse
from app.services import ChatService, NotificationService

router = APIRouter(tags=["events"])
logger = logging.getLogger(__name__)
SSE_HEARTBEAT_INTERVAL_SECONDS = 15.0

ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Chat not found."},
    500: {"model": ErrorResponse, "description": "Internal server error."},
}


def get_chat_service() -> ChatService:
    return ChatService()


def get_event_broker_dependency(request: Request) -> EventBroker:
    return getattr(request.app.state, "event_broker", None) or get_event_broker()


def get_notification_service(
    broker: Annotated[EventBroker, Depends(get_event_broker_dependency)],
) -> NotificationService:
    return NotificationService(broker=broker)


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


async def _event_stream(request: Request, chat_id: str, broker: EventBroker):
    subscription = await broker.subscribe(chat_id)
    logger.info("sse_subscribe", extra={"chat_id": chat_id})

    try:
        while True:
            if await request.is_disconnected():
                break

            try:
                event = await asyncio.wait_for(subscription.queue.get(), timeout=SSE_HEARTBEAT_INTERVAL_SECONDS)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue

            logger.info(
                "sse_event_delivered",
                extra={"chat_id": chat_id, "event_id": event.id, "event_type": event.event_type.value},
            )
            yield _format_sse_message(event)
    finally:
        await broker.unsubscribe(subscription)
        logger.info("sse_disconnect", extra={"chat_id": chat_id})


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
    broker: Annotated[EventBroker, Depends(get_event_broker_dependency)],
) -> StreamingResponse | JSONResponse:
    try:
        chat = await chat_service.get_chat(chat_id)
        if chat is None:
            return _error_response(status.HTTP_404_NOT_FOUND, "chat_not_found", f"Chat '{chat_id}' was not found.")
    except Exception:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "Failed to open event stream.")

    return StreamingResponse(
        _event_stream(request=request, chat_id=chat_id, broker=broker),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
