from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.messages import ToolMessage
from sqlalchemy.ext.asyncio import AsyncSession

from config.mysql_engine import get_db
from crud.mysql import (
    create_conversation,
    create_message,
    get_conversation,
)
from schemas.chat import ChatRequest, ChatResponse, Citation
from schemas.mysql import ConversationCreate, MessageCreate, MessageRole

router = APIRouter(prefix="/chat")


def _extract_answer(messages) -> str:
    for message in reversed(messages):
        if getattr(message, "type", "") == "ai" and not getattr(
            message,
            "tool_calls",
            None,
        ):
            return message.content or ""
    return ""


def _extract_citations(messages) -> list[Citation]:
    citations: dict[int, Citation] = {}
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        if getattr(message, "name", None) != "knowledge_search":
            continue
        try:
            payload = json.loads(message.content)
        except (TypeError, json.JSONDecodeError):
            continue
        for item in payload or []:
            chunk_id = item.get("chunk_id")
            document_id = item.get("document_id")
            if chunk_id is None or document_id is None:
                continue
            citations[chunk_id] = Citation(
                chunk_id=chunk_id,
                document_id=document_id,
                title=item.get("title"),
                page_no=item.get("page_no"),
            )
    return list(citations.values())


@router.post("", response_model=ChatResponse)
async def chat(
    data: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    if data.conversation_id is not None:
        conversation = await get_conversation(db, data.conversation_id)
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
        conversation_id = conversation.id
    else:
        conversation = await create_conversation(
            db,
            ConversationCreate(
                user_id=data.user_id,
                title=data.question[:50],
            ),
        )
        conversation_id = conversation.id

    await create_message(
        db,
        MessageCreate(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=data.question,
        ),
    )

    input_messages = [
        {"role": message.role, "content": message.content}
        for message in data.history
    ]
    input_messages.append({"role": "user", "content": data.question})

    try:
        from services.agent import get_agent

        result = await get_agent().ainvoke({"messages": input_messages})
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Agent failed: {exc}",
        ) from exc

    output_messages = result.get("messages", [])
    answer = _extract_answer(output_messages)
    citations = _extract_citations(output_messages)
    trace_id = uuid.uuid4().hex

    await create_message(
        db,
        MessageCreate(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=answer,
            citations=[citation.model_dump() for citation in citations],
        ),
    )
    return ChatResponse(
        answer=answer,
        citations=citations,
        trace_id=trace_id,
    )
