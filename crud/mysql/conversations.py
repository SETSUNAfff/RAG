from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crud.mysql.common import fetch_page
from models.mysql import Conversation
from schemas.mysql import ConversationCreate, ConversationUpdate


async def create_conversation(
    db: AsyncSession,
    data: ConversationCreate,
) -> Conversation:
    conversation = Conversation(**data.model_dump())
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def get_conversation(
    db: AsyncSession,
    conversation_id: int,
) -> Conversation | None:
    return await db.get(Conversation, conversation_id)


async def list_conversations(
    db: AsyncSession,
    *,
    user_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Conversation], int]:
    statement = select(Conversation).order_by(Conversation.id.desc())
    if user_id is not None:
        statement = statement.where(Conversation.user_id == user_id)
    return await fetch_page(db, statement, page, page_size)


async def update_conversation(
    db: AsyncSession,
    conversation_id: int,
    data: ConversationUpdate,
) -> Conversation | None:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(conversation, field, value)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def delete_conversation(db: AsyncSession, conversation_id: int) -> None:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        return
    await db.delete(conversation)
    await db.commit()
