from enum import Enum


class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class MessageStatus(str, Enum):
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class SourceType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    MD = "md"
    MARKDOWN = "markdown"
    HTML = "html"
    HTM = "htm"
    TXT = "txt"
    OTHER = "other"
