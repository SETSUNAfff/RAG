from datetime import datetime

from pydantic import BaseModel, ConfigDict

from schemas.mysql.enums import DocumentStatus, SourceType


class DocumentBase(BaseModel):
    title: str
    source_type: SourceType
    status: DocumentStatus = DocumentStatus.PENDING
    version: int = 1
    error_message: str | None = None


class DocumentCreate(DocumentBase):
    pass


class DocumentUpdate(BaseModel):
    title: str | None = None
    source_type: SourceType | None = None
    status: DocumentStatus | None = None
    version: int | None = None
    error_message: str | None = None


class DocumentRead(DocumentBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
