"""기본정보 연동 세무조정 테스트 — 특정법인(영§42②)·간주임대료(조특법§138).

law.go.kr 확인 근거 (2025-12-31 시행):
- 법§25⑤: 특정법인 기업업무추진비 한도 = ④ 각 호 합계 × 50%
- 영§50의2⑮: 특정법인 승용차 800만→400만, 1,500만→500만
- 조특령§132⑤: 간주익금 = (보증금 − 건설비상당액) × 이자율 − 금융수익 (음수면 0)
"""
import pytest

from src.rules.entertainment import calc_entertainment
from src.rules.income_items import calc_deemed_rental


def test_entertainment_specified_corp_half_limit():
    r_norm = calc_entertainment(
        total_expense=50_000_000, card_expense=50_000_000,
        revenue=1_000_000_000, is_sme=True,
    )
    r_spec = calc_entertainment(
        total_expense=50_000_000, card_expense=50_000_000,
        revenue=1_000_000_000, is_sme=True, is_specified_corp=True,
    )
    # 일반: 3,600만 + 1,000백만×0.3% = 39,000,000 / 특정법인: ×50% = 19,500,000
    assert r_norm.total_limit == 39_000_000
    assert r_spec.total_limit == 19_500_000
    assert r_spec.excess == 50_000_000 - 19_500_000


def test_entertainment_months_proration():
    """사업연도 6개월 → 기본한도 월수 안분 (법§25④1호)."""
    r = calc_entertainment(
        total_expense=0, card_expense=0,
        revenue=0, is_sme=False, months=6,
    )
    assert r.base_limit == 6_000_000


def test_deemed_rental_not_rental_main():
    """부동산임대업 주업 아님 → 미적용 (조특법§138①)."""
    r = calc_deemed_rental(
        deposit=1_000_000_000, debt=10_000_000_000, equity=1_000_000_000,
        bank_rate=0.035, is_rental_main=False,
    )
    assert not r.applicable
    assert r.inclusion_amount == 0


def test_deemed_rental_debt_not_excessive():
    """차입금 ≤ 자기자본×2 → 미적용 (조특령§132①)."""
    r = calc_deemed_rental(
        deposit=1_000_000_000, debt=2_000_000_000, equity=1_000_000_000,
        bank_rate=0.035, is_rental_main=True,
    )
    assert not r.applicable
    assert r.inclusion_amount == 0


def test_deemed_rental_formula():
    """(보증금 − 건설비) × 이자율 − 금융수익 (조특령§132⑤)."""
    r = calc_deemed_rental(
        deposit=1_000_000_000, debt=5_000_000_000, equity=1_000_000_000,
        bank_rate=0.035, is_rental_main=True,
        construction_cost=400_000_000, financial_income=5_000_000,
    )
    assert r.applicable
    # (10억 − 4억) × 3.5% = 21,000,000 − 5,000,000 = 16,000,000
    assert r.inclusion_amount == 16_000_000


def test_deemed_rental_negative_floor():
    """금융수익이 더 크면 0 (조특령§132⑤ — 영보다 적으면 없는 것)."""
    r = calc_deemed_rental(
        deposit=100_000_000, debt=5_000_000_000, equity=1_000_000_000,
        bank_rate=0.035, is_rental_main=True,
        financial_income=10_000_000,
    )
    assert r.inclusion_amount == 0
