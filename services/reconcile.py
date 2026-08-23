from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from sqlalchemy import select, update

from config.mysql_engine import async_session
from config.redis import get_redis_client
from crud.milvus.knowledge_chunks import (
    delete_chunks_by_ids,
    list_milvus_chunk_ids,
)
from models.mysql import Chunk, Document
from schemas.mysql import DocumentStatus
from services.locks import ingestion_lock

RECONCILE_TASK_TTL_SECONDS = 60 * 60
_TASK_KEY = "rag:reconcile:task:{}"
_RUNNING_KEY = "rag:reconcile:running"


async def get_running_task_id() -> str | None:
    return await get_redis_client().get(_RUNNING_KEY)


async def create_reconcile_task() -> str:
    redis = get_redis_client()
    task_id = uuid.uuid4().hex
    await redis.set(
        _TASK_KEY.format(task_id),
        json.dumps(
            {"task_id": task_id, "status": "running"},
            ensure_ascii=False,
        ),
        ex=RECONCILE_TASK_TTL_SECONDS,
    )
    await redis.set(
        _RUNNING_KEY,
        task_id,
        ex=RECONCILE_TASK_TTL_SECONDS,
    )
    return task_id


async def get_reconcile_task(task_id: str) -> dict | None:
    raw = await get_redis_client().get(_TASK_KEY.format(task_id))
    if raw is None:
        return None
    return json.loads(raw)


async def _finish_reconcile_task(
    task_id: str,
    *,
    status: str,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    redis = get_redis_client()
    payload: dict[str, Any] = {"task_id": task_id, "status": status}
    if result is not None:
        payload["result"] = result
    if error is not None:
        payload["error"] = error
    await redis.set(
        _TASK_KEY.format(task_id),
        json.dumps(payload, ensure_ascii=False),
        ex=RECONCILE_TASK_TTL_SECONDS,
    )
    current = await redis.get(_RUNNING_KEY)
    if current == task_id:
        await redis.delete(_RUNNING_KEY)


async def _mark_documents_failed(
    db,
    document_ids: list[int],
    message: str,
) -> None:
    if not document_ids:
        return
    await db.execute(
        update(Document)
        .where(Document.id.in_(document_ids))
        .values(
            status=DocumentStatus.FAILED.value,
            error_message=message,
        )
    )


async def _run_reconcile() -> dict[str, Any]:
    async with ingestion_lock:
        # Milvus 查询是同步阻塞调用，放到线程池避免卡住事件循环。
        milvus_rows = await asyncio.to_thread(list_milvus_chunk_ids)
        milvus_ids = {
            int(row.get("chunk_id", row.get("id")))
            for row in milvus_rows
        }

        async with async_session() as db:
            chunk_rows = (
                await db.execute(
                    select(Chunk.id, Chunk.document_id, Chunk.is_active)
                )
            ).all()
            doc_rows = (
                await db.execute(select(Document.id, Document.status))
            ).all()

            mysql_active_ids: set[int] = set()
            chunks_by_doc: dict[int, set[int]] = {}
            for chunk_id, document_id, is_active in chunk_rows:
                if is_active:
                    mysql_active_ids.add(chunk_id)
                    chunks_by_doc.setdefault(document_id, set()).add(chunk_id)

            doc_status = {doc_id: status for doc_id, status in doc_rows}

            # A. 正向孤儿：Milvus 有、MySQL 没有 active chunk。
            orphan_ids = list(milvus_ids - mysql_active_ids)

            # B. 反向缺失 + 卡住的 pending 空文档。
            missing_doc_ids: list[int] = []
            stuck_doc_ids: list[int] = []
            for doc_id, status in doc_status.items():
                if status == DocumentStatus.READY.value:
                    chunk_set = chunks_by_doc.get(doc_id, set())
                    if chunk_set and not chunk_set.issubset(milvus_ids):
                        missing_doc_ids.append(doc_id)
                elif status in (
                    DocumentStatus.PENDING.value,
                    DocumentStatus.PROCESSING.value,
                ):
                    if not chunks_by_doc.get(doc_id):
                        stuck_doc_ids.append(doc_id)

            if missing_doc_ids:
                await _mark_documents_failed(
                    db,
                    missing_doc_ids,
                    "向量索引缺失，请重新上传文档",
                )
            if stuck_doc_ids:
                await _mark_documents_failed(
                    db,
                    stuck_doc_ids,
                    "入库中断，请重新上传文档",
                )
            await db.commit()

        # 分批删除 Milvus 孤儿向量。
        deleted_count = 0
        batch_size = 500
        for index in range(0, len(orphan_ids), batch_size):
            batch = orphan_ids[index:index + batch_size]
            result = await asyncio.to_thread(delete_chunks_by_ids, batch)
            if isinstance(result, dict):
                deleted_count += int(result.get("delete_count", 0) or 0)
            else:
                deleted_count += len(batch)

        affected_documents = list(set(missing_doc_ids + stuck_doc_ids))
        return {
            "orphan_chunks_deleted": deleted_count,
            "missing_documents_failed": len(missing_doc_ids),
            "stuck_documents_failed": len(stuck_doc_ids),
            "affected_documents": affected_documents,
        }


async def run_reconcile_task(task_id: str) -> None:
    try:
        result = await _run_reconcile()
        await _finish_reconcile_task(
            task_id,
            status="done",
            result=result,
        )
    except Exception as exc:
        await _finish_reconcile_task(
            task_id,
            status="failed",
            error=str(exc),
        )
