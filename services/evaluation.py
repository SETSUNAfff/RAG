from __future__ import annotations

import asyncio
import json
import logging
import re
from difflib import SequenceMatcher
from datetime import datetime
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.mysql_engine import async_session
from crud.mysql.evaluations import (
    create_evaluation_result,
    create_evaluation_case,
    clear_evaluation_cases,
    get_evaluation_run,
    get_evaluation_case_by_external_id,
    update_evaluation_case,
    update_evaluation_run,
)
from schemas.evaluation import CaseImportItem, ImportResult
from schemas.mysql import EvaluationCaseCreate
from models.mysql import Chunk, Document, EvaluationCase
from schemas.mysql import EvaluationCaseUpdate
from services.embeddings import get_embedding_model

logger = logging.getLogger(__name__)

_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_PUNCT_MAP = str.maketrans(
    {
        "，": ",",
        "。": ".",
        "；": ";",
        "：": ":",
        "？": "?",
        "！": "!",
        "（": "(",
        "）": ")",
        "、": ",",
        "《": "<",
        "》": ">",
    }
)
_PUNCT_NOISE_RE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)
_FALLBACK_MATCH_THRESHOLD = 0.85
_MAX_EXPECTED_CHUNKS = 3


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _MARKDOWN_LINK_RE.sub(r"\1", text)

    lines: list[str] = []
    for line in text.splitlines():
        line = re.sub(r"^\s*>+\s*", "", line)
        line = re.sub(r"^\s*#{1,6}\s*", "", line)
        line = line.replace("**", "").replace("`", "")
        line = re.sub(r"^\s*(?:\d+\s*[\.、)]|[-*+])\s*", "", line)
        lines.append(line)
    text = "\n".join(lines)
    text = text.translate(_PUNCT_MAP)
    text = text.replace("\u200b", "").replace("\ufeff", "")
    return re.sub(r"\s+", "", text)


def _normalize_for_match(text: str | None) -> str:
    return _PUNCT_NOISE_RE.sub("", _normalize(text))


def _split_evidence_segments(text: str) -> list[str]:
    """Split expected source into list items, QA blocks, then sentences."""
    if not text:
        return []

    text = _MARKDOWN_LINK_RE.sub(r"\1", text)
    text = re.sub(r"(?m)^\s*>+\s*", "", text)
    text = re.sub(r"(?m)^\s*#{1,6}\s*", "", text)
    text = text.replace("**", "").replace("`", "")

    parts = re.split(
        r"(?m)(?=^\s*(?:\d+\s*[\.、)]|[-*+]|Q[:：]|A[:：]))",
        text,
    )
    if len(parts) <= 1:
        parts = re.split(
            r"(?=(?:\d+\s*[\.、)]|[-*+]|Q[:：]|A[:：]))",
            text,
        )
    segments: list[str] = []
    for part in parts:
        part = re.sub(
            r"^\s*(?:\d+\s*[\.、)]|[-*+])\s*",
            "",
            part.strip(),
        )
        for segment in re.split(r"(?<=[。！？；])", part):
            normalized = _normalize(segment)
            if normalized:
                segments.append(normalized)
    return list(dict.fromkeys(segments))


def _match_coverage(segment: str, content: str) -> float:
    """Return aggregate segment coverage from multiple matching blocks."""
    normalized_segment = _normalize_for_match(segment)
    normalized_content = _normalize_for_match(content)
    if not normalized_segment or not normalized_content:
        return 0.0
    if normalized_segment in normalized_content:
        return 1.0

    matcher = SequenceMatcher(
        None,
        normalized_segment,
        normalized_content,
        autojunk=False,
    )
    matched_chars = sum(block.size for block in matcher.get_matching_blocks())
    return matched_chars / len(normalized_segment)


def _extract_retrieval_traces(
    messages,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract knowledge_search calls with query text and deduplicated chunks."""
    from langchain_core.messages import ToolMessage

    query_by_call_id: dict[str, str] = {}
    for message in messages:
        if getattr(message, "type", "") == "ai":
            for call in (getattr(message, "tool_calls", None) or []):
                if call.get("name") != "knowledge_search":
                    continue
                args = call.get("args") or {}
                query_by_call_id[str(call.get("id"))] = args.get("query") or ""

    traces: list[dict[str, Any]] = []
    chunks: dict[int, dict[str, Any]] = {}
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        if getattr(message, "name", None) != "knowledge_search":
            continue
        try:
            payload = json.loads(message.content)
        except (TypeError, json.JSONDecodeError):
            continue
        parsed: list[dict[str, Any]] = []
        for item in payload or []:
            if isinstance(item, dict) and item.get("chunk_id") is not None:
                parsed.append(item)
                chunks[int(item["chunk_id"])] = item
        traces.append(
            {
                "query": query_by_call_id.get(
                    str(getattr(message, "tool_call_id", "")),
                ),
                "chunks": parsed,
            }
        )
    return traces, list(chunks.values())


def _extract_citation_ids(
    answer: str,
    allowed_ids: list[int],
) -> list[int]:
    """Parse common citation markers and validate against evidence ids."""
    allowed = set(allowed_ids)
    candidates: list[tuple[int, int]] = []
    seen: set[int] = set()
    patterns = [
        r"\[\s*citation\s*:\s*(\d+)\s*\]",
        r"(?:引用|来源)\s*[:：]\s*(\d+(?:\s*[、,，和及]\s*\d+)*)",
        r"(?:chunk|块)\s*[:：]?\s*(\d+(?:\s*[、,，和及]\s*\d+)*)",
        r"\[\s*(\d+)\s*\]",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, answer, re.IGNORECASE):
            for raw in re.split(r"[、,，和及]+", match.group(1)):
                digits = re.sub(r"\D", "", raw)
                if not digits:
                    continue
                chunk_id = int(digits)
                if chunk_id in allowed and chunk_id not in seen:
                    seen.add(chunk_id)
                    candidates.append((match.start(), chunk_id))
    return [chunk_id for _, chunk_id in sorted(candidates)]


def _extract_answer(messages) -> str:
    for message in reversed(messages):
        if getattr(message, "type", "") == "ai" and not getattr(
            message, "tool_calls", None
        ):
            return message.content or ""
    return ""


async def resolve_expected_chunks(
    db: AsyncSession,
    case: EvaluationCase,
) -> tuple[list[int], bool]:
    """Resolve the expected source text to a stable set of chunk ids."""
    stored_ids = case.expected_chunk_ids or []
    if stored_ids:
        existing = list(
            (
                await db.execute(
                    select(Chunk.id).where(
                        Chunk.id.in_(stored_ids),
                        Chunk.is_active.is_(True),
                    )
                )
            ).scalars().all()
        )
        if existing:
            return sorted(set(existing)), False

    titles = case.expected_document_titles or []
    if not titles:
        return [], False

    docs = list(
        (
            await db.execute(
                select(Document).where(Document.title.in_(titles))
            )
        ).scalars().all()
    )
    if not docs:
        return [], True

    doc_ids = [doc.id for doc in docs]
    chunks = list(
        (
            await db.execute(
                select(Chunk)
                .where(
                    Chunk.document_id.in_(doc_ids),
                    Chunk.is_active.is_(True),
                )
                .order_by(Chunk.id.asc())
            )
        ).scalars().all()
    )
    if not chunks:
        return [], True

    source = case.expected_source_text
    if not source:
        return [], True

    match_source = _normalize_for_match(source)
    matched: list[int] = []
    for chunk in chunks:
        chunk_text = _normalize_for_match(chunk.content)
        if chunk_text and (
            match_source in chunk_text or chunk_text in match_source
        ):
            matched.append(chunk.id)

    matched = sorted(set(matched))
    if matched and len(matched) <= _MAX_EXPECTED_CHUNKS:
        return matched, False
    if len(matched) > _MAX_EXPECTED_CHUNKS:
        return [], True

    matched_by_segment: list[tuple[int, float]] = []
    for segment in _split_evidence_segments(source):
        best: tuple[float, int] | None = None
        for chunk in chunks:
            coverage = _match_coverage(segment, chunk.content)
            if coverage >= _FALLBACK_MATCH_THRESHOLD:
                if best is None or coverage > best[0]:
                    best = (coverage, chunk.id)
        if best is None:
            return [], True
        matched_by_segment.append((best[1], best[0]))

    fallback_ids = list(dict.fromkeys(chunk_id for chunk_id, _ in matched_by_segment))
    fallback_ids = sorted(set(fallback_ids))
    if fallback_ids and len(fallback_ids) <= _MAX_EXPECTED_CHUNKS:
        return fallback_ids, False
    return [], True


async def import_cases(
    db: AsyncSession,
    items: list[CaseImportItem],
    *,
    replace: bool = False,
) -> ImportResult:
    result = ImportResult()
    if replace:
        await clear_evaluation_cases(db)
    for item in items:
        try:
            existing = await get_evaluation_case_by_external_id(db, item.id)
            expected_ids, stale = await resolve_expected_chunks(
                db,
                EvaluationCase(
                    external_id=item.id,
                    question=item.question,
                    expected_answer=item.expected_answer,
                    expected_document_titles=item.expected_document_titles,
                    expected_source_text=item.expected_source_text,
                ),
            )
            case_status = "pending_review" if stale else "active"
            if stale:
                result.stale += 1
            else:
                result.resolved += 1

            if existing is None:
                await create_evaluation_case(
                    db,
                    EvaluationCaseCreate(
                        external_id=item.id,
                        question=item.question,
                        expected_answer=item.expected_answer,
                        expected_document_titles=item.expected_document_titles,
                        expected_source_text=item.expected_source_text,
                        expected_chunk_ids=expected_ids,
                        chapter=item.chapter,
                        difficulty=item.difficulty,
                        status=case_status,
                    ),
                )
                result.created += 1
            else:
                await update_evaluation_case(
                    db,
                    existing.id,
                    EvaluationCaseUpdate(
                        external_id=item.id,
                        question=item.question,
                        expected_answer=item.expected_answer,
                        expected_document_titles=item.expected_document_titles,
                        expected_source_text=item.expected_source_text,
                        expected_chunk_ids=expected_ids,
                        chapter=item.chapter,
                        difficulty=item.difficulty,
                        status=case_status,
                    ),
                )
                result.updated += 1
        except Exception as exc:
            logger.exception("Import case %s failed", getattr(item, "id", ""))
            result.errors.append(f"{getattr(item, 'id', '')}: {exc}")
            result.skipped += 1
    return result


def compute_retrieval_metrics(
    expected_ids: list[int],
    retrieved_ids: list[int],
) -> dict[str, float | bool | None]:
    if not expected_ids:
        return {
            "retrieval_precision": None,
            "retrieval_recall": None,
            "mrr": None,
            "hit": None,
        }
    expected = set(expected_ids)
    retrieved = list(dict.fromkeys(retrieved_ids or []))
    if not retrieved:
        return {
            "retrieval_precision": 0.0,
            "retrieval_recall": 0.0,
            "mrr": 0.0,
            "hit": False,
        }
    hits = sum(1 for chunk_id in retrieved if chunk_id in expected)
    precision = hits / len(retrieved)
    recall = hits / len(expected)
    mrr = 0.0
    for index, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in expected:
            mrr = 1.0 / index
            break
    return {
        "retrieval_precision": precision,
        "retrieval_recall": recall,
        "mrr": mrr,
        "hit": hits > 0,
    }


def _rouge_l_fmeasure(reference: str, prediction: str) -> float | None:
    try:
        import jieba
        from rouge_score import rouge_scorer

        class _WhitespaceTokenizer:
            def tokenize(self, text: str) -> list[str]:
                return text.split()

        ref_tokens = " ".join(jieba.cut(reference))
        pred_tokens = " ".join(jieba.cut(prediction))
        scorer = rouge_scorer.RougeScorer(
            ["rougeL"],
            use_stemmer=False,
            tokenizer=_WhitespaceTokenizer(),
        )
        return float(scorer.score(ref_tokens, pred_tokens)["rougeL"].fmeasure)
    except Exception:
        return None


def _embedding_similarity(reference: str, prediction: str) -> float | None:
    try:
        model = get_embedding_model()
        vectors = model.encode([reference, prediction])
        a, b = vectors[0], vectors[1]
        denominator = (np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
        return float(np.dot(a, b) / denominator)
    except Exception:
        return None


def compute_answer_metrics(
    reference: str,
    prediction: str,
) -> dict[str, float | None]:
    if not reference or not prediction:
        return {"rouge_l": None, "embedding_sim": None}
    return {
        "rouge_l": _rouge_l_fmeasure(reference, prediction),
        "embedding_sim": _embedding_similarity(reference, prediction),
    }


async def evaluate_case(db: AsyncSession, case: EvaluationCase) -> dict[str, Any]:
    from services.agent import get_agent, set_document_ids
    from services.context import clean_agent_output
    from services.retrieval import hybrid_search

    expected_ids, stale = await resolve_expected_chunks(db, case)
    if stale:
        expected_ids = []

    set_document_ids(None)
    result = await get_agent().ainvoke(
        {"messages": [{"role": "user", "content": case.question}]}
    )
    output_messages = result.get("messages", []) or []
    answer = clean_agent_output(_extract_answer(output_messages))
    retrieval_traces, retrieved = _extract_retrieval_traces(output_messages)
    if retrieved:
        evidence_ids = [
            int(item["chunk_id"])
            for item in retrieved
            if item.get("chunk_id") is not None
        ]
        retrieved_doc_ids = list(
            {
                int(item["document_id"])
                for item in retrieved
                if item.get("document_id") is not None
            }
        )
    else:
        fallback_results = await hybrid_search(
            db, case.question, top_k=5, document_ids=None
        )
        evidence_ids = [item.chunk_id for item in fallback_results]
        retrieved_doc_ids = list(
            {
                item.document_id
                for item in fallback_results
                if item.document_id
            }
        )
        retrieved = [item.to_tool_dict() for item in fallback_results]
        retrieval_traces = [
            {
                "query": case.question,
                "chunks": retrieved,
            }
        ]
    evidence_ids = list(dict.fromkeys(evidence_ids))

    diagnostic_results = await hybrid_search(
        db,
        case.question,
        top_k=20,
        vector_top_n=20,
        bm25_top_n=20,
        rrf_candidates=20,
        document_ids=None,
    )
    diagnostic_ids = [
        item.chunk_id
        for item in diagnostic_results
        if item.chunk_id
    ]
    diagnostic_scores = [
        {
            "chunk_id": item.chunk_id,
            "rrf_score": item.rrf_score,
            "rerank_score": item.rerank_score,
        }
        for item in diagnostic_results
    ]
    recall_at_20 = compute_retrieval_metrics(expected_ids, diagnostic_ids)[
        "retrieval_recall"
    ]

    retrieval_metrics = compute_retrieval_metrics(expected_ids, diagnostic_ids)
    retrieval_metrics["retrieval_precision"] = compute_retrieval_metrics(
        expected_ids,
        diagnostic_ids[:1],
    )["retrieval_precision"]
    answer_metrics = await asyncio.to_thread(
        compute_answer_metrics, case.expected_answer, answer
    )
    citation_ids = _extract_citation_ids(answer, evidence_ids)

    fields = {
        "case_id": case.id,
        "question": case.question,
        "difficulty": case.difficulty,
        "retrieved_chunk_ids": evidence_ids,
        "retrieved_document_ids": list(dict.fromkeys(retrieved_doc_ids)),
        "answer": answer,
        "citation_chunk_ids": citation_ids,
        "recall_at_20": recall_at_20,
        "stale": stale,
        "raw_json": {
            "expected_ids": expected_ids,
            "retrieval_traces": retrieval_traces,
            "retrieved": retrieved,
            "diagnostic_ids": diagnostic_ids,
            "diagnostic_scores": diagnostic_scores,
            "tool_call_count": len(retrieval_traces),
            "evidence_chunk_count": len(evidence_ids),
            "expected_answer": case.expected_answer,
            "chapter": case.chapter,
        },
    }
    fields.update(retrieval_metrics)
    fields.update(answer_metrics)
    return fields


def _aggregate(values: list[float | None]) -> float | None:
    numbers = [value for value in values if value is not None]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def _build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    metric_keys = [
        "retrieval_precision",
        "retrieval_recall",
        "recall_at_20",
        "mrr",
        "hit",
        "rouge_l",
        "embedding_sim",
    ]
    for key in metric_keys:
        summary[key] = _aggregate(
            [
                result.get(key)
                for result in results
                if not result.get("error") and not result.get("stale")
            ]
        )
    summary["total"] = len(results)
    summary["success"] = sum(
        1 for result in results if not result.get("error")
    )
    summary["failed"] = sum(1 for result in results if result.get("error"))
    summary["stale"] = sum(1 for result in results if result.get("stale"))

    for dimension, key in (
        ("difficulty", "difficulty"),
        ("chapter", "chapter"),
    ):
        groups: dict[str, dict[str, Any]] = {}
        for result in results:
            if key == "chapter":
                value = (result.get("raw_json") or {}).get("chapter") or "unknown"
            else:
                value = result.get(key) or "unknown"
            group = groups.setdefault(value, {"count": 0, "metrics": []})
            group["count"] += 1
            group["metrics"].append(result)
        for group in groups.values():
            group["metrics"] = {
                metric: _aggregate(
                    [
                        item.get(metric)
                        for item in group["metrics"]
                        if not item.get("error") and not item.get("stale")
                    ]
                )
                for metric in metric_keys
            }
        summary[dimension] = {
            value: group
            for value, group in groups.items()
        }

    return summary


async def run_evaluation_task(run_id: int, case_ids: list[int] | None = None) -> None:
    async with async_session() as db:
        run = await get_evaluation_run(db, run_id)
        if run is None:
            return
        await update_evaluation_run(
            db,
            run_id,
            {
                "status": "running",
                "started_at": datetime.now(),
            },
        )

        if case_ids:
            statement = (
                select(EvaluationCase)
                .where(EvaluationCase.id.in_(case_ids))
                .order_by(EvaluationCase.id.asc())
            )
        else:
            statement = (
                select(EvaluationCase)
                .where(EvaluationCase.status == "active")
                .order_by(EvaluationCase.id.asc())
            )
        cases = list((await db.execute(statement)).scalars().all())
        await update_evaluation_run(
            db,
            run_id,
            {
                "total_cases": len(cases),
                "completed_cases": 0,
            },
        )

        result_rows: list[dict[str, Any]] = []
        for case in cases:
            try:
                fields = await evaluate_case(db, case)
                fields["run_id"] = run_id
                result_row = await create_evaluation_result(db, fields)
                result_rows.append(fields)

                if case.expected_chunk_ids != fields["raw_json"]["expected_ids"]:
                    await update_evaluation_case(
                        db,
                        case.id,
                        EvaluationCaseUpdate(
                            expected_chunk_ids=fields["raw_json"]["expected_ids"]
                        ),
                    )
            except Exception as exc:
                logger.exception("Evaluation case %s failed", case.id)
                error_fields = {
                    "run_id": run_id,
                    "case_id": case.id,
                    "question": case.question,
                    "difficulty": case.difficulty,
                    "error": str(exc),
                    "stale": False,
                }
                await create_evaluation_result(db, error_fields)
                result_rows.append(error_fields)

            await update_evaluation_run(
                db,
                run_id,
                {"completed_cases": len(result_rows)},
            )

        summary = _build_summary(result_rows)
        await update_evaluation_run(
            db,
            run_id,
            {
                "status": "success",
                "completed_at": datetime.now(),
                "message": f"共 {len(cases)} 条，成功 {summary['success']}，失败 {summary['failed']}，过期 {summary['stale']}",
                "metrics_summary": summary,
            },
        )
