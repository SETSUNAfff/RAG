import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


class _FakeEmbeddingModel:
    def __init__(self, path: str) -> None:
        self.path = path

    def encode(self, chunks: list[str]) -> "_FakeEmbeddings":
        return _FakeEmbeddings(len(chunks))


class _FakeEmbeddings:
    def __init__(self, count: int) -> None:
        self._rows = [[0.1] * 768 for _ in range(count)]

    def tolist(self) -> list[list[float]]:
        return self._rows


def test_ingestion_uses_mysql_chunk_ids_in_milvus() -> None:
    asyncio.run(_test_ingestion_uses_mysql_chunk_ids())


async def _test_ingestion_uses_mysql_chunk_ids() -> None:
    from services import ingestion

    db = AsyncMock()
    document = SimpleNamespace(
        id=42,
        status="pending",
        version=1,
        error_message=None,
    )
    db.get.return_value = document
    db_chunks = [SimpleNamespace(id=1001), SimpleNamespace(id=1002)]

    with (
        patch.object(ingestion, "extract_text", return_value="first\n\nsecond"),
        patch.object(ingestion, "split_text", return_value=["first", "second"]),
        patch.dict("os.environ", {"EMBEDDING_MODEL_PATH": "fake-model"}),
        patch("dotenv.load_dotenv", return_value=None),
        patch(
            "sentence_transformers.SentenceTransformer",
            _FakeEmbeddingModel,
        ),
        patch.object(
            ingestion,
            "create_chunks",
            new=AsyncMock(return_value=db_chunks),
        ) as create_chunks_mock,
        patch(
            "crud.milvus.knowledge_chunks.insert_knowledge_chunks",
            return_value={"insert_count": 2},
        ) as insert_mock,
    ):
        result = await ingestion.ingest_uploaded_file(
            db,
            "test.txt",
            b"content",
            document.id,
        )

    create_chunks_mock.assert_awaited_once()
    insert_mock.assert_called_once()
    assert insert_mock.call_args.kwargs["chunk_id"] == [1001, 1002]
    assert insert_mock.call_args.kwargs["document_id"] == 42
    assert result == {"insert_count": 2}
    assert document.status == "ready"
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(document)


def test_reindex_hard_deletes_old_mysql_and_milvus_chunks() -> None:
    asyncio.run(_test_reindex_hard_deletes_old_mysql_and_milvus_chunks())


async def _test_reindex_hard_deletes_old_mysql_and_milvus_chunks() -> None:
    from services import ingestion

    db = AsyncMock()
    document = SimpleNamespace(
        id=7,
        status="ready",
        version=3,
        error_message=None,
    )
    db.get.return_value = document

    with (
        patch.object(ingestion, "extract_text", return_value="new content"),
        patch.object(ingestion, "split_text", return_value=["new content"]),
        patch.dict("os.environ", {"EMBEDDING_MODEL_PATH": "fake-model"}),
        patch("dotenv.load_dotenv", return_value=None),
        patch(
            "sentence_transformers.SentenceTransformer",
            _FakeEmbeddingModel,
        ),
        patch.object(
            ingestion,
            "hard_delete_chunks_by_document",
            new=AsyncMock(),
        ) as hard_delete_mock,
        patch.object(
            ingestion,
            "create_chunks",
            new=AsyncMock(return_value=[SimpleNamespace(id=2001)]),
        ),
        patch(
            "crud.milvus.knowledge_chunks.delete_document_chunks",
            return_value={},
        ) as delete_milvus_mock,
        patch(
            "crud.milvus.knowledge_chunks.insert_knowledge_chunks",
            return_value={"insert_count": 1},
        ),
    ):
        await ingestion.ingest_uploaded_file(
            db,
            "test.md",
            b"content",
            document.id,
            replace_existing=True,
        )

    hard_delete_mock.assert_awaited_once_with(db, 7)
    delete_milvus_mock.assert_called_once_with(7)
    assert document.version == 4
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(document)


def test_ingestion_marks_document_failed_and_compensates_milvus() -> None:
    asyncio.run(_test_ingestion_marks_document_failed_and_compensates_milvus())


async def _test_ingestion_marks_document_failed_and_compensates_milvus() -> None:
    from services import ingestion

    db = AsyncMock()
    document = SimpleNamespace(
        id=9,
        status="pending",
        version=1,
        error_message=None,
    )
    db.get.return_value = document

    with (
        patch.object(ingestion, "extract_text", return_value="content"),
        patch.object(ingestion, "split_text", return_value=["content"]),
        patch.dict("os.environ", {"EMBEDDING_MODEL_PATH": "fake-model"}),
        patch("dotenv.load_dotenv", return_value=None),
        patch(
            "sentence_transformers.SentenceTransformer",
            _FakeEmbeddingModel,
        ),
        patch.object(
            ingestion,
            "create_chunks",
            new=AsyncMock(return_value=[SimpleNamespace(id=3001)]),
        ),
        patch(
            "crud.milvus.knowledge_chunks.delete_document_chunks",
            return_value={},
        ) as delete_milvus_mock,
        patch(
            "crud.milvus.knowledge_chunks.insert_knowledge_chunks",
            side_effect=RuntimeError("milvus down"),
        ),
    ):
        with pytest.raises(RuntimeError, match="milvus down"):
            await ingestion.ingest_uploaded_file(
                db,
                "test.txt",
                b"content",
                document.id,
            )

    db.rollback.assert_awaited_once()
    delete_milvus_mock.assert_called_once_with(9)
    assert document.status == "failed"
    assert "milvus down" in document.error_message
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(document)
