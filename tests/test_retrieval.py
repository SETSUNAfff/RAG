import asyncio
from unittest.mock import AsyncMock, patch

from services.retrieval import RetrievalResult, hybrid_search


def _result(
    chunk_id: int,
    *,
    rrf_score: float | None = None,
) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        document_id=chunk_id * 10,
        title=f"doc-{chunk_id}",
        page_no=1,
        content=f"content-{chunk_id}",
        metadata=None,
        rrf_score=rrf_score,
    )


def test_hybrid_search_uses_milvus_and_returns_top_k() -> None:
    fused_results = [
        _result(2, rrf_score=0.8),
        _result(1, rrf_score=0.5),
        _result(3, rrf_score=0.3),
    ]

    with (
        patch(
            "services.retrieval.get_cached_search",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "services.retrieval.set_cached_search",
            new=AsyncMock(),
        ),
        patch(
            "services.retrieval._hybrid_search",
            new=AsyncMock(return_value=fused_results),
        ),
    ):
        results = asyncio.run(
            hybrid_search(
                db=None,
                query="退款规则",
                top_k=2,
                use_rerank=False,
            )
        )

    assert [item.chunk_id for item in results] == [2, 1]


def test_hybrid_search_skips_rerank_when_disabled() -> None:
    fused_results = [_result(2, rrf_score=0.8)]

    with (
        patch(
            "services.retrieval.get_cached_search",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "services.retrieval.set_cached_search",
            new=AsyncMock(),
        ),
        patch(
            "services.retrieval._hybrid_search",
            new=AsyncMock(return_value=fused_results),
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

    assert len(results) == 1
    assert results[0].rerank_score is None


def test_retrieval_result_tool_dict_contains_citation_fields() -> None:
    item = _result(7, rrf_score=0.5)
    assert item.to_tool_dict() == {
        "chunk_id": 7,
        "document_id": 70,
        "title": "doc-7",
        "page_no": 1,
        "content": "content-7",
    }
