from typing import Any
from config.milvus_client import COLLECTION_NAME, client


def insert_knowledge_chunks(
    chunk_id: list[int],
    document_id: int,
    embeddings: list[list[float]],
    page_no: list[int] | None = None,
    metadata: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if len(chunk_id) != len(embeddings):
        raise ValueError("chunk_id and embeddings must have the same length")

    page_no = page_no if page_no is not None else [0] * len(chunk_id)
    metadata = metadata if metadata is not None else [{}] * len(chunk_id)

    if len(page_no) != len(chunk_id) or len(metadata) != len(chunk_id):
        raise ValueError(
            "chunk_id, page_no and metadata must have the same length"
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


def delete_document_chunks(document_id: int) -> dict[str, int]:
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
