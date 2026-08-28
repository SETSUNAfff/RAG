from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from crud.mysql.common import fetch_page
from models.mysql import EvaluationCase, EvaluationRun, EvaluationRunResult
from schemas.mysql import EvaluationCaseCreate, EvaluationCaseUpdate


async def list_evaluation_cases(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    chapter: str | None = None,
    difficulty: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[EvaluationCase], int]:
    statement = select(EvaluationCase).order_by(EvaluationCase.id.asc())
    if keyword:
        statement = statement.where(EvaluationCase.question.ilike(f"%{keyword}%"))
    if chapter:
        statement = statement.where(EvaluationCase.chapter == chapter)
    if difficulty:
        statement = statement.where(EvaluationCase.difficulty == difficulty)
    return await fetch_page(db, statement, page, page_size)


async def get_evaluation_case(
    db: AsyncSession,
    case_id: int,
) -> EvaluationCase | None:
    return await db.get(EvaluationCase, case_id)


async def get_evaluation_case_by_external_id(
    db: AsyncSession,
    external_id: str,
) -> EvaluationCase | None:
    statement = select(EvaluationCase).where(
        EvaluationCase.external_id == external_id
    )
    return (await db.execute(statement)).scalar_one_or_none()


async def create_evaluation_case(
    db: AsyncSession,
    data: EvaluationCaseCreate,
) -> EvaluationCase:
    case = EvaluationCase(**data.model_dump())
    db.add(case)
    await db.commit()
    await db.refresh(case)
    return case


async def update_evaluation_case(
    db: AsyncSession,
    case_id: int,
    data: EvaluationCaseUpdate,
) -> EvaluationCase | None:
    case = await db.get(EvaluationCase, case_id)
    if case is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(case, field, value)
    await db.commit()
    await db.refresh(case)
    return case


async def delete_evaluation_case(db: AsyncSession, case_id: int) -> None:
    case = await db.get(EvaluationCase, case_id)
    if case is None:
        return
    await db.delete(case)
    await db.commit()


async def clear_evaluation_cases(db: AsyncSession) -> None:
    await db.execute(delete(EvaluationRunResult))
    await db.execute(delete(EvaluationCase))
    await db.commit()


async def create_evaluation_run(
    db: AsyncSession,
    name: str,
) -> EvaluationRun:
    run = EvaluationRun(name=name)
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def get_evaluation_run(
    db: AsyncSession,
    run_id: int,
) -> EvaluationRun | None:
    return await db.get(EvaluationRun, run_id)


async def list_evaluation_runs(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[EvaluationRun], int]:
    statement = select(EvaluationRun).order_by(EvaluationRun.id.desc())
    return await fetch_page(db, statement, page, page_size)


async def update_evaluation_run(
    db: AsyncSession,
    run_id: int,
    fields: dict,
) -> EvaluationRun | None:
    run = await db.get(EvaluationRun, run_id)
    if run is None:
        return None
    for field, value in fields.items():
        setattr(run, field, value)
    await db.commit()
    await db.refresh(run)
    return run


async def create_evaluation_result(
    db: AsyncSession,
    fields: dict,
) -> EvaluationRunResult:
    result = EvaluationRunResult(**fields)
    db.add(result)
    await db.commit()
    await db.refresh(result)
    return result


async def list_evaluation_results(
    db: AsyncSession,
    run_id: int,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[EvaluationRunResult], int]:
    statement = (
        select(EvaluationRunResult)
        .where(EvaluationRunResult.run_id == run_id)
        .order_by(EvaluationRunResult.id.asc())
    )
    return await fetch_page(db, statement, page, page_size)
