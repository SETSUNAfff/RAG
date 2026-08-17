from threading import Lock
from typing import Any

from config.milvus_client import COLLECTION_NAME, get_milvus_client, init_milvus
from models.milvus.knowledge_chunks import (
    CHUNK_ID_FIELD,
    DOCUMENT_ID_FIELD,
    METADATA_FIELD,
    METRIC_TYPE,
    PAGE_NO_FIELD,
)

_initialized = False
_initialization_lock = Lock()


# 只在首次调用时初始化 Milvus 集合，未启动 Milvus 不会阻塞 FastAPI 启动。
def _ensure_milvus() -> None:
    global _initialized
    if _initialized:
        return
    with _initialization_lock:
        if not _initialized:
            init_milvus()
            _initialized = True


def insert_knowledge_chunks(
    chunk_id: list[int],
    document_id: int,
    embeddings: list[list[float]],
    page_no: list[int] | None = None,
    metadata: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    _ensure_milvus()
    client = get_milvus_client()
    if len(chunk_id) != len(embeddings):
        raise ValueError("chunk_id和embeddings必须是相同长度！")

    page_no = page_no if page_no is not None else [0] * len(chunk_id)
    metadata = metadata if metadata is not None else [{}] * len(chunk_id)

    if len(page_no) != len(chunk_id) or len(metadata) != len(chunk_id):
        raise ValueError(
            "chunk_id, page_no, metadata必须是相同长度！"
        )

    rows = [
        {
            "chunk_id": chunk_id,
            "embedding": embedding,
            "document_id": document_id,
            "page_no": page_no,
            "metadata": metadata,
        }
        for chunk_id, embedding, page_no, metadata in zip(
            chunk_id,
            embeddings,
            page_no,
            metadata,
        )
    ]

    return client.insert(collection_name=COLLECTION_NAME, data=rows)


def search_knowledge_chunks(
    query_embeddings: list[list[float]],
    top_k: int = 10,
    *,
    document_id: int | None = None,
) -> list[dict[str, Any]]:
    """Search Milvus by embedding and return scalar chunk metadata."""
    _ensure_milvus()
    client = get_milvus_client()
    search_filter = (
        f"{DOCUMENT_ID_FIELD} == {document_id}"
        if document_id is not None
        else ""
    )
    results = client.search(
        collection_name=COLLECTION_NAME,
        data=query_embeddings,
        limit=top_k,
        output_fields=[
            CHUNK_ID_FIELD,
            DOCUMENT_ID_FIELD,
            PAGE_NO_FIELD,
            METADATA_FIELD,
        ],
        search_params={"metric_type": METRIC_TYPE, "params": {}},
        filter=search_filter,
    )
    hits = results[0] if results else []
    parsed: list[dict[str, Any]] = []
    for hit in hits:
        parsed.append(
            {
                "chunk_id": hit.get(CHUNK_ID_FIELD, hit.get("id")),
                "document_id": hit.get(DOCUMENT_ID_FIELD),
                "page_no": hit.get(PAGE_NO_FIELD),
                "metadata": hit.get(METADATA_FIELD) or {},
                "score": hit.get("distance", 0.0),
            }
        )
    return parsed


def delete_knowledge_chunk(chunk_id: int) -> dict[str, int]:
    # 删除单条向量，用于 DELETE /chunks/{chunk_id} 的一致性清理。
    _ensure_milvus()
    client = get_milvus_client()
    return client.delete(
        collection_name=COLLECTION_NAME,
        filter=f"chunk_id == {chunk_id}",
    )


def delete_document_chunks(document_id: int) -> dict[str, int]:
    _ensure_milvus()
    client = get_milvus_client()
    return client.delete(
        collection_name=COLLECTION_NAME,
        filter=f"document_id == {document_id}",
    )


def replace_document_chunks(
    chunk_id: list[int],
    document_id: int,
    embeddings: list[list[float]],
    page_no: list[int] | None = None,
    metadata: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    delete_document_chunks(document_id)
    return insert_knowledge_chunks(
        chunk_id=chunk_id,
        document_id=document_id,
        embeddings=embeddings,
        page_no=page_no,
        metadata=metadata,
    )
