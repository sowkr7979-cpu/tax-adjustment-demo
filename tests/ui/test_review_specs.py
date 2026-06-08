"""건별 질문 스펙 카탈로그 — 부당행위·복리후생·의제배당."""
from src.ui.review_specs import (
    unfair_transaction_spec, _UNFAIR_TYPES, welfare_spec, deemed_dividend_spec,
    inventory_spec, officer_retirement_spec, officer_bonus_spec,
)


# ── 임원 상여 한도초과 (영§43②) ──────────────────────────────────────────────

def test_officer_bonus_excess_over_standard():
    """지급기준 한도 초과분만 손금불산입."""
    spec = officer_bonus_spec()
    a = {"is_officer": True, "has_standard": "있음", "standard_amount": 30_000_000,
         "paid_amount": 50_000_000}
    assert build_result(spec, a).amount == 20_000_000


def test_officer_bonus_no_standard_full_disallowed():
    """지급기준 없으면 전액 손금불산입 (기준=0)."""
    spec = officer_bonus_spec()
    a = {"is_officer": True, "has_standard": "없음", "paid_amount": 40_000_000}
    assert build_result(spec, a).amount == 40_000_000


def test_officer_bonus_employee_not_applicable():
    """직원(임원 아님)이면 영§43② 미적용 — 게이트 차단."""
    spec = officer_bonus_spec()
    a = {"is_officer": False, "paid_amount": 40_000_000}
    assert build_result(spec, a) is None
from src.ui.review_questions import build_result, build_results, visible_questions


# ── 임원 퇴직금 한도초과 (영§44④⑤ 정관규정 우선) ────────────────────────────

def test_officer_retire_articles_limit_priority():
    """정관 규정 있으면 정관금액이 한도 (1/10×근속 산식 미적용)."""
    spec = officer_retirement_spec()
    a = {"has_articles": "있음", "articles_limit": 100_000_000, "paid_amount": 150_000_000}
    assert build_result(spec, a).amount == 50_000_000
    # 정관 있으면 근속·총급여 질문 미노출
    vis = [q.id for q in visible_questions(spec, {"has_articles": "있음"})]
    assert "service_years" not in vis and "total_salary_1y" not in vis


def test_officer_retire_statutory_limit_when_no_articles():
    """정관 없으면 한도 = 총급여 × 1/10 × 근속연수 (영§44④2호)."""
    spec = officer_retirement_spec()
    # 한도 = 120,000,000 × 0.1 × 5 = 60,000,000 / 지급 80,000,000 → 초과 20,000,000
    a = {"has_articles": "없음", "total_salary_1y": 120_000_000, "service_years": 5,
         "paid_amount": 80_000_000}
    assert build_result(spec, a).amount == 20_000_000


# ── 재고자산 평가 (영§74④ 단서) ──────────────────────────────────────────────

def test_inventory_lawful_filing_no_adjustment():
    """적법신고면 조정 없음."""
    spec = inventory_spec()
    assert build_result(spec, {"filing_status": "적법신고"}) is None


def test_inventory_no_filing_uses_fifo():
    """무신고 → 선입선출 평가액 − 장부액 (단서 미적용)."""
    spec = inventory_spec()
    a = {"filing_status": "무신고", "book_value": 80_000_000, "fifo_value": 100_000_000}
    r = build_result(spec, a)
    assert r.amount == 20_000_000
    assert r.reserve_field == "inventory_adjustment"   # 을표 연계


def test_inventory_proviso_uses_max_of_fifo_and_filed():
    """신고방법 외 평가 → 단서: max(선입선출, 신고방법 평가액) − 장부액."""
    spec = inventory_spec()
    # 선입선출 100M < 신고방법 120M → 신고방법(120M) 적용
    a = {"filing_status": "신고방법 외 평가", "book_value": 90_000_000,
         "fifo_value": 100_000_000, "filed_method_value": 120_000_000}
    assert build_result(spec, a).amount == 30_000_000   # 120M − 90M


# ── 의제배당 (법§16① 사유별·상법§459 게이트) ────────────────────────────────

def test_deemed_dividend_general_cause_subtracts_cost():
    """감자·해산·합병·분할: 교부재산 − 취득가액."""
    spec = deemed_dividend_spec()
    a = {"cause": "합병(5호)", "received": 100_000_000, "cost": 60_000_000}
    assert build_result(spec, a).amount == 40_000_000


def test_deemed_dividend_bonus_issue_no_cost_subtraction():
    """무상증자(2호): 취득가액 차감 없이 교부주식가액 전부. 취득가액 질문 미노출."""
    spec = deemed_dividend_spec()
    a = {"cause": "잉여금 자본전입=무상증자(2호)", "excluded_reserve": "아니오(이익잉여금 등)",
         "received": 30_000_000}
    assert build_result(spec, a).amount == 30_000_000
    # 무상증자에는 'cost'(취득가액) 질문이 노출되지 않아야 함
    vis = [q.id for q in visible_questions(spec, {"cause": "잉여금 자본전입=무상증자(2호)"})]
    assert "cost" not in vis
    assert "cost" in [q.id for q in visible_questions(spec, {"cause": "합병(5호)"})]


def test_deemed_dividend_capital_reserve_excluded():
    """상법§459① 자본준비금·재평가적립금 자본전입은 의제배당 제외(게이트 차단)."""
    spec = deemed_dividend_spec()
    a = {"cause": "잉여금 자본전입=무상증자(2호)", "excluded_reserve": "예(의제배당 제외)",
         "received": 30_000_000}
    assert build_result(spec, a) is None


# ── 복리후생비 (영§45① 열거 게이트 → 귀속자 처분) ────────────────────────────

def test_welfare_enumerated_item_not_disallowed():
    """영§45 열거 8항목(경조사비 등)은 손금 인정 — 게이트 차단(행 미생성)."""
    spec = welfare_spec()
    a = {"category": "경조사비 등 유사비용(8호)", "amount": 5_000_000, "who": "임원·직원(상여)"}
    assert build_result(spec, a) is None


def test_welfare_non_enumerated_disallowed_with_disposition():
    """'열거 외 비용'만 손금불산입, 귀속자별 소득처분."""
    spec = welfare_spec()
    a = {"category": "열거 외 비용", "amount": 4_250_000, "who": "주주(배당)"}
    r = build_result(spec, a)
    assert r.amount == 4_250_000 and r.disposition == "배당"
    a2 = {"category": "열거 외 비용", "amount": 1_000_000, "who": "불분명(대표자상여)"}
    assert build_result(spec, a2).disposition == "대표자상여"


def test_loan_type_excluded_from_options():
    """금전 대여(영§88①6호)는 거래유형 보기에 없어야 한다 (인정이자 트랙·통산금지)."""
    joined = " ".join(_UNFAIR_TYPES)
    assert "대여" not in joined and "6호" not in joined


def test_gated_type_below_threshold_excluded():
    """1·3·6·7·9호: 차액 < 3억 그리고 < 시가 5% → 부인 제외."""
    spec = unfair_transaction_spec()
    a = {"type": "고가매입(1호)", "market": 1_000_000_000, "deal": 1_040_000_000, "who": "주주"}
    assert build_result(spec, a) is None         # 4천만 < 3억·5%
    a2 = {"type": "고가매입(1호)", "market": 1_000_000_000, "deal": 1_060_000_000, "who": "주주"}
    r = build_result(spec, a2)
    assert r.amount == 60_000_000 and r.disposition == "배당"   # 6천만 ≥ 5%


def test_full_type_no_gate():
    """2·8호(무수익자산·자본거래): 게이트 없이 전액 부인 — 차액 작아도 적용."""
    spec = unfair_transaction_spec()
    a = {"type": "자본거래(8호)", "market": 100_000_000, "deal": 99_000_000, "who": "법인등"}
    r = build_result(spec, a)               # 차액 100만 (5% 미만)이라도 전액 부인
    assert r is not None
    assert r.amount == 1_000_000 and r.disposition == "기타사외유출"


def test_disposition_mapping():
    spec = unfair_transaction_spec()
    base = {"type": "저가양도(3호)", "market": 500_000_000, "deal": 0}  # 차액 5억 ≥ 3억
    assert build_result(spec, {**base, "who": "임원·직원"}).disposition == "상여"
    assert build_result(spec, {**base, "who": "불분명"}).disposition == "대표자상여"


def test_build_results_filters_and_keeps_refs():
    """여러 건 중 게이트 통과분만, _ref는 line_ref로 보존."""
    spec = unfair_transaction_spec()
    answers = [
        {"type": "해당없음", "_ref": "J1|1"},                                   # 제외
        {"type": "고가매입(1호)", "market": 1_000_000_000, "deal": 1_010_000_000,
         "who": "주주", "_ref": "J2|3"},                                        # 1% < 5% → 제외
        {"type": "고가매입(1호)", "market": 1_000_000_000, "deal": 1_400_000_000,
         "who": "주주", "_ref": "J3|5"},                                        # 4억 ≥ 3억 → 포함
    ]
    results = build_results(spec, answers)
    assert len(results) == 1
    assert results[0].amount == 400_000_000
    assert results[0].line_ref == "J3|5"
