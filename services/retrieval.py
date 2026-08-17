from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from crud.milvus.knowledge_chunks import search_knowledge_chunks
from crud.mysql.bm25 import bm25_search
from crud.mysql.chunks import get_chunk_details_by_ids
from services.embeddings import get_embedding_model


@dataclass
class RetrievalResult:
    chunk_id: int
    document_id: int
    title: str
    page_no: int | None
    content: str
    metadata: dict[str, Any] | None
    vector_score: float | None = None
    bm25_score: float | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None

    def to_tool_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "title": self.title,
            "page_no": self.page_no,
            "content": self.content,
        }


async def _vector_search(
    db: AsyncSession,
    query: str,
    top_n: int,
) -> list[RetrievalResult]:
    embedding = get_embedding_model().encode([query]).tolist()
    hits = search_knowledge_chunks(embedding, top_n)
    if not hits:
        return []

    details = {
        chunk.id: (chunk, title)
        for chunk, title in await get_chunk_details_by_ids(
            db,
            [hit["chunk_id"] for hit in hits],
        )
    }
    results: list[RetrievalResult] = []
    for hit in hits:
        detail = details.get(hit["chunk_id"])
        if detail is None:
            continue
        chunk, title = detail
        results.append(
            RetrievalResult(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                title=title,
                page_no=chunk.page_no,
                content=chunk.content,
                metadata=chunk.meta,
                vector_score=float(hit["score"]),
            )
        )
    return results


async def _bm25_search(
    db: AsyncSession,
    query: str,
    top_n: int,
) -> list[RetrievalResult]:
    hits = await bm25_search(db, query, top_n)
    return [
        RetrievalResult(
            chunk_id=hit.chunk_id,
            document_id=hit.document_id,
            title=hit.title,
            page_no=hit.page_no,
            content=hit.content,
            metadata=hit.metadata,
            bm25_score=hit.score,
        )
        for hit in hits
    ]


def rrf_merge(
    vector_results: list[RetrievalResult],
    bm25_results: list[RetrievalResult],
    *,
    k: int = 60,
    top_n: int = 10,
) -> list[RetrievalResult]:
    """Reciprocal Rank Fusion over vector and BM25 result lists."""
    merged: dict[int, RetrievalResult] = {}

    def _base(item: RetrievalResult) -> RetrievalResult:
        return RetrievalResult(
            chunk_id=item.chunk_id,
            document_id=item.document_id,
            title=item.title,
            page_no=item.page_no,
            content=item.content,
            metadata=item.metadata,
        )

    for results, score_attr in (
        (vector_results, "vector_score"),
        (bm25_results, "bm25_score"),
    ):
        for rank, item in enumerate(results, start=1):
            current = merged.setdefault(item.chunk_id, _base(item))
            if score_attr == "vector_score":
                current.vector_score = item.vector_score
            else:
                current.bm25_score = item.bm25_score
            current.rrf_score = (current.rrf_score or 0.0) + 1.0 / (k + rank)

    return sorted(
        merged.values(),
        key=lambda item: item.rrf_score or 0.0,
        reverse=True,
    )[:top_n]


async def hybrid_search(
    db: AsyncSession,
    query: str,
    *,
    top_k: int = 3,
    vector_top_n: int = 10,
    bm25_top_n: int = 10,
    rrf_candidates: int = 10,
    use_rerank: bool = True,
) -> list[RetrievalResult]:
    """Run vector + BM25 fusion, then optional cross-encoder reranking."""
    vector_results = await _vector_search(db, query, vector_top_n)
    bm25_results = await _bm25_search(db, query, bm25_top_n)
    fused = rrf_merge(
        vector_results,
        bm25_results,
        top_n=rrf_candidates,
    )

    if use_rerank:
        from services.rerank import rerank_results

        fused = rerank_results(query, fused)
    return fused[:top_k]
