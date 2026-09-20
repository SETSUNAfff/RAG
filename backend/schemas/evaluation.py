from __future__ import annotations

from pydantic import BaseModel, Field


class CaseImportItem(BaseModel):
    id: str = Field(alias="id")
    chapter: str | None = None
    difficulty: str = "medium"
    question: str
    expected_answer: str
    expected_document_titles: list[str] | None = None
    expected_source_text: str | None = None


class CaseImportRequest(BaseModel):
    replace: bool = False
    cases: list[CaseImportItem]


class ImportResult(BaseModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    resolved: int = 0
    stale: int = 0
    errors: list[str] = []


class EvaluationRunRequest(BaseModel):
    name: str | None = None
    case_ids: list[int] | None = None
