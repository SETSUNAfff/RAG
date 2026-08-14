from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from config.mysql_engine import get_db
from crud.mysql import (
    create_conversation,
    delete_conversation,
    get_conversation,
    list_conversations,
    update_conversation,
)
from schemas.common import Page
from schemas.mysql import ConversationCreate, ConversationRead, ConversationUpdate

# 会话 CRUD 路由；消息记录通过 /messages 单独管理。
router = APIRouter(prefix="/conversations")


@router.get("", response_model=Page[ConversationRead])
async def read_conversations(
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[ConversationRead]:
    items, total = await list_conversations(
        db,
        user_id=user_id,
        page=page,
        page_size=page_size,
    )
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
async def create_new_conversation(
    data: ConversationCreate,
    db: AsyncSession = Depends(get_db),
) -> ConversationRead:
    return await create_conversation(db, data)


@router.get("/{conversation_id}", response_model=ConversationRead)
async def read_conversation(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
) -> ConversationRead:
    conversation = await get_conversation(db, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.patch("/{conversation_id}", response_model=ConversationRead)
async def update_existing_conversation(
    conversation_id: int,
    data: ConversationUpdate,
    db: AsyncSession = Depends(get_db),
) -> ConversationRead:
    conversation = await update_conversation(db, conversation_id, data)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_conversation(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    if await get_conversation(db, conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await delete_conversation(db, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
