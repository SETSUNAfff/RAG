from __future__ import annotations

import json
import os
import re


def estimate_tokens(text: str) -> int:
    """Heuristic token count: Chinese chars ~1 token, ASCII ~4 chars per token."""
    cjk_count = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    other_count = len(text) - cjk_count
    return cjk_count + (other_count + 3) // 4


def estimate_message_tokens(message: dict[str, str]) -> int:
    return estimate_tokens(message.get("content", "")) + 4


def estimate_messages_tokens(messages: list[dict[str, str]]) -> int:
    return sum(estimate_message_tokens(message) for message in messages)


def _is_retrieval_json_array(raw: str) -> bool:
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return False
    return (
        isinstance(data, list)
        and bool(data)
        and all(
            isinstance(item, dict)
            and "chunk_id" in item
            and "content" in item
            for item in data
        )
    )


def _strip_all_retrieval_json(text: str) -> str:
    """Remove retrieval JSON arrays that appear anywhere in the text.

    The agent sometimes pastes knowledge_search results in the middle of
    its answer, not just at the beginning.  Scan the whole string and
    drop every JSON array that looks like a chunk list.
    """
    decoder = json.JSONDecoder()
    result: list[str] = []
    pos = 0
    while pos < len(text):
        bracket = text.find("[", pos)
        if bracket == -1:
            result.append(text[pos:])
            break
        result.append(text[pos:bracket])
        try:
            _, end = decoder.raw_decode(text, bracket)
        except json.JSONDecodeError:
            result.append("[")
            pos = bracket + 1
            continue
        segment = text[bracket:end]
        if _is_retrieval_json_array(segment):
            pos = end
        else:
            result.append(segment)
            pos = end
    return "".join(result)


def clean_agent_output(text: str) -> str:
    """Normalize generated answer text while preserving code blocks."""
    if not text:
        return ""
    text = _strip_all_retrieval_json(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u200b", "").replace("\ufeff", "")

    in_code = False
    cleaned_lines: list[str] = []
    blank_count = 0
    for line in text.split("\n"):
        stripped = line.rstrip()
        if stripped.startswith("```"):
            in_code = not in_code
            cleaned_lines.append(stripped)
            blank_count = 0
            continue
        if not in_code and not stripped.strip():
            blank_count += 1
            if blank_count <= 1:
                cleaned_lines.append("")
            continue
        blank_count = 0
        cleaned_lines.append(stripped)
    return "\n".join(cleaned_lines).strip()


def _group_turns(messages: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    turns: list[list[dict[str, str]]] = []
    current: list[dict[str, str]] = []
    for message in messages:
        current.append(message)
        if message.get("role") == "assistant":
            turns.append(current)
            current = []
    if current:
        turns.append(current)
    return turns


def trim_history_messages(
    messages: list[dict[str, str]],
    budget: int,
) -> list[dict[str, str]]:
    """Keep the latest complete user/assistant turns within the token budget."""
    if budget <= 0 or not messages:
        return []

    turns = _group_turns(messages)
    selected: list[list[dict[str, str]]] = []
    total = 0

    for turn in reversed(turns):
        turn_cost = estimate_messages_tokens(turn)
        if selected and total + turn_cost > budget:
            break
        if not selected and total + turn_cost > budget:
            # 即使最新一轮超预算也保留，保证至少有一轮上下文。
            selected.append(turn)
            break
        selected.append(turn)
        total += turn_cost

    return [message for turn in reversed(selected) for message in turn]


def get_history_token_budget() -> int:
    return int(os.getenv("CHAT_HISTORY_TOKEN_BUDGET", "4000"))
