from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from config.mysql_engine import get_db
from crud.mysql.evaluations import (
    create_evaluation_case,
    create_evaluation_run,
    delete_evaluation_case,
    get_evaluation_case,
    get_evaluation_run,
    list_evaluation_cases,
    list_evaluation_results,
    list_evaluation_runs,
    update_evaluation_case,
)
from schemas.common import Page
from schemas.evaluation import CaseImportRequest, EvaluationRunRequest, ImportResult
from schemas.mysql import (
    EvaluationCaseCreate,
    EvaluationCaseRead,
    EvaluationCaseUpdate,
    EvaluationRunRead,
    EvaluationRunResultRead,
)
from services.evaluation import import_cases, run_evaluation_task

router = APIRouter(prefix="/evaluations")


@router.get("/cases", response_model=Page[EvaluationCaseRead])
async def read_evaluation_cases(
    db: AsyncSession = Depends(get_db),
    keyword: str | None = Query(default=None),
    chapter: str | None = Query(default=None),
    difficulty: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[EvaluationCaseRead]:
    items, total = await list_evaluation_cases(
        db,
        keyword=keyword,
        chapter=chapter,
        difficulty=difficulty,
        page=page,
        page_size=page_size,
    )
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.post("/cases", response_model=EvaluationCaseRead, status_code=201)
async def create_evaluation_case_route(
    data: EvaluationCaseCreate,
    db: AsyncSession = Depends(get_db),
) -> EvaluationCaseRead:
    return await create_evaluation_case(db, data)


@router.patch("/cases/{case_id}", response_model=EvaluationCaseRead)
async def update_evaluation_case_route(
    case_id: int,
    data: EvaluationCaseUpdate,
    db: AsyncSession = Depends(get_db),
) -> EvaluationCaseRead:
    case = await update_evaluation_case(db, case_id, data)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.delete("/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_evaluation_case_route(
    case_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    if await get_evaluation_case(db, case_id) is None:
        raise HTTPException(status_code=404, detail="Case not found")
    await delete_evaluation_case(db, case_id)


@router.post("/cases/import", response_model=ImportResult)
async def import_evaluation_cases(
    data: CaseImportRequest,
    db: AsyncSession = Depends(get_db),
) -> ImportResult:
    return await import_cases(db, data.cases, replace=data.replace)


@router.post("/runs", response_model=EvaluationRunRead, status_code=201)
async def create_evaluation_run_route(
    data: EvaluationRunRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> EvaluationRunRead:
    name = data.name or datetime.now().strftime("评测 %Y-%m-%d %H:%M")
    run = await create_evaluation_run(db, name)
    background_tasks.add_task(run_evaluation_task, run.id, data.case_ids)
    return run


@router.get("/runs", response_model=Page[EvaluationRunRead])
async def read_evaluation_runs(
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[EvaluationRunRead]:
    items, total = await list_evaluation_runs(db, page=page, page_size=page_size)
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/runs/{run_id}", response_model=EvaluationRunRead)
async def read_evaluation_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
) -> EvaluationRunRead:
    run = await get_evaluation_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/runs/{run_id}/results", response_model=Page[EvaluationRunResultRead])
async def read_evaluation_run_results(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> Page[EvaluationRunResultRead]:
    if await get_evaluation_run(db, run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    items, total = await list_evaluation_results(
        db, run_id, page=page, page_size=page_size
    )
    return Page(items=items, total=total, page=page, page_size=page_size)
