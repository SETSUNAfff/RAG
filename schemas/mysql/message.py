from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from schemas.mysql.enums import MessageRole


class MessageBase(BaseModel):
    conversation_id: int
    role: MessageRole
    content: str
    citations: list[Any] | None = None


class MessageCreate(MessageBase):
    pass


class MessageUpdate(BaseModel):
    role: MessageRole | None = None
    content: str | None = None
    citations: list[Any] | None = None


class MessageRead(MessageBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
