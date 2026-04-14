"""In-memory knowledge document index built from a KnowledgeLoader.

The indexer solves the per-query filesystem scan problem: instead of calling
``KnowledgeLoader.list_documents()`` — which runs ``rglob()`` on every
invocation — the indexer loads all documents once at application startup and
keeps them in memory for the lifetime of the process.

Typical usage
-------------
Build the index once during the application lifespan (see
``app/config/app.py``) and pass the indexer instance to a
:class:`~app.knowledge.retriever.KnowledgeRetriever`.  When the knowledge
base directory changes, call :meth:`refresh_index` to rebuild.
"""

from app.knowledge.loader import KnowledgeLoader
from app.knowledge.models import KnowledgeDocument


class KnowledgeIndexer:
    """Builds and refreshes an explicit in-memory view of knowledge documents.

    The indexer satisfies :class:`~app.knowledge.retriever.DocumentStoreProtocol`
    and can be used anywhere a :class:`~app.knowledge.loader.KnowledgeLoader`
    is accepted by that protocol.
    """

    def __init__(self, loader: KnowledgeLoader) -> None:
        """Initialize the indexer with the loader used to enumerate KB documents."""
        self._loader = loader
        self._documents: list[KnowledgeDocument] = []

    def build_index(self) -> list[KnowledgeDocument]:
        """Load all documents from the knowledge base directory into memory.

        Subsequent calls to :meth:`list_documents` and :meth:`get_document`
        will use this cached list without touching the filesystem.

        Returns
        -------
        list[KnowledgeDocument]
            A snapshot of the indexed documents (copy, not the internal list).
        """
        self._documents = self._loader.list_documents()
        return list(self._documents)

    def refresh_index(self) -> list[KnowledgeDocument]:
        """Rebuild the in-memory index using the latest filesystem state.

        Useful when knowledge base files are added or removed at runtime
        without restarting the application.

        Returns
        -------
        list[KnowledgeDocument]
            A snapshot of the refreshed documents.
        """
        return self.build_index()

    def list_documents(self) -> list[KnowledgeDocument]:
        """Return all currently indexed documents (no filesystem I/O).

        Returns
        -------
        list[KnowledgeDocument]
            A copy of the in-memory document list.  Empty until
            :meth:`build_index` has been called at least once.
        """
        return list(self._documents)

    def get_document(self, file_id: str) -> KnowledgeDocument | None:
        """Look up a single document by its stable file ID (no filesystem I/O).

        Parameters
        ----------
        file_id:
            The SHA-256-derived identifier assigned by
            :class:`~app.knowledge.loader.KnowledgeLoader`.

        Returns
        -------
        KnowledgeDocument | None
            The matching document, or ``None`` if not found in the current index.
        """
        return next((doc for doc in self._documents if doc.id == file_id), None)
