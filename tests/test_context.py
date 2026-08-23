from services.context import clean_agent_output, estimate_tokens, trim_history_messages


def test_estimate_tokens_chinese_and_ascii() -> None:
    assert estimate_tokens("你好") == 2
    assert estimate_tokens("hello") == 2


def test_trim_history_drops_oldest_turn_within_budget() -> None:
    messages = [
        {"role": "user", "content": "a" * 100},
        {"role": "assistant", "content": "b" * 100},
        {"role": "user", "content": "c" * 100},
        {"role": "assistant", "content": "d" * 100},
    ]

    trimmed = trim_history_messages(messages, budget=80)

    assert trimmed == messages[2:]


def test_trim_history_keeps_latest_turn_when_over_budget() -> None:
    messages = [
        {"role": "user", "content": "x" * 1000},
        {"role": "assistant", "content": "y" * 1000},
    ]

    trimmed = trim_history_messages(messages, budget=10)

    assert trimmed == messages


def test_trim_history_empty_returns_empty_list() -> None:
    assert trim_history_messages([], budget=4000) == []


def test_clean_agent_output_normalizes_formatting_and_keeps_code() -> None:
    raw = "\ufeff第一行  \r\n\r\n\r\n第二行\r\n```\ncode\n\n\ncode\n```\r\n"

    cleaned = clean_agent_output(raw)

    assert "\r" not in cleaned
    assert "\u200b" not in cleaned
    assert "第一行" in cleaned
    assert "```" in cleaned
    assert "code" in cleaned


def test_clean_agent_output_strips_leading_retrieval_json() -> None:
    raw = (
        '[{"chunk_id": 79, "document_id": 44, "title": "knowledge.txt", '
        '"page_no": 0, "content": "退款规则原文"}'
        '][{"chunk_id": 75, "document_id": 44, "title": "knowledge.txt", '
        '"page_no": 0, "content": "补充说明原文"}]'
        "根据知识库内容，退款申请被拒的常见原因如下。"
    )

    cleaned = clean_agent_output(raw)

    assert cleaned.startswith("根据知识库内容")
    assert "chunk_id" not in cleaned


def test_clean_agent_output_strips_mid_text_retrieval_json() -> None:
    raw = (
        "你好！我是企业知识库助手。"
        '[{"chunk_id": 79, "document_id": 44, "title": "k.txt", '
        '"page_no": 0, "content": "退款规则"}]'
        "根据知识库内容，回答如下。"
    )
    cleaned = clean_agent_output(raw)
    assert "chunk_id" not in cleaned
    assert "退款规则" not in cleaned
    assert cleaned.startswith("你好！我是企业知识库助手。")
    assert "根据知识库内容，回答如下。" in cleaned
