from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.tools import tool

from config.mysql_engine import async_session
from services.retrieval import hybrid_search

load_dotenv(override=True)

_agent = None


_current_document_ids: list[int] | None = None

_RETRIEVAL_FILTER_ENABLED = os.getenv(
    "RETRIEVAL_FILTER_ENABLED",
    "false",
).lower() in {"1", "true", "yes"}
_RETRIEVAL_FILTER_MIN_RATIO = float(
    os.getenv("RETRIEVAL_FILTER_MIN_RATIO", "0.7")
)
_RETRIEVAL_MAX_EVIDENCE_PER_CALL = int(
    os.getenv("RETRIEVAL_MAX_EVIDENCE_PER_CALL", "3")
)


def set_document_ids(document_ids: list[int] | None) -> None:
    """Set the document filter for the next knowledge_search call."""
    global _current_document_ids
    _current_document_ids = document_ids


def _filter_evidence(results):
    if not _RETRIEVAL_FILTER_ENABLED:
        return results

    ranked = sorted(
        results,
        key=lambda item: item.rerank_score
        if item.rerank_score is not None
        else -float("inf"),
        reverse=True,
    )
    if not ranked:
        return []

    max_score = ranked[0].rerank_score
    if max_score is None or max_score == 0.0:
        return ranked[: _RETRIEVAL_MAX_EVIDENCE_PER_CALL]

    kept: list = []
    for result in ranked:
        if not kept:
            kept.append(result)
        elif (
            result.rerank_score is not None
            and result.rerank_score >= max_score * _RETRIEVAL_FILTER_MIN_RATIO
        ):
            kept.append(result)
        if len(kept) >= _RETRIEVAL_MAX_EVIDENCE_PER_CALL:
            break
    return kept


@tool
async def knowledge_search(query: str) -> str:
    """从企业知识库检索与问题相关的证据，返回带引用字段和正文的结果。"""
    async with async_session() as db:
        results = _filter_evidence(await hybrid_search(
            db, query, top_k=5, document_ids=_current_document_ids
        ))
    return json.dumps(
        [result.to_tool_dict() for result in results],
        ensure_ascii=False,
    )


def get_agent():
    global _agent
    if _agent is None:
        model = init_chat_model(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            model=os.getenv("DEEPSEEK_MODEL"),
            base_url=os.getenv("DEEPSEEK_BASE_URL"),
        )
        _agent = create_agent(
            model=model,
            tools=[knowledge_search],
            system_prompt=(
                "你是一个企业知识库助手。你需要帮助用户回答相关问题"
                "回答前必须使用 knowledge_search 工具检索证据，"
                "引用检索结果中的 chunk_id，不能编造没有证据支撑的内容。"
                "回答正文中不得输出 knowledge_search 的原始 JSON、检索结果数组或引用原文本身，"
                "只能使用其中的证据组织回答。"
                "如果检索结果为空，回复“根据当前知识库内容，无法回答该问题”。"
                "每个引用必须能直接支撑对应句子，不引用泛化介绍或相邻章节。"
                "默认只基于当前问题检索一次，不要用多个近似改写后的查询重复检索；"
                "只有第一轮证据明显不足，或问题包含多个独立子问题时才允许第二次检索，"
                "第二次只检索缺失部分，不要重复调用相同查询。"
            ),
        )
    return _agent
