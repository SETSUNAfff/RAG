from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from config.mysql_engine import get_db
from crud.mysql import (
    create_message,
    delete_message,
    get_message,
    list_messages,
    update_message,
)
from schemas.common import Page
from schemas.mysql import MessageCreate, MessageRead, MessageUpdate
from services.cache import invalidate_conversation_history

# 消息 CRUD 路由；可按 conversation_id 查询某个会话的消息列表。
router = APIRouter(prefix="/messages")


@router.get("", response_model=Page[MessageRead])
async def read_messages(
    db: AsyncSession = Depends(get_db),
    conversation_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[MessageRead]:
    items, total = await list_messages(
        db,
        conversation_id=conversation_id,
        page=page,
        page_size=page_size,
    )
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
async def create_new_message(
    data: MessageCreate,
    db: AsyncSession = Depends(get_db),
) -> MessageRead:
    message = await create_message(db, data)
    # 直接新增消息后清空该会话的 Redis 历史缓存，避免 chat 读到旧上下文。
    await invalidate_conversation_history(message.conversation_id)
    return message


@router.get("/{message_id}", response_model=MessageRead)
async def read_message(
    message_id: int,
    db: AsyncSession = Depends(get_db),
) -> MessageRead:
    message = await get_message(db, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return message


@router.patch("/{message_id}", response_model=MessageRead)
async def update_existing_message(
    message_id: int,
    data: MessageUpdate,
    db: AsyncSession = Depends(get_db),
) -> MessageRead:
    message = await update_message(db, message_id, data)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    # 消息内容变化后清空 Redis 历史缓存。
    await invalidate_conversation_history(message.conversation_id)
    return message


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_message(
    message_id: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    message = await get_message(db, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    await delete_message(db, message_id)
    # 删除消息后清空 Redis 历史缓存，保证 chat 上下文与数据库一致。
    await invalidate_conversation_history(message.conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
