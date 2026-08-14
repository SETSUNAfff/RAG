from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select


def normalize_page(page: int, page_size: int) -> tuple[int, int]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    return page, page_size


async def fetch_page(
    session: AsyncSession,
    statement: Select[Any],
    page: int,
    page_size: int,
) -> tuple[list[Any], int]:
    page, page_size = normalize_page(page, page_size)
    count_statement = select(func.count()).select_from(
        statement.order_by(None).subquery()
    )
    total = await session.scalar(count_statement) or 0
    rows = list(
        (
            await session.scalars(
                statement.offset((page - 1) * page_size).limit(page_size)
            )
        ).all()
    )
    return rows, total
