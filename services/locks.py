from __future__ import annotations

import asyncio

# 上传入库与对账任务共用，保证同一时间只有一个在改 MySQL/Milvus 数据。
ingestion_lock = asyncio.Lock()
