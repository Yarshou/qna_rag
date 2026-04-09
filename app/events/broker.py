import asyncio
from dataclasses import dataclass
from typing import Protocol

from app.domain import ChatEvent


@dataclass(slots=True)
class EventSubscription:
    chat_id: str
    queue: asyncio.Queue[ChatEvent]


class EventBroker(Protocol):
    async def publish(self, event: ChatEvent) -> None:
        """Deliver a persisted event to active subscribers."""

    async def subscribe(self, chat_id: str) -> EventSubscription:
        """Register a subscriber for one chat stream."""

    async def unsubscribe(self, subscription: EventSubscription) -> None:
        """Remove a previously registered subscriber."""


_event_broker: EventBroker | None = None


def configure_event_broker(broker: EventBroker) -> None:
    global _event_broker
    _event_broker = broker


def get_event_broker() -> EventBroker:
    global _event_broker
    if _event_broker is None:
        from app.events.in_memory import InMemoryEventBroker

        _event_broker = InMemoryEventBroker()
    return _event_broker
