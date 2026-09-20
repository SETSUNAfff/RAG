from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from schemas.mysql.enums import MessageRole, MessageStatus


class MessageBase(BaseModel):
    conversation_id: int
    role: MessageRole
    content: str
    citations: list[Any] | None = None
    status: MessageStatus = MessageStatus.COMPLETED
    reply_to_message_id: int | None = None
    suggested_questions: list[str] | None = None
    trace_id: str | None = None


class MessageCreate(MessageBase):
    pass


class MessageUpdate(BaseModel):
    role: MessageRole | None = None
    content: str | None = None
    citations: list[Any] | None = None
    status: MessageStatus | None = None
    reply_to_message_id: int | None = None
    suggested_questions: list[str] | None = None
    trace_id: str | None = None


class MessageRead(MessageBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
