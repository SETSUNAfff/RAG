import asyncio
import json
from types import SimpleNamespace

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from api.v1.chat import (
    _StreamState,
    _extract_citations,
    _history_from_messages,
    _message_chunk_text,
    _produce_agent_stream,
    _sse_comment,
    _sse_event,
)


def test_sse_event_serialization() -> None:
    raw = _sse_event("token", {"content": "你好"}, "generation:1")
    lines = raw.strip().splitlines()
    assert lines[0] == "event: token"
    assert lines[1] == "id: generation:1"
    payload = json.loads(lines[2].removeprefix("data: "))
    assert payload["type"] == "token"
    assert payload["content"] == "你好"


def test_sse_heartbeat_is_a_comment() -> None:
    assert _sse_comment() == ": heartbeat\n\n"


def test_message_chunk_text_handles_content_blocks() -> None:
    class Chunk:
        content = [{"text": "答案"}, {"text": "完成"}]

    assert _message_chunk_text(Chunk()) == "答案完成"


def test_extract_citations_keeps_original_content() -> None:
    tool_message = ToolMessage(
        content=json.dumps(
            [
                {
                    "chunk_id": 1,
                    "document_id": 2,
                    "title": "制度文档",
                    "page_no": 3,
                    "content": "这是原文正文",
                }
            ],
            ensure_ascii=False,
        ),
        name="knowledge_search",
        tool_call_id="call-1",
    )

    citations = _extract_citations([tool_message])

    assert len(citations) == 1
    assert citations[0].content == "这是原文正文"


def test_history_only_uses_completed_assistant_messages() -> None:
    messages = [
        SimpleNamespace(id=1, role="user", content="问题一", status="completed"),
        SimpleNamespace(id=2, role="assistant", content="答案一", status="completed"),
        SimpleNamespace(id=3, role="user", content="问题二", status="completed"),
        SimpleNamespace(id=4, role="assistant", content="部分答案", status="failed"),
    ]

    history = _history_from_messages(messages)

    assert history == [
        {"role": "user", "content": "问题一"},
        {"role": "assistant", "content": "答案一"},
        {"role": "user", "content": "问题二"},
    ]
    assert _history_from_messages(messages, stop_before_id=3) == [
        {"role": "user", "content": "问题一"},
        {"role": "assistant", "content": "答案一"},
    ]


def test_agent_stream_ignores_pre_retrieval_model_text(monkeypatch) -> None:
    tool_message = ToolMessage(
        content="[]",
        name="knowledge_search",
        tool_call_id="call-1",
    )

    class FakeAgent:
        async def astream(self, *args, **kwargs):
            yield {
                "type": "messages",
                "data": (AIMessageChunk(content="不应输出"), {}),
            }
            yield {"type": "values", "data": {"messages": [tool_message]}}
            yield {"type": "messages", "data": (tool_message, {})}
            yield {
                "type": "messages",
                "data": (AIMessageChunk(content="最终答案"), {}),
            }
            yield {
                "type": "values",
                "data": {
                    "messages": [tool_message, AIMessage(content="最终答案")],
                },
            }

    monkeypatch.setattr("services.agent.get_agent", lambda: FakeAgent())

    async def run() -> tuple[list, _StreamState]:
        queue = asyncio.Queue()
        state = _StreamState(trace_id="trace", generation_id="generation")
        await _produce_agent_stream(queue, state, [], [1])
        items = []
        while not queue.empty():
            items.append(queue.get_nowait())
        return items, state

    items, state = asyncio.run(run())

    assert state.answer_parts == ["最终答案"]
    assert items[0][0] == "event"
    assert items[0][1][0] == "status"
    assert items[1] == ("event", ("token", {"content": "最终答案"}))
    assert items[2] == ("complete", None)
