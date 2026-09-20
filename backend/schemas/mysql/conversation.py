from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConversationBase(BaseModel):
    user_id: str
    title: str = "Untitled"


class ConversationCreate(ConversationBase):
    pass


class ConversationUpdate(BaseModel):
    user_id: str | None = None
    title: str | None = None


class ConversationRead(ConversationBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
