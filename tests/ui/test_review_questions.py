"""건별 질문형 수기입력 공통 프레임 — 순수 로직 테스트."""
import pytest
from src.ui.review_questions import (
    Question, DispositionRule, ReviewItemSpec,
    should_show, visible_questions, resolve_disposition, build_result,
)


def _diff(a: dict) -> int:
    return max(0, int(a.get("deal", 0)) - int(a.get("market", 0))) \
        if a.get("type") == "고가매입" else 0


def _unfair_gate(a: dict) -> bool:
    """영§88③: 1·3·6·7·9호는 차액 ≥ 3억 또는 시가 5% 이상일 때만 적용."""
    d = _diff(a)
    market = int(a.get("market", 0))
    return d >= 300_000_000 or (market > 0 and d >= market * 0.05)


def _unfair_spec() -> ReviewItemSpec:
    """부당행위계산 부인 — decision tree + 영§88③ 게이트 예시 스펙."""
    return ReviewItemSpec(
        key="부당행위계산 부인",
        legal_basis="법§52, 영§88③",
        unit="line",
        questions=[
            Question("type", "거래유형?", "select",
                     options=("해당없음", "고가매입", "저가양도", "무상이전")),
            Question("market", "시가(원)?", "amount",
                     show_when=(("type", "고가매입"),)),
            Question("deal", "거래가액(원)?", "amount",
                     show_when=(("type", "고가매입"),)),
            Question("who", "귀속자?", "select",
                     options=("주주", "임원·직원", "법인등", "불분명")),
        ],
        amount_fn=_diff,
        disposition=DispositionRule(
            by_question="who",
            mapping={"주주": "배당", "임원·직원": "상여", "법인등": "기타사외유출",
                     "불분명": "대표자상여"},
        ),
        target_label="부당행위계산 부인",
        add_or_deduct="add",
        gate_fn=_unfair_gate,
    )


# ── show_when (decision tree) ─────────────────────────────────────────────────

def test_show_when_hides_until_condition_met():
    spec = _unfair_spec()
    market_q = next(q for q in spec.questions if q.id == "market")
    assert should_show(market_q, {}) is False
    assert should_show(market_q, {"type": "저가양도"}) is False
    assert should_show(market_q, {"type": "고가매입"}) is True


def test_visible_questions_progressive():
    """해당없음 → 후속 금액질문 숨김 / 고가매입 → 시가·거래가액 노출."""
    spec = _unfair_spec()
    none_ids = [q.id for q in visible_questions(spec, {"type": "해당없음"})]
    assert none_ids == ["type", "who"]
    full_ids = [q.id for q in visible_questions(spec, {"type": "고가매입"})]
    assert full_ids == ["type", "market", "deal", "who"]


# ── 금액·처분 ────────────────────────────────────────────────────────────────

def test_amount_and_disposition_high_purchase():
    spec = _unfair_spec()
    # 차액 20M ≥ 시가(30M)의 5%(1.5M) → 게이트 통과
    answers = {"type": "고가매입", "market": 30_000_000, "deal": 50_000_000, "who": "주주"}
    r = build_result(spec, answers, line_ref="J1|3")
    assert r is not None
    assert r.amount == 20_000_000          # 거래가액 − 시가
    assert r.disposition == "배당"         # 주주 귀속
    assert r.add_or_deduct == "add"
    assert r.line_ref == "J1|3"


def test_unfair_gate_blocks_below_threshold():
    """영§88③: 차액 < 3억 그리고 < 시가 5% → 부인 제외(행 미생성)."""
    spec = _unfair_spec()
    # 시가 10억, 거래가액 10억 4천 → 차액 4천만 < 3억 그리고 < 5%(5천만) → 게이트 차단
    answers = {"type": "고가매입", "market": 1_000_000_000, "deal": 1_040_000_000, "who": "주주"}
    assert build_result(spec, answers) is None
    # 차액 6천만 ≥ 5%(5천만) → 통과
    answers2 = {"type": "고가매입", "market": 1_000_000_000, "deal": 1_060_000_000, "who": "주주"}
    assert build_result(spec, answers2).amount == 60_000_000


def test_zero_amount_returns_none():
    """조정금액 0(해당없음) → 행 미생성."""
    spec = _unfair_spec()
    assert build_result(spec, {"type": "해당없음", "who": "주주"}) is None


def test_disposition_default_when_unanswered():
    spec = _unfair_spec()
    # 귀속자 미선택 → 기본 '검토필요'
    assert resolve_disposition(spec, {"type": "고가매입"}) == "검토필요"


# ── 스펙 검증 (선언 오류 조기 차단) ───────────────────────────────────────────

def test_spec_rejects_dangling_show_when():
    with pytest.raises(ValueError):
        ReviewItemSpec(
            key="x", legal_basis="법§1", unit="line",
            questions=[Question("a", "?", "yesno",
                                show_when=(("ghost", True),))],
            amount_fn=lambda a: 0,
        )


def test_spec_rejects_dangling_disposition():
    with pytest.raises(ValueError):
        ReviewItemSpec(
            key="x", legal_basis="법§1", unit="line",
            questions=[Question("a", "?", "yesno")],
            amount_fn=lambda a: 0,
            disposition=DispositionRule(by_question="ghost", mapping={}),
        )


def test_select_requires_options():
    with pytest.raises(ValueError):
        Question("a", "?", "select")
