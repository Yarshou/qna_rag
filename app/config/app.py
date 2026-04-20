import contextlib
import logging

from fastapi import FastAPI

from app.api import router
from app.config import settings
from app.config.setup import setup
from app.db.connection import build_connection_factory, resolve_database_path
from app.db.init import initialize_database

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def lifespan(application: FastAPI):
    await initialize_database(db_path=resolve_database_path())

    application.state.knowledge_loader = None
    application.state.embeddings_client = None
    application.state.knowledge_repository = None

    if settings.KNOWLEDGE_DIR is None:
        yield
        return

    from app.knowledge import KnowledgeLoader, sync_knowledge_index
    from app.repositories.knowledge import KnowledgeRepository

    loader = KnowledgeLoader(settings.KNOWLEDGE_DIR)
    application.state.knowledge_loader = loader

    embeddings_client = None
    if settings.HYBRID_ENABLED:
        try:
            from app.llm import OpenAIChatClient

            embeddings_client = OpenAIChatClient()
        except Exception as exc:
            logger.warning(
                "knowledge_embeddings_client_unavailable",
                extra={"error_type": exc.__class__.__name__},
            )

    if embeddings_client is not None:
        application.state.embeddings_client = embeddings_client
        connection_factory = build_connection_factory(resolve_database_path())
        repository = KnowledgeRepository(connection_factory=connection_factory)
        application.state.knowledge_repository = repository

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

    yield


app = FastAPI(
    debug=settings.DEBUG,
    title="QNA-RAG",
    lifespan=lifespan,
    redirect_slashes=False,
    docs_url=None,
    redoc_url=None,
)
app.include_router(router=router)
setup(app=app)
