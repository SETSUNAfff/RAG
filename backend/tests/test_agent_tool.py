import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import services.agent as agent_module
from services.agent import knowledge_search


class _FakeResult:
    def __init__(self, chunk_id: int) -> None:
        self.chunk_id = chunk_id

    def to_tool_dict(self) -> dict:
        return {"chunk_id": self.chunk_id}


class _ScoredResult:
    def __init__(self, chunk_id: int, rerank_score: float) -> None:
        self.chunk_id = chunk_id
        self.rerank_score = rerank_score


def test_knowledge_search_passes_database_before_query() -> None:
    fake_db = object()
    fake_session = MagicMock()
    fake_session.__aenter__ = AsyncMock(return_value=fake_db)
    fake_session.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("services.agent.async_session", return_value=fake_session),
        patch(
            "services.agent.hybrid_search",
            new=AsyncMock(return_value=[_FakeResult(7)]),
        ) as mock_search,
    ):
        output = asyncio.run(
            knowledge_search.ainvoke({"query": "外部协作者"})
        )

    call = mock_search.await_args
    assert call is not None
    assert call.args[0] is fake_db
    assert call.args[1] == "外部协作者"
    assert json.loads(output) == [{"chunk_id": 7}]


def test_filter_evidence_keeps_top1_and_high_ratio_only() -> None:
    original_enabled = agent_module._RETRIEVAL_FILTER_ENABLED
    original_ratio = agent_module._RETRIEVAL_FILTER_MIN_RATIO
    original_max = agent_module._RETRIEVAL_MAX_EVIDENCE_PER_CALL
    agent_module._RETRIEVAL_FILTER_ENABLED = True
    agent_module._RETRIEVAL_FILTER_MIN_RATIO = 0.7
    agent_module._RETRIEVAL_MAX_EVIDENCE_PER_CALL = 3
    try:
        results = [
            _ScoredResult(1, 10.0),
            _ScoredResult(2, 9.0),
            _ScoredResult(3, 6.0),
            _ScoredResult(4, 2.0),
        ]
        filtered = agent_module._filter_evidence(results)
    finally:
        agent_module._RETRIEVAL_FILTER_ENABLED = original_enabled
        agent_module._RETRIEVAL_FILTER_MIN_RATIO = original_ratio
        agent_module._RETRIEVAL_MAX_EVIDENCE_PER_CALL = original_max

    assert [result.chunk_id for result in filtered] == [1, 2]
