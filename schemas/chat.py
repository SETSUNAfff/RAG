from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class Citation(BaseModel):
    chunk_id: int
    document_id: int
    title: str | None = None
    page_no: int | None = None
    content: str | None = None


class ChatRequest(BaseModel):
    conversation_id: int | None = None
    user_id: str = "anonymous"
    question: str = Field(min_length=1)
    history: list[ChatHistoryMessage] = []
    source_ids: list[int] | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    trace_id: str
