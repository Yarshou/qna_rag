from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from app.knowledge.models import KnowledgeDocument


@dataclass(frozen=True, slots=True)
class _KnowledgeFileRecord:
    document_id: str
    absolute_path: Path
    relative_path: str


class KnowledgeLoader:
    """Loads supported text documents from a configured knowledge base directory."""

    def __init__(
        self,
        knowledge_base_dir: str | Path,
        supported_extensions: tuple[str, ...] = (".txt", ".md", ".rst", ".text"),
    ) -> None:
        """Initialize the loader with an explicit KB directory and allowed text extensions."""
        self._knowledge_base_dir = Path(knowledge_base_dir).expanduser().resolve()
        self._supported_extensions = tuple(extension.lower() for extension in supported_extensions)
        self._validate_knowledge_base_dir()

    def list_documents(self) -> list[KnowledgeDocument]:
        """Return all supported knowledge documents in deterministic path order."""
        documents: list[KnowledgeDocument] = []
        for record in self._iter_file_records():
            documents.append(self._read_document(record))
        return documents

    def get_document(self, file_id: str) -> KnowledgeDocument | None:
        """Return a single knowledge document by its stable file id, or `None` if it does not exist."""
        for record in self._iter_file_records():
            if record.document_id == file_id:
                return self._read_document(record)
        return None

    def _validate_knowledge_base_dir(self) -> None:
        if not self._knowledge_base_dir.exists():
            raise FileNotFoundError(f"Knowledge base directory does not exist: {self._knowledge_base_dir}")

        if not self._knowledge_base_dir.is_dir():
            raise NotADirectoryError(f"Knowledge base path is not a directory: {self._knowledge_base_dir}")

    def _iter_file_records(self) -> list[_KnowledgeFileRecord]:
        records: list[_KnowledgeFileRecord] = []
        for path in sorted(self._knowledge_base_dir.rglob("*")):
            if not path.is_file():
                continue

            if path.suffix.lower() not in self._supported_extensions:
                continue

            relative_path = path.relative_to(self._knowledge_base_dir).as_posix()
            records.append(
                _KnowledgeFileRecord(
                    document_id=self._build_document_id(relative_path),
                    absolute_path=path,
                    relative_path=relative_path,
                )
            )

        return records

    @staticmethod
    def _build_document_id(relative_path: str) -> str:
        return sha256(relative_path.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _read_document(record: _KnowledgeFileRecord) -> KnowledgeDocument:
        content = record.absolute_path.read_text(encoding="utf-8")
        stat_result = record.absolute_path.stat()
        updated_at = datetime.fromtimestamp(stat_result.st_mtime, tz=UTC)

        return KnowledgeDocument(
            id=record.document_id,
            filename=record.absolute_path.name,
            path=record.relative_path,
            content=content,
            checksum=sha256(content.encode("utf-8")).hexdigest(),
            updated_at=updated_at,
        )
