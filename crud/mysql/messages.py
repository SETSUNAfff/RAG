from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crud.mysql.common import fetch_page
from models.mysql import Message
from schemas.mysql import MessageCreate, MessageUpdate


async def create_message(db: AsyncSession, data: MessageCreate) -> Message:
    message = Message(**data.model_dump())
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def get_message(db: AsyncSession, message_id: int) -> Message | None:
    return await db.get(Message, message_id)


async def list_messages(
    db: AsyncSession,
    *,
    conversation_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Message], int]:
    statement = select(Message).order_by(
        Message.created_at.asc(),
        Message.id.asc(),
    )
    if conversation_id is not None:
        statement = statement.where(Message.conversation_id == conversation_id)
    return await fetch_page(db, statement, page, page_size)


async def update_message(
    db: AsyncSession,
    message_id: int,
    data: MessageUpdate,
) -> Message | None:
    message = await db.get(Message, message_id)
    if message is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(message, field, value)
    await db.commit()
    await db.refresh(message)
    return message


async def delete_message(db: AsyncSession, message_id: int) -> None:
    message = await db.get(Message, message_id)
    if message is None:
        return
    await db.delete(message)
    await db.commit()
