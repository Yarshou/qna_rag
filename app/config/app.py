import contextlib
import logging
from collections.abc import AsyncGenerator

from fastapi import FastAPI

from app.api import router
from app.config import settings
from app.config.setup import setup
from app.db.connection import resolve_database_path
from app.db.init import initialize_database

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    await initialize_database(db_path=resolve_database_path())

    # Build the knowledge index once at startup so that search queries read
    # from an in-memory list rather than scanning the filesystem on every call.
    application.state.knowledge_indexer = None
    if settings.KNOWLEDGE_DIR is not None:
        # Import here to avoid a circular dependency at module level.
        from app.knowledge import KnowledgeIndexer, KnowledgeLoader

        loader = KnowledgeLoader(settings.KNOWLEDGE_DIR)
        indexer = KnowledgeIndexer(loader)
        doc_count = len(indexer.build_index())
        application.state.knowledge_indexer = indexer
        logger.info("knowledge_index_built", extra={"doc_count": doc_count, "knowledge_dir": str(settings.KNOWLEDGE_DIR)})

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
