from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Any

from jieba import lcut_for_search
from rank_bm25 import BM25Okapi
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.mysql import Chunk, Document


# BM25 使用的索引项：只保留 MySQL chunks 中参与检索的标量字段和正文。
@dataclass(frozen=True)
class BM25Chunk:
    chunk_id: int
    document_id: int
    title: str
    page_no: int | None
    content: str
    metadata: dict[str, Any] | None


# BM25 命中结果：在索引项基础上追加该 chunk 对当前查询的 BM25 分数。
@dataclass(frozen=True)
class BM25Hit:
    chunk_id: int
    document_id: int
    title: str
    page_no: int | None
    content: str
    metadata: dict[str, Any] | None
    score: float


# 进程内缓存：首次检索时从 MySQL 构建，数据变更后通过 invalidate_bm25_index 清空。
_index: tuple[BM25Okapi, list[BM25Chunk]] | None = None
_lock = threading.Lock()


def tokenize(text: str) -> list[str]:
    # jieba 搜索模式适合查询词切分；统一小写并去掉空白 token。
    return [
        token.strip()
        for token in lcut_for_search(text.lower())
        if token.strip() and not token.isspace()
    ]


def _build_index(rows) -> tuple[BM25Okapi, list[BM25Chunk]]:
    chunks = [
        BM25Chunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            title=title,
            page_no=chunk.page_no,
            content=chunk.content,
            metadata=chunk.meta,
        )
        for chunk, title in rows
    ]
    return (
        BM25Okapi([tokenize(chunk.content) for chunk in chunks]),
        chunks,
    )


async def _ensure_index(db: AsyncSession) -> tuple[BM25Okapi, list[BM25Chunk]]:
    global _index
    # 索引已存在时直接复用，避免每次查询都全表加载 chunks。
    if _index is not None:
        return _index

    rows = (
        await db.execute(
            select(Chunk, Document.title)
            .join(Document, Document.id == Chunk.document_id)
            .where(Chunk.is_active.is_(True))
            .order_by(Chunk.id.asc())
        )
    ).all()
    built = await asyncio.to_thread(_build_index, rows)

    with _lock:
        if _index is None:
            _index = built
    return _index


async def bm25_search(
    db: AsyncSession,
    query: str,
    top_n: int = 10,
    *,
    document_ids: list[int] | None = None,
) -> list[BM25Hit]:
    bm25, chunks = await _ensure_index(db)
    if not chunks:
        return []

    # 查询同样需要分词，只有与语料 token 对齐才能得到有效分数。
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    # get_scores 会为每个 chunk 计算一次 BM25 分数，这里按分数从高到低排序。
    scores = await asyncio.to_thread(bm25.get_scores, query_tokens)
    # 可选：按 document_ids 过滤候选 chunk，再在全量分数中取对应分。
    if document_ids is not None:
        score_map = {chunk.chunk_id: score for chunk, score in zip(chunks, scores)}
        candidates = [c for c in chunks if c.document_id in document_ids]
        ranked = sorted(
            ((chunk, score_map.get(chunk.chunk_id, 0.0)) for chunk in candidates),
            key=lambda item: item[1],
            reverse=True,
        )
    else:
        ranked = sorted(zip(chunks, scores), key=lambda item: item[1], reverse=True)
    hits: list[BM25Hit] = []
    for chunk, score in ranked:
        # 得分为 0 表示查询词在该 chunk 中完全没有命中，无需返回。
        if score <= 0:
            continue
        hits.append(
            BM25Hit(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                title=chunk.title,
                page_no=chunk.page_no,
                content=chunk.content,
                metadata=chunk.metadata,
                score=float(score),
            )
        )
        if len(hits) >= top_n:
            break
    return hits


def invalidate_bm25_index() -> None:
    # 文档上传、重传或删除后调用，强制下一次检索重建索引。
    global _index
    with _lock:
        _index = None
