from __future__ import annotations

import os
from functools import lru_cache

from redis.asyncio import Redis


@lru_cache(maxsize=1)
def get_redis_client() -> Redis:
    # Redis 客户端懒加载单例，URL 从 .env 的 REDIS_URL 读取。
    return Redis.from_url(
        os.getenv("REDIS_URL"),
        decode_responses=True,
    )
