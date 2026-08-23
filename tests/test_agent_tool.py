import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from services.agent import knowledge_search


class _FakeResult:
    def __init__(self, chunk_id: int) -> None:
        self.chunk_id = chunk_id

    def to_tool_dict(self) -> dict:
        return {"chunk_id": self.chunk_id}


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
