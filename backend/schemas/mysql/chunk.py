from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ChunkBase(BaseModel):
    document_id: int
    content: str
    heading_path: str | None = None
    page_no: int | None = None
    token_count: int | None = None
    metadata: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("meta", "metadata"),
        serialization_alias="metadata",
    )
    is_active: bool = True
    model_config = ConfigDict(populate_by_name=True)


class ChunkCreate(ChunkBase):
    pass


class ChunkUpdate(BaseModel):
    content: str | None = None
    heading_path: str | None = None
    page_no: int | None = None
    token_count: int | None = None
    metadata: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("meta", "metadata"),
        serialization_alias="metadata",
    )
    is_active: bool | None = None
    model_config = ConfigDict(populate_by_name=True)


class ChunkRead(ChunkBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
