from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EvaluationCaseBase(BaseModel):
    external_id: str
    question: str
    expected_answer: str
    expected_document_titles: list[str] | None = None
    expected_source_text: str | None = None
    chapter: str | None = None
    difficulty: str = "medium"
    source_file: str | None = None
    status: str = "active"


class EvaluationCaseCreate(EvaluationCaseBase):
    expected_chunk_ids: list[int] | None = None


class EvaluationCaseUpdate(BaseModel):
    external_id: str | None = None
    question: str | None = None
    expected_answer: str | None = None
    expected_document_titles: list[str] | None = None
    expected_source_text: str | None = None
    expected_chunk_ids: list[int] | None = None
    chapter: str | None = None
    difficulty: str | None = None
    source_file: str | None = None
    status: str | None = None


class EvaluationCaseRead(EvaluationCaseBase):
    id: int
    expected_chunk_ids: list[int] | None = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class EvaluationRunRead(BaseModel):
    id: int
    name: str
    status: str
    total_cases: int
    completed_cases: int
    message: str | None = None
    metrics_summary: dict | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class EvaluationRunResultRead(BaseModel):
    id: int
    run_id: int
    case_id: int
    question: str
    difficulty: str | None = None
    retrieved_chunk_ids: list[int] | None = Field(default=None)
    retrieved_document_ids: list[int] | None = Field(default=None)
    answer: str | None = None
    citation_chunk_ids: list[int] | None = Field(default=None)
    retrieval_precision: float | None = None
    retrieval_recall: float | None = None
    recall_at_20: float | None = None
    mrr: float | None = None
    hit: bool | None = None
    rouge_l: float | None = None
    embedding_sim: float | None = None
    stale: bool = False
    error: str | None = None
    raw_json: dict | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
