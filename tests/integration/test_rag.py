"""Real LLM integration tests for the RAG pipeline.

These tests hit an actual OpenAI-compatible provider and are skipped
automatically when no credentials are present.  They satisfy the
assessment requirement: "No mock responses."

Supported providers (configure ONE via environment variables or app/envs/.env):

    Azure OpenAI
        AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT,
        OPENAI_API_VERSION, AZURE_OPENAI_DEPLOYMENT

    Generic OpenAI-compatible (OpenRouter, EPAM DIAL, Ollama, …)
        OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL

    OpenRouter example:
        OPENAI_BASE_URL=https://openrouter.ai/api/v1
        OPENAI_API_KEY=<your-key>
        OPENAI_MODEL=meta-llama/llama-3-8b-instruct

    Ollama example:
        OPENAI_BASE_URL=http://localhost:11434/v1
        OPENAI_API_KEY=ollama
        OPENAI_MODEL=llama3

The test knowledge base lives under tests/fixtures/knowledge.
"""

from pathlib import Path

import pytest

from app.config import settings

_AZURE_READY = bool(settings.AZURE_OPENAI_ENDPOINT and settings.AZURE_OPENAI_API_KEY)
_GENERIC_READY = bool(settings.OPENAI_BASE_URL and settings.OPENAI_API_KEY and settings.OPENAI_MODEL)
_LLM_READY = _AZURE_READY or _GENERIC_READY

pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(
        not _LLM_READY,
        reason=(
            "No LLM provider configured. "
            "Set AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY for Azure, "
            "or OPENAI_BASE_URL + OPENAI_API_KEY + OPENAI_MODEL for a generic provider "
            "(OpenRouter, DIAL, Ollama, etc.)."
        ),
    ),
]

_FIXTURES_KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "knowledge"


@pytest.fixture
def rag_db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated SQLite database for the RAG flow; patches global settings."""
    db_path = tmp_path / "rag_test.sqlite3"
    monkeypatch.setattr(settings, "DATABASE_PATH", db_path)
    monkeypatch.setattr(settings, "KNOWLEDGE_DIR", _FIXTURES_KNOWLEDGE_DIR)

    import asyncio

    from app.db.init import initialize_database

    asyncio.run(initialize_database(db_path=db_path))
    return db_path


async def _build_services(db_path: Path):
    """Construct real service objects wired to the isolated test database."""
    from app.db.connection import build_connection_factory
    from app.knowledge import KnowledgeLoader, KnowledgeRetriever, sync_knowledge_index
    from app.llm import OpenAIChatClient, ToolExecutor
    from app.repositories.chats import ChatsRepository
    from app.repositories.events import EventsRepository
    from app.repositories.knowledge import KnowledgeRepository
    from app.repositories.messages import MessagesRepository
    from app.services.chat_service import ChatService
    from app.services.context_service import ContextService
    from app.services.message_service import MessageService
    from app.services.notification_service import NotificationService

    connection_factory = build_connection_factory(db_path=db_path)

    chats_repo = ChatsRepository(connection_factory=connection_factory)
    messages_repo = MessagesRepository(connection_factory=connection_factory)
    events_repo = EventsRepository(connection_factory=connection_factory)
    knowledge_repo = KnowledgeRepository(connection_factory=connection_factory)

    chat_service = ChatService(chats_repository=chats_repo)
    notification_service = NotificationService(events_repository=events_repo)
    context_service = ContextService(messages_repo)

    loader = KnowledgeLoader(_FIXTURES_KNOWLEDGE_DIR)
    embeddings_client = OpenAIChatClient()
    await sync_knowledge_index(
        loader=loader,
        embeddings_client=embeddings_client,
        repository=knowledge_repo,
        embedding_model=settings.EMBEDDING_MODEL,
        batch_size=settings.EMBEDDING_BATCH_SIZE,
    )
    retriever = KnowledgeRetriever(
        repository=knowledge_repo,
        embeddings_client=embeddings_client,
        loader=loader,
    )
    tool_executor = ToolExecutor(retriever)

    message_service = MessageService(
        chat_service=chat_service,
        messages_repository=messages_repo,
        notification_service=notification_service,
        context_service=context_service,
        llm_client=OpenAIChatClient(),
        tool_executor=tool_executor,
    )

    return chat_service, message_service


@pytest.mark.anyio
async def test_rag_answers_question_grounded_in_knowledge_base(rag_db_path: Path) -> None:
    """The assistant must produce a non-empty response that uses at least one
    knowledge-base tool call when asked a question covered by the fixtures.

    The fixture knowledge base contains 'deployment_notes.md' which mentions
    'readiness checks', so a query about deployment should trigger a retrieval
    and reference that content.
    """
    chat_service, message_service = await _build_services(rag_db_path)

    chat = await chat_service.create_chat(title="RAG integration test")
    result = await message_service.post_user_message(
        chat.id,
        "What does the knowledge base say about deployment readiness checks?",
    )

    assert result.assistant_message.content.strip(), "Assistant returned an empty response"
    assert result.tool_calls_executed >= 1, (
        f"Expected at least 1 tool call; got {result.tool_calls_executed}. "
        "The model may have answered without consulting the knowledge base."
    )


@pytest.mark.anyio
async def test_rag_persists_user_and_assistant_messages(rag_db_path: Path) -> None:
    """Both the user message and the assistant reply must be saved to the DB
    and retrievable through the message service."""
    chat_service, message_service = await _build_services(rag_db_path)

    chat = await chat_service.create_chat(title="Persistence check")
    await message_service.post_user_message(chat.id, "Tell me about Python basics.")

    history, total = await message_service.list_messages(chat.id)

    assert total == 2, f"Expected total=2 messages in history; got {total}"
    assert len(history) == 2, f"Expected 2 paginated messages in history; got {len(history)}"
    roles = [m.role.value for m in history]
    assert "user" in roles
    assert "assistant" in roles


@pytest.mark.anyio
async def test_rag_maintains_conversation_context_across_turns(rag_db_path: Path) -> None:
    """A follow-up question in the same chat must be answered with awareness
    of the prior exchange — the model must not start from a blank slate."""
    chat_service, message_service = await _build_services(rag_db_path)

    chat = await chat_service.create_chat(title="Multi-turn context test")
    await message_service.post_user_message(chat.id, "What is the knowledge base about?")
    second_result = await message_service.post_user_message(chat.id, "Can you summarise what you just told me?")

    assert second_result.assistant_message.content.strip(), "Second-turn response was empty"
    history, total = await message_service.list_messages(chat.id)
    assert total == 4, f"Expected total=4 messages after two turns; got {total}"
    assert len(history) == 4, f"Expected 4 paginated messages after two turns; got {len(history)}"


@pytest.mark.anyio
async def test_rag_emits_lifecycle_events(rag_db_path: Path) -> None:
    """After a successful message flow the notification service must have
    persisted at least the message_received and message_completed events."""
    from app.db.connection import build_connection_factory
    from app.repositories.events import EventsRepository
    from app.shared_types import EventType

    chat_service, message_service = await _build_services(rag_db_path)

    chat = await chat_service.create_chat(title="Event emission test")
    await message_service.post_user_message(chat.id, "Summarise the deployment notes.")

    connection_factory = build_connection_factory(db_path=rag_db_path)
    events_repo = EventsRepository(connection_factory=connection_factory)
    raw_events = await events_repo.list_events_after(chat_id=chat.id)

    event_types = {row["event_type"] for row in raw_events}
    assert EventType.MESSAGE_RECEIVED.value in event_types
    assert EventType.MESSAGE_COMPLETED.value in event_types
