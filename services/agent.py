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


def set_document_ids(document_ids: list[int] | None) -> None:
    """Set the document filter for the next knowledge_search call."""
    global _current_document_ids
    _current_document_ids = document_ids


@tool
async def knowledge_search(query: str) -> str:
    """从企业知识库检索与问题相关的证据，返回带引用字段和正文的结果。"""
    async with async_session() as db:
        results = await hybrid_search(
            db, query, top_k=3, document_ids=_current_document_ids
        )
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
                "你是一个企业知识库助手。回答前必须使用 knowledge_search 工具检索证据，"
                "引用检索结果中的 chunk_id，不能编造没有证据支撑的内容。"
                "回答正文中不得输出 knowledge_search 的原始 JSON、检索结果数组或引用原文本身，"
                "只能使用其中的证据组织回答。"
                "如果检索结果为空，回复“根据当前知识库内容，无法回答该问题”。"
            ),
        )
    return _agent
