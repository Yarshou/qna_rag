import asyncio

import pytest

from app.domain import ChatEvent, EventType
from app.events import InMemoryEventBroker


@pytest.mark.anyio
async def test_in_memory_event_broker_delivers_published_event_to_subscriber() -> None:
    broker = InMemoryEventBroker()
    subscription = await broker.subscribe("chat-1")
    event = ChatEvent.from_mapping(
        {
            "id": "evt-1",
            "chat_id": "chat-1",
            "event_type": EventType.MESSAGE_RECEIVED.value,
            "payload": {"message_id": "msg-1"},
            "created_at": "2026-04-09T10:00:00+00:00",
        }
    )

    await broker.publish(event)

    delivered = await asyncio.wait_for(subscription.queue.get(), timeout=0.5)
    assert delivered.id == event.id


@pytest.mark.anyio
async def test_in_memory_event_broker_filters_events_by_chat_id() -> None:
    broker = InMemoryEventBroker()
    subscription = await broker.subscribe("chat-1")
    other_event = ChatEvent.from_mapping(
        {
            "id": "evt-2",
            "chat_id": "chat-2",
            "event_type": EventType.MESSAGE_PROCESSING.value,
            "payload": None,
            "created_at": "2026-04-09T10:00:01+00:00",
        }
    )

    await broker.publish(other_event)

    with pytest.raises(asyncio.QueueEmpty):
        subscription.queue.get_nowait()


@pytest.mark.anyio
async def test_in_memory_event_broker_supports_multiple_subscribers_for_same_chat() -> None:
    broker = InMemoryEventBroker()
    first = await broker.subscribe("chat-1")
    second = await broker.subscribe("chat-1")
    event = ChatEvent.from_mapping(
        {
            "id": "evt-3",
            "chat_id": "chat-1",
            "event_type": EventType.TOOL_CALLED.value,
            "payload": {"tool_name": "read_knowledge_file"},
            "created_at": "2026-04-09T10:00:02+00:00",
        }
    )

    await broker.publish(event)

    assert (await asyncio.wait_for(first.queue.get(), timeout=0.5)).id == event.id
    assert (await asyncio.wait_for(second.queue.get(), timeout=0.5)).id == event.id


@pytest.mark.anyio
async def test_in_memory_event_broker_unsubscribe_is_safe_and_does_not_break_other_subscribers() -> None:
    broker = InMemoryEventBroker()
    removed = await broker.subscribe("chat-1")
    active = await broker.subscribe("chat-1")
    await broker.unsubscribe(removed)
    await broker.unsubscribe(removed)
    event = ChatEvent.from_mapping(
        {
            "id": "evt-4",
            "chat_id": "chat-1",
            "event_type": EventType.MESSAGE_COMPLETED.value,
            "payload": {"assistant_message_id": "msg-2"},
            "created_at": "2026-04-09T10:00:03+00:00",
        }
    )

    await broker.publish(event)

    assert (await asyncio.wait_for(active.queue.get(), timeout=0.5)).id == event.id
    with pytest.raises(asyncio.QueueEmpty):
        removed.queue.get_nowait()
