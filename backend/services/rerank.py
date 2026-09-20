from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from sentence_transformers import CrossEncoder

from services.retrieval import RetrievalResult


@lru_cache(maxsize=1)
def get_rerank_model() -> CrossEncoder:
    load_dotenv(override=True)
    model_path = os.getenv("RERANK_MODEL_PATH")
    return CrossEncoder(model_path)


def rerank_results(
    query: str,
    candidates: list[RetrievalResult],
) -> list[RetrievalResult]:
    if not candidates:
        return []

    model = get_rerank_model()
    pairs = [(query, candidate.content) for candidate in candidates]
    scores = model.predict(pairs, show_progress_bar=False)
    ranked = sorted(
        zip(candidates, scores.tolist()),
        key=lambda item: item[1],
        reverse=True,
    )
    return [
        candidate
        if candidate.rerank_score == score
        else RetrievalResult(
            chunk_id=candidate.chunk_id,
            document_id=candidate.document_id,
            title=candidate.title,
            page_no=candidate.page_no,
            content=candidate.content,
            metadata=candidate.metadata,
            vector_score=candidate.vector_score,
            bm25_score=candidate.bm25_score,
            rrf_score=candidate.rrf_score,
            rerank_score=float(score),
        )
        for candidate, score in ranked
    ]
