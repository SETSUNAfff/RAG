from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from crud.mysql.common import fetch_page
from models.mysql import Chunk, Document
from schemas.mysql import ChunkCreate, ChunkUpdate

def _orm_values(data: ChunkCreate | ChunkUpdate) -> dict:
    values = data.model_dump(exclude_unset=True)
    if "metadata" in values:
        values["meta"] = values.pop("metadata")
    return values


async def create_chunk(db: AsyncSession, data: ChunkCreate) -> Chunk:
    chunk = Chunk(**_orm_values(data))
    db.add(chunk)
    await db.commit()
    await db.refresh(chunk)
    return chunk


async def create_chunks(
    db: AsyncSession,
    data: list[ChunkCreate],
) -> list[Chunk]:
    """Bulk-create chunks and flush to obtain MySQL IDs without committing."""
    chunks = [Chunk(**_orm_values(item)) for item in data]
    db.add_all(chunks)
    await db.flush()
    return chunks


async def get_chunk(db: AsyncSession, chunk_id: int) -> Chunk | None:
    return await db.get(Chunk, chunk_id)


async def list_chunks(
    db: AsyncSession,
    *,
    document_id: int | None = None,
    is_active: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Chunk], int]:
    statement = select(Chunk).order_by(Chunk.id.desc())
    if document_id is not None:
        statement = statement.where(Chunk.document_id == document_id)
    if is_active is not None:
        statement = statement.where(Chunk.is_active == is_active)
    return await fetch_page(db, statement, page, page_size)


async def get_chunk_details_by_ids(
    db: AsyncSession,
    chunk_ids: list[int],
) -> list[tuple[Chunk, str]]:
    """Return active chunk rows joined with their document title."""
    if not chunk_ids:
        return []
    statement = (
        select(Chunk, Document.title)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.id.in_(chunk_ids), Chunk.is_active.is_(True))
    )
    return list((await db.execute(statement)).all())


async def update_chunk(
    db: AsyncSession,
    chunk_id: int,
    data: ChunkUpdate,
) -> Chunk | None:
    chunk = await db.get(Chunk, chunk_id)
    if chunk is None:
        return None
    for field, value in _orm_values(data).items():
        setattr(chunk, field, value)
    await db.commit()
    await db.refresh(chunk)
    return chunk


async def delete_chunk(db: AsyncSession, chunk_id: int) -> None:
    chunk = await db.get(Chunk, chunk_id)
    if chunk is None:
        return
    await db.delete(chunk)
    await db.commit()


async def hard_delete_chunks_by_document(
    db: AsyncSession,
    document_id: int,
) -> None:
    """Delete all chunks for a document inside the caller's transaction."""
    await db.execute(delete(Chunk).where(Chunk.document_id == document_id))
