from pathlib import Path

import pytest

from app.knowledge import KnowledgeIndexer, KnowledgeLoader, KnowledgeRetriever


@pytest.fixture
def knowledge_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "fixtures" / "knowledge"


def test_loader_lists_only_supported_documents(knowledge_dir: Path) -> None:
    loader = KnowledgeLoader(knowledge_dir)

    documents = loader.list_documents()

    assert [document.filename for document in documents] == [
        "deployment_notes.md",
        "python_basics.txt",
    ]
    assert all(document.checksum for document in documents)
    assert all(document.updated_at is not None for document in documents)
    assert all(not document.path.startswith("/") for document in documents)


def test_loader_get_document_returns_none_for_unknown_id(knowledge_dir: Path) -> None:
    loader = KnowledgeLoader(knowledge_dir)

    assert loader.get_document("missing-file-id") is None


def test_retriever_returns_ranked_hits_and_snippets(knowledge_dir: Path) -> None:
    loader = KnowledgeLoader(knowledge_dir)
    retriever = KnowledgeRetriever(loader)

    result = retriever.search_knowledge_base("readiness startup", limit=2)

    assert result.query == "readiness startup"
    assert len(result.hits) == 1
    assert result.hits[0].filename == "deployment_notes.md"
    assert result.hits[0].score > 0
    assert result.hits[0].snippet is not None
    assert "readiness" in result.hits[0].snippet.lower()


def test_retriever_reads_single_document_by_id(knowledge_dir: Path) -> None:
    loader = KnowledgeLoader(knowledge_dir)
    retriever = KnowledgeRetriever(loader)
    document = loader.list_documents()[0]

    loaded_document = retriever.read_knowledge_file(document.id)

    assert loaded_document is not None
    assert loaded_document.id == document.id
    assert loaded_document.content == document.content


def test_indexer_build_and_refresh_are_deterministic(knowledge_dir: Path) -> None:
    loader = KnowledgeLoader(knowledge_dir)
    indexer = KnowledgeIndexer(loader)

    initial_documents = indexer.build_index()
    refreshed_documents = indexer.refresh_index()

    assert [document.id for document in initial_documents] == [document.id for document in refreshed_documents]


def test_loader_raises_for_missing_directory(tmp_path: Path) -> None:
    missing_dir = tmp_path / "knowledge"

    with pytest.raises(FileNotFoundError):
        KnowledgeLoader(missing_dir)
