"""참고자료 RAG(키워드 검색) — 검색기·토픽 enrich 테스트.

실제 추출텍스트(2_참고자료/추출텍스트)에 의존. 파일 부재 시에도 안전 폴백([])이어야 한다.
"""
from datetime import date

from src.rag.reference_retriever import (
    search_references, enrich_topics_with_references, _chunk_text, _tokenize,
)
from src.rules.consulting import build_consulting_topics, ConsultingTopic
from src.project.taxproj import CompanyInfo, ManualInput
from src.utils.models import TaxAdjustmentResult


def test_chunk_text_by_page_marker():
    """페이지 마커(=== 페이지 N === / === PDF페이지 N ===)로 청킹."""
    txt = "=== 페이지 1 ===\n첫 내용\n=== PDF페이지 2 ===\n둘째 내용"
    chunks = _chunk_text(txt)
    assert [c[0] for c in chunks] == ["p.1", "p.2"]
    assert chunks[0][1] == "첫 내용"


def test_chunk_text_without_markers():
    """마커 없으면 문단 블록으로 청킹(빈 블록 없음)."""
    txt = "문단 A\n\n문단 B\n\n문단 C"
    chunks = _chunk_text(txt)
    assert chunks and all(c[1].strip() for c in chunks)


def test_tokenize_drops_short_tokens_and_dups():
    toks = _tokenize("가지급금 인정이자 가지급금 의 등")
    assert "가지급금" in toks and "인정이자" in toks
    assert toks.count("가지급금") == 1          # 중복 제거
    assert "의" not in toks and "등" not in toks  # 1자 토큰 제거


def test_empty_query_returns_empty():
    assert search_references("", top_k=3) == []
    assert search_references("의 를 에", top_k=3) == []  # 의미 토큰 없음


def test_search_returns_scored_hits():
    """중소기업 세액감면 검색 → 관련 청크가 점수순으로 반환."""
    hits = search_references(
        "중소기업 세액감면",
        top_k=3,
        keywords=["중소기업", "세액감면", "통합투자", "고용증대"],
    )
    assert hits, "추출텍스트에서 중소기업 세액감면 관련 청크를 찾지 못함"
    # 점수 내림차순 정렬
    assert all(hits[i]["score"] >= hits[i + 1]["score"] for i in range(len(hits) - 1))
    # 출처·발췌·청크ID 형식
    h = hits[0]
    assert h["source"] and h["chunk_id"] and h["text"]
    assert h["score"] > 0


def test_enrich_topics_fills_references():
    """실제 컨설팅 토픽을 enrich하면 references가 채워진다."""
    r = TaxAdjustmentResult(
        fiscal_year_start=date(2025, 1, 1),
        fiscal_year_end=date(2025, 12, 31),
        is_sme=True,
    )
    r.deemed_interest = 5_000_000
    topics = build_consulting_topics(
        company=CompanyInfo(is_sme=True),
        manual_input=ManualInput(),
        result=r,
        fiscal_year_end=date(2025, 12, 31),
    )
    enrich_topics_with_references(topics, top_k=2)
    # 가지급금 토픽은 참고자료가 붙어야 한다(키워드 명확)
    g = next(t for t in topics if t.title == "특수관계인 가지급금 정리")
    assert isinstance(g.references, list)
    assert g.references, "가지급금 토픽에 참고자료가 연결되지 않음"
    assert g.references[0]["source"]


def test_enrich_is_resilient_to_no_keywords():
    """keywords 없는 토픽도 title로 검색하고, 실패해도 예외 없이 []."""
    t = ConsultingTopic(
        category="정책", title="존재하지않을제목xyz",
        situation="", basis="", legal_basis="", severity="낮음",
    )
    enrich_topics_with_references([t], top_k=2)
    assert t.references == [] or isinstance(t.references, list)
