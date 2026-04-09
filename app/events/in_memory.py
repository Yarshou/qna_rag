import asyncio

from app.domain import ChatEvent
from app.events.broker import EventBroker, EventSubscription


class InMemoryEventBroker(EventBroker):
    """Process-local pub/sub broker keyed by chat id."""

    def __init__(self) -> None:
        self._subscriptions: dict[str, set[asyncio.Queue[ChatEvent]]] = {}
        self._lock = asyncio.Lock()

    async def publish(self, event: ChatEvent) -> None:
        async with self._lock:
            subscribers = tuple(self._subscriptions.get(event.chat_id, ()))

        for subscriber in subscribers:
            subscriber.put_nowait(event)

    async def subscribe(self, chat_id: str) -> EventSubscription:
        subscription = EventSubscription(chat_id=chat_id, queue=asyncio.Queue())

        async with self._lock:
            self._subscriptions.setdefault(chat_id, set()).add(subscription.queue)

        return subscription

    async def unsubscribe(self, subscription: EventSubscription) -> None:
        async with self._lock:
            subscribers = self._subscriptions.get(subscription.chat_id)
            if subscribers is None:
                return

            subscribers.discard(subscription.queue)
            if not subscribers:
                self._subscriptions.pop(subscription.chat_id, None)
