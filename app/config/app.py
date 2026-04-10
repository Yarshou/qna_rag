import contextlib

from fastapi import FastAPI

from app.api import router
from app.config import settings
from app.config.setup import setup
from app.db.connection import resolve_database_path
from app.db.init import initialize_database


@contextlib.asynccontextmanager
async def lifespan(application: FastAPI):
    await initialize_database(db_path=resolve_database_path())
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
