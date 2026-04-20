import logging

from app.config.settings import Settings
from app.context import AppContext
from app.db.connection import build_connection_factory, resolve_database_path
from app.knowledge import KnowledgeLoader, KnowledgeRetriever, sync_knowledge_index
from app.llm import OpenAIChatClient, ToolExecutor
from app.repositories.knowledge import KnowledgeRepository

logger = logging.getLogger(__name__)


async def build_app_context(settings: Settings) -> AppContext:
    if settings.KNOWLEDGE_DIR is None:
        return AppContext(tool_executor=None)

    loader = KnowledgeLoader(settings.KNOWLEDGE_DIR)

    embeddings_client = None
    if settings.HYBRID_ENABLED:
        try:
            embeddings_client = OpenAIChatClient()
        except Exception as exc:
            logger.warning(
                "knowledge_embeddings_client_unavailable",
                extra={"error_type": exc.__class__.__name__},
            )

    if embeddings_client is None:
        return AppContext(tool_executor=None)

    connection_factory = build_connection_factory(resolve_database_path())
    repository = KnowledgeRepository(connection_factory=connection_factory)

    try:
        doc_count = await sync_knowledge_index(
            loader=loader,
            embeddings_client=embeddings_client,
            repository=repository,
            embedding_model=settings.EMBEDDING_MODEL,
            batch_size=settings.EMBEDDING_BATCH_SIZE,
        )
        logger.info(
            "knowledge_index_ready",
            extra={
                "doc_count": doc_count,
                "knowledge_dir": str(settings.KNOWLEDGE_DIR),
            },
        )
    except Exception as exc:
        logger.error(
            "knowledge_index_sync_failed",
            extra={"error_type": exc.__class__.__name__, "error": str(exc)},
        )
        return AppContext(tool_executor=None)

    retriever = KnowledgeRetriever(
        repository=repository,
        embeddings_client=embeddings_client,
        loader=loader,
        hybrid_lexical_weight=settings.HYBRID_LEXICAL_WEIGHT,
    )
    return AppContext(tool_executor=ToolExecutor(retriever))
