import logging
from collections.abc import Mapping

from app.domain import ChatEvent, EventType
from app.events import EventBroker, get_event_broker
from app.repositories.events import EventsRepository

logger = logging.getLogger(__name__)

EventPayload = Mapping[str, object] | None


class NotificationService:
    """Stores chat-processing lifecycle events when event persistence is enabled."""

    def __init__(
        self,
        events_repository: EventsRepository | None = None,
        *,
        broker: EventBroker | None = None,
        enabled: bool = True,
    ) -> None:
        self._events_repository = EventsRepository() if enabled and events_repository is None else events_repository
        self._broker = get_event_broker() if enabled and broker is None else broker

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

        if self._broker is not None:
            await self._broker.publish(persisted_event)
            logger.info(
                "chat_event_published",
                extra={"chat_id": chat_id, "event_id": persisted_event.id, "event_type": event_type.value},
            )

        return persisted_event
