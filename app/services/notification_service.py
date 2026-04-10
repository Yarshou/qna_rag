import logging
from collections.abc import Mapping

from app.domain import ChatEvent, EventType
from app.repositories.events import EventsRepository

logger = logging.getLogger(__name__)

EventPayload = Mapping[str, object] | None


class NotificationService:
    """Persists chat-processing lifecycle events and reads them for REST/SSE delivery."""

    def __init__(
        self,
        events_repository: EventsRepository | None = None,
        *,
        enabled: bool = True,
    ) -> None:
        self._events_repository = EventsRepository() if enabled and events_repository is None else events_repository

    async def emit_message_received(self, chat_id: str, payload: EventPayload = None) -> ChatEvent | None:
        return await self._emit(chat_id, EventType.MESSAGE_RECEIVED, payload)

    async def emit_message_processing(self, chat_id: str, payload: EventPayload = None) -> ChatEvent | None:
        return await self._emit(chat_id, EventType.MESSAGE_PROCESSING, payload)

    async def emit_tool_called(self, chat_id: str, payload: EventPayload = None) -> ChatEvent | None:
        return await self._emit(chat_id, EventType.TOOL_CALLED, payload)

    async def emit_message_completed(self, chat_id: str, payload: EventPayload = None) -> ChatEvent | None:
        return await self._emit(chat_id, EventType.MESSAGE_COMPLETED, payload)

    async def emit_message_failed(self, chat_id: str, payload: EventPayload = None) -> ChatEvent | None:
        return await self._emit(chat_id, EventType.MESSAGE_FAILED, payload)

    async def list_events(
        self,
        chat_id: str,
        *,
        since: str | None = None,
        limit: int | None = None,
    ) -> list[ChatEvent]:
        if self._events_repository is None:
            logger.info("chat_event_list_skipped", extra={"chat_id": chat_id, "reason": "repository_not_configured"})
            return []

        events = await self._events_repository.list_events(chat_id=chat_id, since=since, limit=limit)
        logger.info("chat_event_list_completed", extra={"chat_id": chat_id, "count": len(events)})
        return [ChatEvent.from_mapping(event) for event in events]

    async def list_events_after(
        self,
        chat_id: str,
        *,
        after_created_at: str | None = None,
        after_id: str | None = None,
        limit: int | None = None,
    ) -> list[ChatEvent]:
        if self._events_repository is None:
            logger.info("chat_event_tail_skipped", extra={"chat_id": chat_id, "reason": "repository_not_configured"})
            return []

        events = await self._events_repository.list_events_after(
            chat_id=chat_id,
            after_created_at=after_created_at,
            after_id=after_id,
            limit=limit,
        )
        if events:
            logger.info("chat_event_tail_completed", extra={"chat_id": chat_id, "count": len(events)})
        return [ChatEvent.from_mapping(event) for event in events]

    async def get_event(self, chat_id: str, event_id: str) -> ChatEvent | None:
        if self._events_repository is None:
            logger.info(
                "chat_event_lookup_skipped",
                extra={"chat_id": chat_id, "event_id": event_id, "reason": "repository_not_configured"},
            )
            return None

        event = await self._events_repository.get_event(chat_id=chat_id, event_id=event_id)
        return ChatEvent.from_mapping(event) if event is not None else None

    async def get_latest_event(self, chat_id: str) -> ChatEvent | None:
        if self._events_repository is None:
            logger.info("chat_event_latest_skipped", extra={"chat_id": chat_id, "reason": "repository_not_configured"})
            return None

        event = await self._events_repository.get_latest_event(chat_id=chat_id)
        return ChatEvent.from_mapping(event) if event is not None else None

    async def _emit(self, chat_id: str, event_type: EventType, payload: EventPayload) -> ChatEvent | None:
        if self._events_repository is None:
            logger.info(
                "chat_event_skipped",
                extra={"chat_id": chat_id, "event_type": event_type.value, "reason": "repository_not_configured"},
            )
            return None

        logger.info("chat_event_emitting", extra={"chat_id": chat_id, "event_type": event_type.value})
        event = await self._events_repository.create_event(
            chat_id=chat_id,
            event_type=event_type.value,
            payload=payload,
        )
        persisted_event = ChatEvent.from_mapping(event)
        logger.info(
            "chat_event_persisted",
            extra={"chat_id": chat_id, "event_id": persisted_event.id, "event_type": event_type.value},
        )
        return persisted_event
