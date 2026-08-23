from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crud.mysql.chunks import hard_delete_chunks_by_document
from crud.mysql.common import fetch_page
from models.mysql import Document
from schemas.mysql import DocumentCreate, DocumentStatus, DocumentUpdate, SourceType


async def create_document(
    db: AsyncSession,
    data: DocumentCreate,
) -> Document:
    document = Document(**data.model_dump())
    db.add(document)
    await db.commit()
    await db.refresh(document)
    return document


async def get_document(db: AsyncSession, document_id: int) -> Document | None:
    return await db.get(Document, document_id)


async def list_documents(
    db: AsyncSession,
    *,
    status: DocumentStatus | str | None = None,
    source_type: SourceType | str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Document], int]:
    statement = select(Document).order_by(Document.id.desc())
    if status is not None:
        statement = statement.where(Document.status == status)
    if source_type is not None:
        statement = statement.where(Document.source_type == source_type)
    if keyword:
        statement = statement.where(Document.title.ilike(f"%{keyword}%"))
    return await fetch_page(db, statement, page, page_size)


async def update_document(
    db: AsyncSession,
    document_id: int,
    data: DocumentUpdate,
) -> Document | None:
    document = await db.get(Document, document_id)
    if document is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(document, field, value)
    await db.commit()
    await db.refresh(document)
    return document


async def delete_document(db: AsyncSession, document_id: int) -> None:
    document = await db.get(Document, document_id)
    if document is None:
        return
    # 文档删除时同步删除其 chunks，确保 MySQL 不残留孤儿 chunk。
    await hard_delete_chunks_by_document(db, document_id)
    await db.delete(document)
    await db.commit()
