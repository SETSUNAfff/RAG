from services.evaluation import (
    _aggregate,
    _extract_citation_ids,
    _match_coverage,
    _normalize,
    _split_evidence_segments,
    _rouge_l_fmeasure,
    compute_retrieval_metrics,
)


def test_normalize_removes_whitespace_and_zero_width() -> None:
    assert _normalize("退 款\n规则\u200b\ufeff") == "退款规则"


def test_normalize_strips_markdown_and_normalizes_punctuation() -> None:
    value = "> **Q：手册里没写的情况怎么办？**\n> A：先问直属主管。"
    assert _normalize(value) == "Q:手册里没写的情况怎么办?A:先问直属主管."


def test_split_evidence_segments_keeps_list_items() -> None:
    segments = _split_evidence_segments(
        "1. 客户第一：做决策时先想对客户好不好。2. 坦诚透明：有问题当面说。"
    )
    assert len(segments) == 2
    assert "客户第一:做决策时先想对客户好不好." in segments
    assert "坦诚透明:有问题当面说." in segments


def test_match_coverage_ignores_markdown_and_punctuation() -> None:
    segment = "请病假超过3天的，需要二级及以上医院的诊断证明"
    content = "**请病假超过 3 天**的，需要二级及以上医院的诊断证明和病假条"
    assert _match_coverage(segment, content) >= 0.99


def test_extract_citation_ids_parses_known_formats_with_whitelist() -> None:
    answer = (
        "根据知识库可知[citation:330]，同时参考[335]。"
        "加班规则见（chunk 338、339），来源:340。"
        "公司成立于2015年。"
    )
    allowed = [330, 335, 338, 339, 340]
    assert _extract_citation_ids(answer, allowed) == [330, 335, 338, 339, 340]


def test_extract_citation_ids_ignores_numbers_outside_evidence() -> None:
    answer = "公司成立于2015年，规则见[330]。"
    assert _extract_citation_ids(answer, [330]) == [330]


def test_retrieval_metrics_with_perfect_hit() -> None:
    metrics = compute_retrieval_metrics([10, 11], [10, 20, 11])
    assert metrics["hit"] is True
    assert metrics["mrr"] == 1.0
    assert metrics["retrieval_precision"] == 2 / 3
    assert metrics["retrieval_recall"] == 1.0


def test_retrieval_metrics_with_second_rank_mrr() -> None:
    metrics = compute_retrieval_metrics([99], [1, 99, 2])
    assert metrics["hit"] is True
    assert metrics["mrr"] == 0.5


def test_retrieval_metrics_empty_expected_returns_none() -> None:
    metrics = compute_retrieval_metrics([], [1, 2])
    assert metrics["retrieval_precision"] is None
    assert metrics["hit"] is None


def test_rouge_l_returns_score_for_matching_chinese() -> None:
    score = _rouge_l_fmeasure("退款规则如下", "退款规则如下")
    assert score is not None
    assert score > 0.99


def test_aggregate_ignores_none() -> None:
    assert _aggregate([1.0, None, 3.0]) == 2.0
    assert _aggregate([None, None]) is None
