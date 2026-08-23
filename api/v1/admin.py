from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, status

from services.reconcile import (
    create_reconcile_task,
    get_reconcile_task,
    get_running_task_id,
    run_reconcile_task,
)

router = APIRouter(prefix="/admin")


@router.post("/reconcile")
async def start_reconcile() -> dict:
    existing = await get_running_task_id()
    if existing is not None:
        return {"task_id": existing, "status": "running", "reused": True}

    task_id = await create_reconcile_task()
    asyncio.create_task(run_reconcile_task(task_id))
    return {"task_id": task_id, "status": "running"}


@router.get("/reconcile/{task_id}")
async def read_reconcile_status(task_id: str) -> dict:
    task = await get_reconcile_task(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reconcile task not found",
        )
    return task
