import asyncio
from unittest.mock import AsyncMock, patch

from services.retrieval import RetrievalResult, hybrid_search, rrf_merge


def _result(
    chunk_id: int,
    *,
    vector_score: float | None = None,
    bm25_score: float | None = None,
) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        document_id=chunk_id * 10,
        title=f"doc-{chunk_id}",
        page_no=1,
        content=f"content-{chunk_id}",
        metadata=None,
        vector_score=vector_score,
        bm25_score=bm25_score,
    )


def test_rrf_merge_keeps_source_scores_and_fuses_ranks() -> None:
    vector_results = [
        _result(1, vector_score=0.9),
        _result(2, vector_score=0.8),
    ]
    bm25_results = [
        _result(2, bm25_score=2.5),
        _result(3, bm25_score=1.2),
    ]

    merged = rrf_merge(vector_results, bm25_results, top_n=10)

    assert [item.chunk_id for item in merged] == [2, 1, 3]
    assert merged[0].vector_score == 0.8
    assert merged[0].bm25_score == 2.5
    assert merged[0].rrf_score is not None
    assert merged[0].rrf_score > merged[1].rrf_score


def test_hybrid_search_uses_both_sources_without_rerank() -> None:
    vector_results = [
        _result(1, vector_score=0.9),
        _result(2, vector_score=0.8),
    ]
    bm25_results = [
        _result(2, bm25_score=2.5),
        _result(3, bm25_score=1.2),
    ]

    with (
        patch(
            "services.retrieval._vector_search",
            new=AsyncMock(return_value=vector_results),
        ),
        patch(
            "services.retrieval._bm25_search",
            new=AsyncMock(return_value=bm25_results),
        ),
    ):
        results = asyncio.run(
            hybrid_search(
                db=None,
                query="退款规则",
                top_k=3,
                use_rerank=False,
            )
        )

    assert [item.chunk_id for item in results] == [2, 1, 3]


def test_retrieval_result_tool_dict_contains_citation_fields() -> None:
    item = _result(7, vector_score=0.5)
    assert item.to_tool_dict() == {
        "chunk_id": 7,
        "document_id": 70,
        "title": "doc-7",
        "page_no": 1,
        "content": "content-7",
    }
