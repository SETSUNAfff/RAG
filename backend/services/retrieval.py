from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from crud.milvus.knowledge_chunks import hybrid_search_knowledge_chunks
from crud.mysql.chunks import get_chunk_details_by_ids
from services.cache import get_cached_search, set_cached_search
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

    def to_cache_dict(self) -> dict[str, Any]:
        # 完整序列化检索结果，Redis 缓存恢复后可直接构造 RetrievalResult。
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "title": self.title,
            "page_no": self.page_no,
            "content": self.content,
            "metadata": self.metadata,
            "vector_score": self.vector_score,
            "bm25_score": self.bm25_score,
            "rrf_score": self.rrf_score,
            "rerank_score": self.rerank_score,
        }

    @classmethod
    def from_cache_dict(cls, data: dict[str, Any]) -> "RetrievalResult":
        # 从 Redis 中的 JSON 恢复检索结果。
        return cls(**data)


def _encode_query(query: str) -> list[list[float]]:
    return get_embedding_model().encode([query]).tolist()


async def _hybrid_search(
    db: AsyncSession,
    query: str,
    top_n: int,
    *,
    vector_limit: int = 10,
    sparse_limit: int = 10,
    document_ids: list[int] | None = None,
) -> list[RetrievalResult]:
    """Dense + sparse hybrid search in Milvus, then enrich from MySQL."""
    embedding = await asyncio.to_thread(_encode_query, query)
    hits = await asyncio.to_thread(
        hybrid_search_knowledge_chunks,
        query_embedding=embedding[0],
        query_text=query,
        top_k=top_n,
        vector_limit=vector_limit,
        sparse_limit=sparse_limit,
        document_ids=document_ids,
    )
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
                rrf_score=float(hit["score"]),
            )
        )
    return results


async def hybrid_search(
    db: AsyncSession,
    query: str,
    *,
    top_k: int = 10,
    vector_top_n: int = 20,
    bm25_top_n: int = 20,
    rrf_candidates: int = 20,
    use_rerank: bool = True,
    document_ids: list[int] | None = None,
) -> list[RetrievalResult]:
    """Milvus hybrid search + optional cross-encoder reranking."""
    # 先查 Redis；命中则跳过 Milvus 检索和 rerank。
    if document_ids is None:
        cached = await get_cached_search(
            query,
            top_k,
            vector_top_n,
            bm25_top_n,
            rrf_candidates,
            use_rerank,
        )
        if cached is not None:
            return [RetrievalResult.from_cache_dict(item) for item in cached]

    fused = await _hybrid_search(
        db,
        query,
        rrf_candidates,
        vector_limit=vector_top_n,
        sparse_limit=bm25_top_n,
        document_ids=document_ids,
    )

    if use_rerank and fused:
        from services.rerank import rerank_results

        fused = await asyncio.to_thread(rerank_results, query, fused)
    results = fused[:top_k]

    # 把最终结果写入 Redis，5 分钟内相同查询直接复用。
    if document_ids is None:
        await set_cached_search(
            query,
            top_k,
            vector_top_n,
            bm25_top_n,
            rrf_candidates,
            use_rerank,
            [item.to_cache_dict() for item in results],
        )
    return results
