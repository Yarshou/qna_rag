"""Loader-level tests for the knowledge base layer."""

from pathlib import Path

import pytest

from app.knowledge import KnowledgeLoader


@pytest.fixture
def knowledge_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "test_data" / "knowledge"


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


def test_loader_raises_for_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        KnowledgeLoader(tmp_path / "knowledge")


def test_loader_skips_oversized_files(tmp_path: Path) -> None:
    (tmp_path / "small.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "large.txt").write_bytes(b"x" * 100)

    loader = KnowledgeLoader(tmp_path, max_file_size_bytes=50)
    documents = loader.list_documents()

    assert len(documents) == 1
    assert documents[0].filename == "small.txt"


def test_loader_skips_non_utf8_files(tmp_path: Path) -> None:
    (tmp_path / "valid.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "binary.txt").write_bytes(b"\xff\xfe invalid utf-8 \x00\x01")

    loader = KnowledgeLoader(tmp_path)
    documents = loader.list_documents()

    assert len(documents) == 1
    assert documents[0].filename == "valid.txt"


def test_loader_get_document_returns_none_for_oversized_file(tmp_path: Path) -> None:
    (tmp_path / "big.txt").write_bytes(b"x" * 200)
    loader = KnowledgeLoader(tmp_path, max_file_size_bytes=50)

    file_id = loader._build_document_id("big.txt")
    assert loader.get_document(file_id) is None
