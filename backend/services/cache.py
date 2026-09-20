from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from config.redis import get_redis_client

logger = logging.getLogger(__name__)

_PREFIX = "rag"
# 会话历史缓存默认保留 7 天；检索结果变化快，默认只缓存 5 分钟。
CHAT_HISTORY_TTL_SECONDS = 60 * 60 * 24 * 7
SEARCH_CACHE_TTL_SECONDS = 5 * 60


def _key(*parts: str) -> str:
    # 所有 Redis key 统一带 rag 前缀，避免和其他应用混用。
    return ":".join((_PREFIX, *parts))


def _search_key(
    query: str,
    top_k: int,
    vector_top_n: int,
    bm25_top_n: int,
    rrf_candidates: int,
    use_rerank: bool,
) -> str:
    # 检索缓存 key 用完整检索参数生成哈希，避免不同参数互相命中。
    payload = json.dumps(
        {
            "query": query,
            "top_k": top_k,
            "vector_top_n": vector_top_n,
            "bm25_top_n": bm25_top_n,
            "rrf_candidates": rrf_candidates,
            "use_rerank": use_rerank,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return _key("search", digest)


def _conversation_key(conversation_id: int) -> str:
    # 会话历史缓存按 conversation_id 隔离。
    return _key("conversation", str(conversation_id), "history")


async def get_cached_search(
    query: str,
    top_k: int,
    vector_top_n: int,
    bm25_top_n: int,
    rrf_candidates: int,
    use_rerank: bool,
) -> list[dict[str, Any]] | None:
    try:
        # 命中返回 JSON，未命中或 Redis 不可用时返回 None，由调用方回退到 MySQL/Milvus。
        raw = await get_redis_client().get(
            _search_key(
                query,
                top_k,
                vector_top_n,
                bm25_top_n,
                rrf_candidates,
                use_rerank,
            )
        )
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        logger.debug("Redis search cache read failed", exc_info=True)
        return None


async def set_cached_search(
    query: str,
    top_k: int,
    vector_top_n: int,
    bm25_top_n: int,
    rrf_candidates: int,
    use_rerank: bool,
    results: list[dict[str, Any]],
) -> None:
    try:
        # 检索结果写入 Redis，带 TTL 防止旧结果长期占用内存。
        await get_redis_client().set(
            _search_key(
                query,
                top_k,
                vector_top_n,
                bm25_top_n,
                rrf_candidates,
                use_rerank,
            ),
            json.dumps(results, ensure_ascii=False),
            ex=SEARCH_CACHE_TTL_SECONDS,
        )
    except Exception:
        logger.debug("Redis search cache write failed", exc_info=True)


async def invalidate_search_cache() -> None:
    try:
        # 文档入库、重传或删除后清空全部检索缓存，避免返回旧数据。
        client = get_redis_client()
        async for key in client.scan_iter(f"{_PREFIX}:search:*"):
            await client.delete(key)
    except Exception:
        logger.debug("Redis search cache invalidation failed", exc_info=True)


async def get_cached_history(
    conversation_id: int,
) -> list[dict[str, str]] | None:
    try:
        # 会话历史缓存不存在时返回 None，调用方从 MySQL 加载后回填。
        raw = await get_redis_client().get(_conversation_key(conversation_id))
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        logger.debug("Redis conversation cache read failed", exc_info=True)
        return None


async def set_cached_history(
    conversation_id: int,
    messages: list[dict[str, str]],
) -> None:
    try:
        # 写回会话历史并设置 7 天 TTL，避免长期占用 Redis。
        await get_redis_client().set(
            _conversation_key(conversation_id),
            json.dumps(messages, ensure_ascii=False),
            ex=CHAT_HISTORY_TTL_SECONDS,
        )
    except Exception:
        logger.debug("Redis conversation cache write failed", exc_info=True)


async def append_cached_history(
    conversation_id: int,
    messages: list[dict[str, str]],
) -> None:
    # 只在缓存已存在时追加；缓存已过期则由下次 chat 从 MySQL 重建。
    history = await get_cached_history(conversation_id)
    if history is None:
        return
    history.extend(messages)
    await set_cached_history(conversation_id, history)


async def invalidate_conversation_history(conversation_id: int) -> None:
    try:
        # 消息被 CRUD 修改后删除该会话缓存，确保 chat 读取真实历史。
        await get_redis_client().delete(_conversation_key(conversation_id))
    except Exception:
        logger.debug("Redis conversation cache invalidation failed", exc_info=True)
