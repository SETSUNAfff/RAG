"""Chat API with a resilient POST-based SSE stream."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import ToolMessage
from sqlalchemy.ext.asyncio import AsyncSession

from config.mysql_engine import async_session, get_db
from crud.mysql import (
    create_conversation,
    create_message,
    get_assistant_reply,
    get_conversation,
    get_message,
    list_messages,
)
from schemas.chat import ChatRequest, Citation
from schemas.mysql import (
    ConversationCreate,
    MessageCreate,
    MessageRole,
    MessageStatus,
)
from services.cache import (
    get_cached_history,
    invalidate_conversation_history,
    set_cached_history,
)
from services.context import (
    clean_agent_output,
    get_history_token_budget,
    trim_history_messages,
)

router = APIRouter(prefix="/chat")
logger = logging.getLogger(__name__)

SSE_HEARTBEAT_SECONDS = 15
CHAT_GENERATION_TIMEOUT_SECONDS = 180
SUGGESTED_QUESTIONS_TIMEOUT_SECONDS = 15


@dataclass
class _GenerationControl:
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    user_requested: bool = False


@dataclass
class _StreamState:
    trace_id: str
    generation_id: str
    answer_parts: list[str] = field(default_factory=list)
    final_state: dict[str, Any] | None = None
    retrieval_complete: bool = False
    generating_status_sent: bool = False
    sequence: int = 0
    assistant_message_id: int | None = None
    answer_saved: bool = False

    def next_event_id(self) -> str:
        self.sequence += 1
        return f"{self.generation_id}:{self.sequence}"


class _UserCancelled(Exception):
    pass


class _ClientDisconnected(Exception):
    pass


class _GenerationTimedOut(Exception):
    pass


_active_generations: dict[str, _GenerationControl] = {}


async def _generate_suggested_questions(question: str, answer: str) -> list[str]:
    """Ask the LLM for three optional follow-up questions."""
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
            timeout=SUGGESTED_QUESTIONS_TIMEOUT_SECONDS,
        )
        lines = [
            line.strip()
            for line in (response.content or "").strip().split("\n")
            if line.strip()
        ]
        cleaned: list[str] = []
        for line in lines[:3]:
            for prefix in ("1.", "2.", "3.", "1、", "2、", "3、", "- ", "· "):
                if line.startswith(prefix):
                    line = line[len(prefix):].strip()
                    break
            if line:
                cleaned.append(line)
        return cleaned[:3]
    except Exception:
        logger.debug("Suggested question generation failed", exc_info=True)
        return []


def _sse_event(
    event_type: str,
    data: dict[str, object],
    event_id: str | None = None,
) -> str:
    """Serialize one standard SSE event while retaining JSON type compatibility."""
    payload = {"type": event_type}
    payload.update(data)
    lines = [f"event: {event_type}"]
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"data: {json.dumps(payload, ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"


def _sse_comment(comment: str = "heartbeat") -> str:
    return f": {comment}\n\n"


def _message_chunk_text(chunk: Any) -> str:
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


def _extract_answer(messages: list[Any]) -> str:
    for message in reversed(messages):
        if getattr(message, "type", "") == "ai" and not getattr(
            message,
            "tool_calls",
            None,
        ):
            return _message_chunk_text(message)
    return ""


def _has_knowledge_result(messages: list[Any]) -> bool:
    return any(
        isinstance(message, ToolMessage)
        and getattr(message, "name", None) == "knowledge_search"
        for message in messages
    )


def _extract_citations(messages: list[Any]) -> list[Citation]:
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


def _history_from_messages(
    messages: list[Any],
    *,
    stop_before_id: int | None = None,
) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for message in messages:
        if stop_before_id is not None and message.id == stop_before_id:
            break
        if message.role == MessageRole.USER.value:
            history.append({"role": "user", "content": message.content})
        elif (
            message.role == MessageRole.ASSISTANT.value
            and message.status == MessageStatus.COMPLETED.value
        ):
            history.append({"role": "assistant", "content": message.content})
    return history


async def _prepare_chat(
    data: ChatRequest,
    db: AsyncSession,
) -> tuple[int, int, list[dict[str, str]], str]:
    if data.conversation_id is not None:
        conversation = await get_conversation(db, data.conversation_id)
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
        conversation_id = conversation.id
    else:
        if data.retry_user_message_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A retry requires conversation_id",
            )
        conversation = await create_conversation(
            db,
            ConversationCreate(user_id=data.user_id, title=data.question[:50]),
        )
        conversation_id = conversation.id

    if data.retry_user_message_id is not None:
        user_message = await get_message(db, data.retry_user_message_id)
        if (
            user_message is None
            or user_message.role != MessageRole.USER.value
            or user_message.conversation_id != conversation_id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Retry source message not found",
            )
        existing_reply = await get_assistant_reply(db, user_message.id)
        if (
            existing_reply is not None
            and existing_reply.status == MessageStatus.COMPLETED.value
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A completed answer cannot be retried",
            )
        stored_messages, _ = await list_messages(
            db,
            conversation_id=conversation_id,
            page=1,
            page_size=1000,
        )
        history = _history_from_messages(
            stored_messages,
            stop_before_id=user_message.id,
        )
        question = user_message.content
    else:
        history = await get_cached_history(conversation_id)
        if history is None:
            stored_messages, _ = await list_messages(
                db,
                conversation_id=conversation_id,
                page=1,
                page_size=1000,
            )
            history = _history_from_messages(stored_messages)
            await set_cached_history(conversation_id, history)

        user_message = await create_message(
            db,
            MessageCreate(
                conversation_id=conversation_id,
                role=MessageRole.USER,
                content=data.question,
            ),
        )
        await invalidate_conversation_history(conversation_id)
        question = data.question

    input_messages = trim_history_messages(history, get_history_token_budget())
    input_messages.append({"role": "user", "content": question})
    return conversation_id, user_message.id, input_messages, question


async def _save_assistant_message(
    *,
    conversation_id: int,
    user_message_id: int,
    answer: str,
    citations: list[Citation],
    message_status: MessageStatus,
    trace_id: str,
    suggested_questions: list[str] | None = None,
) -> int | None:
    if not answer and message_status != MessageStatus.COMPLETED:
        return None

    async with async_session() as db:
        message = await get_assistant_reply(db, user_message_id)
        values = {
            "content": answer,
            "citations": [citation.model_dump() for citation in citations],
            "status": message_status.value,
            "suggested_questions": suggested_questions or [],
            "trace_id": trace_id,
        }
        if message is None:
            message = await create_message(
                db,
                MessageCreate(
                    conversation_id=conversation_id,
                    role=MessageRole.ASSISTANT,
                    reply_to_message_id=user_message_id,
                    **values,
                ),
            )
        else:
            for key, value in values.items():
                setattr(message, key, value)
            await db.commit()
            await db.refresh(message)
        await invalidate_conversation_history(conversation_id)
        return message.id


async def _save_suggestions(
    assistant_message_id: int,
    conversation_id: int,
    suggestions: list[str],
) -> None:
    async with async_session() as db:
        message = await get_message(db, assistant_message_id)
        if message is None:
            return
        message.suggested_questions = suggestions
        await db.commit()
    await invalidate_conversation_history(conversation_id)


def _current_answer(state: _StreamState) -> str:
    output_messages = (state.final_state or {}).get("messages", []) or []
    return clean_agent_output("".join(state.answer_parts) or _extract_answer(output_messages))


def _current_citations(state: _StreamState) -> list[Citation]:
    output_messages = (state.final_state or {}).get("messages", []) or []
    return _extract_citations(output_messages)


async def _produce_agent_stream(
    queue: asyncio.Queue[tuple[str, Any]],
    state: _StreamState,
    input_messages: list[dict[str, str]],
    source_ids: list[int] | None,
) -> None:
    from services.agent import get_agent, reset_document_ids, set_document_ids

    document_token = set_document_ids(source_ids)
    try:
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
            if mode == "values" and isinstance(payload, dict):
                state.final_state = payload
                messages = payload.get("messages", []) or []
                if _has_knowledge_result(messages):
                    state.retrieval_complete = True
                continue
            if mode != "messages":
                continue

            token = payload[0] if isinstance(payload, tuple) and payload else payload
            if getattr(token, "type", "") not in {"ai", "AIMessageChunk"}:
                continue
            if getattr(token, "tool_calls", None) or getattr(
                token,
                "tool_call_chunks",
                None,
            ):
                continue
            content = _message_chunk_text(token)
            if not content or not state.retrieval_complete:
                continue
            if not state.generating_status_sent:
                state.generating_status_sent = True
                await queue.put(
                    (
                        "event",
                        (
                            "status",
                            {"status": "generating", "message": "正在生成回答..."},
                        ),
                    )
                )
            state.answer_parts.append(content)
            await queue.put(("event", ("token", {"content": content})))
        await queue.put(("complete", None))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        await queue.put(("error", exc))
    finally:
        reset_document_ids(document_token)


async def _persist_interrupted_answer(
    *,
    state: _StreamState,
    conversation_id: int,
    user_message_id: int,
    message_status: MessageStatus,
) -> None:
    if state.answer_saved:
        return
    try:
        state.assistant_message_id = await _save_assistant_message(
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            answer=_current_answer(state),
            citations=_current_citations(state),
            message_status=message_status,
            trace_id=state.trace_id,
        )
    except Exception:
        logger.exception(
            "Failed to persist interrupted answer trace_id=%s",
            state.trace_id,
        )


async def _stream_chat(
    *,
    request: Request,
    generation_id: str,
    trace_id: str,
    conversation_id: int,
    user_message_id: int,
    input_messages: list[dict[str, str]],
    question: str,
    source_ids: list[int] | None,
    is_retry: bool,
) -> AsyncIterator[str]:
    control = _GenerationControl()
    state = _StreamState(trace_id=trace_id, generation_id=generation_id)
    _active_generations[generation_id] = control
    producer: asyncio.Task | None = None

    try:
        yield _sse_event(
            "connected",
            {
                "generation_id": generation_id,
                "trace_id": trace_id,
                "conversation_id": conversation_id,
                "user_message_id": user_message_id,
                "retry": is_retry,
            },
            state.next_event_id(),
        )
        yield _sse_event(
            "status",
            {"status": "searching", "message": "正在检索知识库..."},
            state.next_event_id(),
        )

        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        producer = asyncio.create_task(
            _produce_agent_stream(queue, state, input_messages, source_ids)
        )
        deadline = time.monotonic() + CHAT_GENERATION_TIMEOUT_SECONDS

        while True:
            if control.cancel_event.is_set():
                raise _UserCancelled
            if await request.is_disconnected():
                raise _ClientDisconnected
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _GenerationTimedOut

            queue_wait = asyncio.create_task(queue.get())
            cancel_wait = asyncio.create_task(control.cancel_event.wait())
            done, pending = await asyncio.wait(
                {queue_wait, cancel_wait},
                timeout=min(SSE_HEARTBEAT_SECONDS, remaining),
                return_when=asyncio.FIRST_COMPLETED,
            )
            for pending_task in pending:
                pending_task.cancel()

            if cancel_wait in done and cancel_wait.result():
                if not queue_wait.done():
                    queue_wait.cancel()
                raise _UserCancelled
            if queue_wait not in done:
                yield _sse_comment()
                continue

            item_type, item_payload = queue_wait.result()
            if item_type == "complete":
                break
            if item_type == "error":
                raise item_payload
            event_type, event_data = item_payload
            yield _sse_event(event_type, event_data, state.next_event_id())

        answer = _current_answer(state)
        citations = _current_citations(state)
        state.assistant_message_id = await _save_assistant_message(
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            answer=answer,
            citations=citations,
            message_status=MessageStatus.COMPLETED,
            trace_id=trace_id,
        )
        state.answer_saved = True

        completed_payload = {
            "answer": answer,
            "citations": [citation.model_dump() for citation in citations],
            "trace_id": trace_id,
            "conversation_id": conversation_id,
            "user_message_id": user_message_id,
            "assistant_message_id": state.assistant_message_id,
            "status": MessageStatus.COMPLETED.value,
        }
        yield _sse_event(
            "citations",
            {"citations": completed_payload["citations"]},
            state.next_event_id(),
        )
        yield _sse_event(
            "answer_done",
            completed_payload,
            state.next_event_id(),
        )

        yield _sse_event(
            "status",
            {"status": "suggesting", "message": "正在生成推荐追问..."},
            state.next_event_id(),
        )
        suggestion_task = asyncio.create_task(
            _generate_suggested_questions(question, answer)
        )
        while not suggestion_task.done():
            if control.cancel_event.is_set() or await request.is_disconnected():
                suggestion_task.cancel()
                yield _sse_event(
                    "done",
                    completed_payload,
                    state.next_event_id(),
                )
                return
            try:
                await asyncio.wait_for(
                    asyncio.shield(suggestion_task),
                    timeout=SSE_HEARTBEAT_SECONDS,
                )
            except asyncio.TimeoutError:
                yield _sse_comment()

        suggestions = suggestion_task.result()
        if suggestions and state.assistant_message_id is not None:
            try:
                await _save_suggestions(
                    state.assistant_message_id,
                    conversation_id,
                    suggestions,
                )
            except Exception:
                logger.exception(
                    "Failed to persist suggestions trace_id=%s",
                    trace_id,
                )
            yield _sse_event(
                "suggestions",
                {"suggested_questions": suggestions},
                state.next_event_id(),
            )

        yield _sse_event(
            "done",
            {**completed_payload, "suggested_questions": suggestions},
            state.next_event_id(),
        )
    except _UserCancelled:
        if producer is not None:
            producer.cancel()
        if state.answer_saved:
            yield _sse_event(
                "done",
                {
                    "trace_id": trace_id,
                    "conversation_id": conversation_id,
                    "user_message_id": user_message_id,
                    "assistant_message_id": state.assistant_message_id,
                    "status": MessageStatus.COMPLETED.value,
                },
                state.next_event_id(),
            )
            return
        await _persist_interrupted_answer(
            state=state,
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            message_status=MessageStatus.CANCELLED,
        )
        yield _sse_event(
            "cancelled",
            {
                "message": "已停止生成",
                "answer": _current_answer(state),
                "trace_id": trace_id,
                "conversation_id": conversation_id,
                "user_message_id": user_message_id,
                "assistant_message_id": state.assistant_message_id,
                "status": MessageStatus.CANCELLED.value,
            },
            state.next_event_id(),
        )
        yield _sse_event(
            "done",
            {
                "trace_id": trace_id,
                "conversation_id": conversation_id,
                "user_message_id": user_message_id,
                "assistant_message_id": state.assistant_message_id,
                "status": MessageStatus.CANCELLED.value,
            },
            state.next_event_id(),
        )
    except _ClientDisconnected:
        if producer is not None:
            producer.cancel()
        await _persist_interrupted_answer(
            state=state,
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            message_status=MessageStatus.FAILED,
        )
    except (asyncio.CancelledError, GeneratorExit):
        if producer is not None:
            producer.cancel()
        interrupted_status = (
            MessageStatus.CANCELLED
            if control.user_requested
            else MessageStatus.FAILED
        )
        persist_task = asyncio.create_task(
            _persist_interrupted_answer(
                state=state,
                conversation_id=conversation_id,
                user_message_id=user_message_id,
                message_status=interrupted_status,
            )
        )
        try:
            await asyncio.shield(persist_task)
        except asyncio.CancelledError:
            pass
        raise
    except _GenerationTimedOut:
        if producer is not None:
            producer.cancel()
        await _persist_interrupted_answer(
            state=state,
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            message_status=MessageStatus.FAILED,
        )
        logger.warning("Chat generation timed out trace_id=%s", trace_id)
        yield _sse_event(
            "error",
            {
                "message": "回答生成超时，请重新生成",
                "trace_id": trace_id,
                "assistant_message_id": state.assistant_message_id,
            },
            state.next_event_id(),
        )
        yield _sse_event(
            "done",
            {
                "trace_id": trace_id,
                "conversation_id": conversation_id,
                "user_message_id": user_message_id,
                "assistant_message_id": state.assistant_message_id,
                "status": MessageStatus.FAILED.value,
            },
            state.next_event_id(),
        )
    except Exception:
        if producer is not None:
            producer.cancel()
        await _persist_interrupted_answer(
            state=state,
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            message_status=MessageStatus.FAILED,
        )
        logger.exception("Chat generation failed trace_id=%s", trace_id)
        yield _sse_event(
            "error",
            {
                "message": "回答生成失败，请稍后重新生成",
                "trace_id": trace_id,
                "assistant_message_id": state.assistant_message_id,
            },
            state.next_event_id(),
        )
        yield _sse_event(
            "done",
            {
                "trace_id": trace_id,
                "conversation_id": conversation_id,
                "user_message_id": user_message_id,
                "assistant_message_id": state.assistant_message_id,
                "status": MessageStatus.FAILED.value,
            },
            state.next_event_id(),
        )
    finally:
        _active_generations.pop(generation_id, None)
        if producer is not None and not producer.done():
            producer.cancel()


@router.post("/{generation_id}/cancel")
async def cancel_chat_generation(generation_id: str) -> dict[str, bool]:
    control = _active_generations.get(generation_id)
    if control is None:
        raise HTTPException(status_code=404, detail="Active generation not found")
    control.user_requested = True
    control.cancel_event.set()
    return {"cancelled": True}


@router.post("")
async def chat(
    data: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    conversation_id, user_message_id, input_messages, question = await _prepare_chat(
        data,
        db,
    )
    generation_id = uuid.uuid4().hex
    trace_id = uuid.uuid4().hex
    return StreamingResponse(
        _stream_chat(
            request=request,
            generation_id=generation_id,
            trace_id=trace_id,
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            input_messages=input_messages,
            question=question,
            source_ids=data.source_ids,
            is_retry=data.retry_user_message_id is not None,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
