"""
聊天路由：SSE 流式接口。

核心流程：
1. 前端 POST /api/v1/chat。
2. _prepare_chat 准备会话、历史消息、上下文输入。
3. 返回 StreamingResponse，流式执行 Agent。
4. _stream_chat 推送 connected/status/token/citations/done/suggestions/error 事件。
5. 将 user 消息在流开始前落库，assistant 答案在流结束后落库。
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import ToolMessage
from sqlalchemy.ext.asyncio import AsyncSession

from config.mysql_engine import get_db
from crud.mysql import (
    create_conversation,
    create_message,
    get_conversation,
    list_messages,
)
from schemas.chat import ChatRequest, Citation
from schemas.mysql import ConversationCreate, MessageCreate, MessageRole
from services.cache import (
    append_cached_history,
    get_cached_history,
    set_cached_history,
)
from services.context import (
    clean_agent_output,
    get_history_token_budget,
    trim_history_messages,
)

router = APIRouter(prefix="/chat")

# 推荐追问生成的超时时间，超时后返回空列表，不阻塞主流程。
_SUGGESTED_QUESTIONS_TIMEOUT = 15


async def _generate_suggested_questions(question: str, answer: str) -> list[str]:
    """Ask the LLM to generate 3 follow-up questions based on Q&A."""
    try:
        from langchain.chat_models import init_chat_model

        model = init_chat_model(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            model=os.getenv("DEEPSEEK_MODEL"),
            base_url=os.getenv("DEEPSEEK_BASE_URL"),
        )
        prompt = (
            "根据以下用户问题和助手回答，生成3个用户可能想追问的问题。"
            "每行一个问题，不要编号，不要其他内容。\n\n"
            f"用户问题：{question}\n\n"
            f"助手回答：{answer[:500]}\n\n"
            "追问问题："
        )
        response = await asyncio.wait_for(
            model.ainvoke(prompt),
            timeout=_SUGGESTED_QUESTIONS_TIMEOUT,
        )
        lines = [
            line.strip()
            for line in (response.content or "").strip().split("\n")
            if line.strip()
        ]
        cleaned = []
        for line in lines[:3]:
            for prefix in ("1.", "2.", "3.", "1、", "2、", "3、", "- ", "· "):
                if line.startswith(prefix):
                    line = line[len(prefix):].strip()
                    break
            if line:
                cleaned.append(line)
        return cleaned[:3]
    except Exception:
        return []


def _sse_event(event_type: str, data: dict[str, object]) -> str:
    payload = {"type": event_type}
    payload.update(data)
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _message_chunk_text(chunk) -> str:
    if chunk is None:
        return ""
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return ""


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
                content=item.get("content"),
            )
    return list(citations.values())


async def _prepare_chat(
    data: ChatRequest,
    db: AsyncSession,
) -> tuple[int, list[dict[str, str]], str]:
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

    # Redis 缓存历史 -> MySQL 回填
    history = await get_cached_history(conversation_id)
    if history is None:
        stored_messages, _ = await list_messages(
            db,
            conversation_id=conversation_id,
            page=1,
            page_size=100,
        )
        history = [
            {"role": message.role, "content": message.content}
            for message in stored_messages
            if message.role in {"user", "assistant"}
        ]
        await set_cached_history(conversation_id, history)

    await create_message(
        db,
        MessageCreate(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=data.question,
        ),
    )

    input_messages = trim_history_messages(
        history,
        get_history_token_budget(),
    )
    input_messages.append({"role": "user", "content": data.question})
    return conversation_id, input_messages, data.question


async def _stream_chat(
    conversation_id: int,
    input_messages: list[dict[str, str]],
    question: str,
    source_ids: list[int] | None,
    db: AsyncSession,
) -> AsyncIterator[str]:
    yield _sse_event("connected", {"conversation_id": conversation_id})
    yield _sse_event(
        "status",
        {"status": "searching", "message": "正在检索知识库..."},
    )

    answer_parts: list[str] = []
    final_state: dict | None = None
    try:
        from services.agent import get_agent, set_document_ids

        set_document_ids(source_ids)
        agent = get_agent()
        async for stream_part in agent.astream(
            {"messages": input_messages},
            stream_mode=["messages", "values"],
            version="v2",
        ):
            if not isinstance(stream_part, dict):
                continue
            mode = stream_part.get("type")
            payload = stream_part.get("data")
            if mode == "messages":
                token = (
                    payload[0]
                    if isinstance(payload, tuple) and payload
                    else payload
                )
                content = _message_chunk_text(token)
                if content:
                    if not answer_parts:
                        yield _sse_event(
                            "status",
                            {"status": "generating", "message": "正在生成回答..."},
                        )
                    answer_parts.append(content)
                    yield _sse_event("token", {"content": content})
            elif mode == "values":
                final_state = payload if isinstance(payload, dict) else None
    except Exception as exc:
        yield _sse_event("error", {"message": f"Agent failed: {exc}"})
        return

    output_messages = (final_state or {}).get("messages", []) or []
    answer = "".join(answer_parts) or _extract_answer(output_messages)
    # 清洗答案：去掉检索 JSON、统一换行、压缩多余空行
    answer = clean_agent_output(answer)
    citations = _extract_citations(output_messages)
    trace_id = uuid.uuid4().hex

    # 保存到数据库；失败时不阻断回答交付
    save_error = None
    try:
        await create_message(
            db,
            MessageCreate(
                conversation_id=conversation_id,
                role=MessageRole.ASSISTANT,
                content=answer,
                citations=[citation.model_dump() for citation in citations],
            ),
        )
        await append_cached_history(
            conversation_id,
            [
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer},
            ],
        )
    except Exception as exc:
        save_error = str(exc)

    # 先推送 citations 和 done，让前端立即拿到清洗后的答案
    yield _sse_event(
        "citations",
        {"citations": [citation.model_dump() for citation in citations]},
    )
    yield _sse_event(
        "done",
        {
            "answer": answer,
            "citations": [citation.model_dump() for citation in citations],
            "trace_id": trace_id,
            "conversation_id": conversation_id,
            "save_error": save_error,
            "suggested_questions": [],
        },
    )

    # done 之后异步生成推荐追问，通过单独事件推送
    suggested = await _generate_suggested_questions(question, answer)
    if suggested:
        yield _sse_event("suggestions", {"suggested_questions": suggested})


@router.post("")
async def chat(
    data: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    conversation_id, input_messages, question = await _prepare_chat(data, db)
    return StreamingResponse(
        _stream_chat(conversation_id, input_messages, question, data.source_ids, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
