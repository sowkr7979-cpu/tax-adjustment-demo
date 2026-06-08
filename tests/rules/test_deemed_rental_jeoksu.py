# -*- coding: utf-8 -*-
"""간주임대료 — 적수(積數) 기준 산식 테스트 (조특법§138, 조특령§132①⑤)."""
from src.rules.income_items import calc_deemed_rental


def test_deemed_rental_jeoksu_formula():
    """(보증금 적수 − 건설비 적수) × 1/365 × 이자율 − 금융수익."""
    r = calc_deemed_rental(
        deposit=1_000_000_000, debt=5_000_000_000, equity=1_000_000_000,
        bank_rate=0.035, is_rental_main=True,
        construction_cost=400_000_000, financial_income=5_000_000,
        deposit_jeoksu=365_000_000_000,        # 10억 × 365
        debt_jeoksu=1_825_000_000_000,         # 50억 × 365
        construction_jeoksu=146_000_000_000,   # 4억 × 365
        days=365,
    )
    assert r.applicable
    # (3,650억 − 1,460억) ÷ 365 × 3.5% = 6억 × 3.5% = 21,000,000 − 5,000,000
    assert r.inclusion_amount == 16_000_000


def test_deemed_rental_mid_year_deposit():
    """연중 보증금 수령 — 적수가 절반이면 간주익금도 절반."""
    full = calc_deemed_rental(
        deposit=1_000_000_000, debt=5_000_000_000, equity=1_000_000_000,
        bank_rate=0.035, is_rental_main=True,
        deposit_jeoksu=1_000_000_000 * 365, days=365,
    )
    half = calc_deemed_rental(
        deposit=1_000_000_000, debt=5_000_000_000, equity=1_000_000_000,
        bank_rate=0.035, is_rental_main=True,
        deposit_jeoksu=1_000_000_000 * 365 // 2, days=365,
    )
    assert half.inclusion_amount * 2 == full.inclusion_amount


def test_deemed_rental_debt_jeoksu_condition():
    """차입금 과다 판정도 적수 기준 (조특령§132①) — 연중 상환으로 적수 미달 시 미적용."""
    r = calc_deemed_rental(
        deposit=1_000_000_000, debt=3_000_000_000, equity=1_000_000_000,
        bank_rate=0.035, is_rental_main=True,
        # 기말 차입금 30억 > 자기자본 10억×2 이지만, 연중 대부분 상환 상태였다면
        debt_jeoksu=1_000_000_000 * 365,   # 적수상 평균 10억 ≤ 20억
        days=365,
    )
    assert not r.applicable
    assert r.inclusion_amount == 0
