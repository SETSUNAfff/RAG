import json

from langchain_core.messages import ToolMessage

from api.v1.chat import _extract_citations, _message_chunk_text, _sse_event


def test_sse_event_serialization() -> None:
    raw = _sse_event("token", {"content": "你好"})
    payload = json.loads(raw.removeprefix("data: ").strip())
    assert payload["type"] == "token"
    assert payload["content"] == "你好"


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
