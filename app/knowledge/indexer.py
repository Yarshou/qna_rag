from app.knowledge.loader import KnowledgeLoader
from app.knowledge.models import KnowledgeDocument


class KnowledgeIndexer:
    """Builds and refreshes an explicit in-memory view of knowledge documents."""

    def __init__(self, loader: KnowledgeLoader) -> None:
        """Initialize the indexer with the loader used to enumerate KB documents."""
        self._loader = loader
        self._documents: list[KnowledgeDocument] = []

    def build_index(self) -> list[KnowledgeDocument]:
        """Build and return the current in-memory index from the knowledge base directory."""
        self._documents = self._loader.list_documents()
        return list(self._documents)

    def refresh_index(self) -> list[KnowledgeDocument]:
        """Rebuild and return the in-memory index using the latest filesystem state."""
        return self.build_index()
