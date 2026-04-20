"""Integration tests for the stateless hybrid retriever.

Uses a real on-disk SQLite (tmp_path) with FTS5 + cosine-on-embeddings and a
deterministic stub embeddings client, so the full pipeline is exercised
without any network or LLM provider.
"""

from pathlib import Path

import pytest

from app.db.connection import build_connection_factory
from app.knowledge import KnowledgeLoader, KnowledgeRetriever, sync_knowledge_index
from app.repositories.knowledge import KnowledgeRepository


class _StubEmbeddingsClient:
    """Returns a 3-D vector biased toward the first character of each input."""

    def __init__(self) -> None:
        self.call_count = 0

    def create_embeddings(self, inputs: list[str]) -> list[list[float]]:
        self.call_count += 1
        out: list[list[float]] = []
        for text in inputs:
            head = (text.strip() + "   ")[0].lower()
            if head in {"r", "d", "s"}:
                out.append([1.0, 0.0, 0.0])
            elif head in {"p", "k"}:
                out.append([0.0, 1.0, 0.0])
            else:
                out.append([0.0, 0.0, 1.0])
        return out


def _setup_kb(tmp_path: Path, files: dict[str, str]) -> Path:
    kb = tmp_path / "kb"
    kb.mkdir(exist_ok=True)
    for name, content in files.items():
        (kb / name).write_text(content, encoding="utf-8")
    return kb


def _repository(db_path: Path) -> KnowledgeRepository:
    return KnowledgeRepository(connection_factory=build_connection_factory(db_path))


async def _build(tmp_path: Path, files: dict[str, str]):
    kb = _setup_kb(tmp_path, files)
    loader = KnowledgeLoader(kb)
    stub = _StubEmbeddingsClient()
    db_path = tmp_path / "test.sqlite3"
    repo = _repository(db_path)
    await sync_knowledge_index(
        loader=loader,
        embeddings_client=stub,
        repository=repo,
        embedding_model="stub-model",
        batch_size=16,
    )
    retriever = KnowledgeRetriever(
        repository=repo,
        embeddings_client=stub,
        loader=loader,
        hybrid_lexical_weight=0.5,
    )
    return retriever, stub, loader, repo


# ---------------------------------------------------------------------------
# sync_knowledge_index
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_sync_index_embeds_every_document(tmp_path: Path) -> None:
    _, stub, _, _ = await _build(tmp_path, {"a.txt": "readiness checks", "b.txt": "kubernetes probe"})
    assert stub.call_count >= 1


@pytest.mark.anyio
async def test_sync_index_checksum_cache_skips_reembedding(tmp_path: Path) -> None:
    kb = _setup_kb(tmp_path, {"a.txt": "readiness checks"})
    loader = KnowledgeLoader(kb)
    stub = _StubEmbeddingsClient()
    db = tmp_path / "db.sqlite3"
    repo = _repository(db)

    await sync_knowledge_index(loader, stub, repo, "stub-model", 16)
    after_first = stub.call_count

    await sync_knowledge_index(loader, stub, repo, "stub-model", 16)
    assert stub.call_count == after_first


@pytest.mark.anyio
async def test_sync_index_reembeds_when_content_changes(tmp_path: Path) -> None:
    kb = _setup_kb(tmp_path, {"a.txt": "readiness"})
    loader = KnowledgeLoader(kb)
    stub = _StubEmbeddingsClient()
    db = tmp_path / "db.sqlite3"
    repo = _repository(db)

    await sync_knowledge_index(loader, stub, repo, "stub-model", 16)
    first = stub.call_count

    (kb / "a.txt").write_text("completely different content", encoding="utf-8")
    await sync_knowledge_index(loader, stub, repo, "stub-model", 16)

    assert stub.call_count > first


@pytest.mark.anyio
async def test_sync_index_removes_orphaned_rows(tmp_path: Path) -> None:
    kb = _setup_kb(tmp_path, {"a.txt": "hello", "b.txt": "world"})
    loader = KnowledgeLoader(kb)
    stub = _StubEmbeddingsClient()
    db = tmp_path / "db.sqlite3"
    repo = _repository(db)

    await sync_knowledge_index(loader, stub, repo, "stub-model", 16)

    (kb / "b.txt").unlink()
    count = await sync_knowledge_index(loader, stub, repo, "stub-model", 16)

    assert count == 1
    # Repository no longer contains the orphaned row.
    ids = await repo.list_file_ids()
    assert len(ids) == 1


# ---------------------------------------------------------------------------
# search_knowledge_base
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_search_returns_hits_with_both_sub_scores(tmp_path: Path) -> None:
    retriever, *_ = await _build(
        tmp_path,
        {
            "a.txt": "readiness probe deployment checks",
            "b.txt": "completely unrelated content here",
        },
    )

    result = await retriever.search_knowledge_base("readiness", limit=5)

    assert result.query == "readiness"
    assert len(result.hits) >= 1
    hit = result.hits[0]
    assert hit.filename == "a.txt"
    assert hit.lexical_score is not None
    assert hit.semantic_score is not None
    assert hit.snippet and "readiness" in hit.snippet.lower()


@pytest.mark.anyio
async def test_search_respects_limit(tmp_path: Path) -> None:
    retriever, *_ = await _build(
        tmp_path,
        {
            "a.txt": "readiness deployment probe",
            "b.txt": "readiness kubernetes probe",
            "c.txt": "readiness startup sequence",
        },
    )
    result = await retriever.search_knowledge_base("readiness", limit=2)
    assert len(result.hits) <= 2


@pytest.mark.anyio
async def test_search_hits_are_sorted_descending_by_fused_score(tmp_path: Path) -> None:
    retriever, *_ = await _build(
        tmp_path,
        {
            "a.txt": "readiness readiness readiness deployment",
            "b.txt": "readiness",
            "c.txt": "deployment",
        },
    )
    result = await retriever.search_knowledge_base("readiness deployment", limit=5)
    scores = [hit.score for hit in result.hits]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.anyio
async def test_search_empty_query_returns_empty(tmp_path: Path) -> None:
    retriever, *_ = await _build(tmp_path, {"a.txt": "something"})
    result = await retriever.search_knowledge_base("", limit=5)
    assert result.hits == []


@pytest.mark.anyio
async def test_search_falls_back_to_semantic_only_when_fts_has_no_match(tmp_path: Path) -> None:
    retriever, *_ = await _build(tmp_path, {"a.txt": "readiness probe"})

    result = await retriever.search_knowledge_base("zylophone quasar", limit=5)
    assert len(result.hits) == 1


@pytest.mark.anyio
async def test_search_sanitises_special_characters_in_query(tmp_path: Path) -> None:
    retriever, *_ = await _build(tmp_path, {"a.txt": "readiness probe"})

    result = await retriever.search_knowledge_base('readiness "OR" !! *', limit=5)
    assert len(result.hits) == 1
    assert result.hits[0].filename == "a.txt"


# ---------------------------------------------------------------------------
# read_knowledge_file
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_read_knowledge_file_returns_document_content(tmp_path: Path) -> None:
    retriever, _, loader, _ = await _build(tmp_path, {"policy.txt": "vacation policy"})
    docs = loader.list_documents()

    loaded = await retriever.read_knowledge_file(docs[0].id)
    assert loaded is not None
    assert loaded.content == "vacation policy"


@pytest.mark.anyio
async def test_read_knowledge_file_returns_none_for_unknown_id(tmp_path: Path) -> None:
    retriever, *_ = await _build(tmp_path, {"a.txt": "x"})
    assert await retriever.read_knowledge_file("nonexistent-id") is None
