# -*- coding: utf-8 -*-
"""적수(積數) 계산 및 거래상대방별 인정이자 테스트 (영§89⑤, 영§88③, 영§53③)."""
from datetime import date

from src.rules.jeoksu import jeoksu_from_deltas, fy_days
from src.rules.income_items import calc_deemed_interest_by_party

FY_S = date(2025, 1, 1)
FY_E = date(2025, 12, 31)


def test_fy_days():
    assert fy_days(FY_S, FY_E) == 365


def test_jeoksu_constant_balance():
    """기초잔액만 있고 변동 없음 → 잔액 × 365."""
    assert jeoksu_from_deltas([], FY_S, FY_E, opening=1_000_000) == 1_000_000 * 365


def test_jeoksu_mid_year_loan():
    """7/1에 1,000만원 대여 → 적수 = 1,000만 × 184일 (7/1~12/31)."""
    j = jeoksu_from_deltas([(date(2025, 7, 1), 10_000_000)], FY_S, FY_E)
    assert j == 10_000_000 * 184


def test_jeoksu_loan_and_repayment():
    """3/1 대여 1,000만, 9/1 회수 1,000만 → 3/1~8/31 (184일)만 적수."""
    j = jeoksu_from_deltas(
        [(date(2025, 3, 1), 10_000_000), (date(2025, 9, 1), -10_000_000)],
        FY_S, FY_E,
    )
    assert j == 10_000_000 * 184


def test_jeoksu_floor_zero():
    """가수금이 가지급금보다 크면 음수 구간은 0 (영§53③ 상계 후 음수 불인정)."""
    j = jeoksu_from_deltas(
        [(date(2025, 1, 1), 5_000_000), (date(2025, 2, 1), -8_000_000)],
        FY_S, FY_E,
    )
    assert j == 5_000_000 * 31   # 1월만 양수


def test_deemed_interest_by_party_no_netting_across():
    """상대방별 계산 — 한 상대방의 약정이자 초과분이 다른 상대방과 통산되지 않음."""
    r = calc_deemed_interest_by_party(
        [
            ("갑", 3_650_000_000, 0),          # 인정이자 = 36.5억×4.6%/365 = 460,000
            ("을", 3_650_000_000, 10_000_000), # 약정이자가 커서 차액 음수 → 0
        ],
        rate=0.046, days=365,
    )
    assert r.parties[0].inclusion == 460_000
    assert r.parties[1].inclusion == 0
    assert r.inclusion_amount == 460_000     # 을의 초과 약정이자가 갑과 상계되지 않음


def test_deemed_interest_5pct_threshold():
    """영§88③: 차액이 시가의 5% 미만이고 3억 미만이면 적용 제외."""
    # 인정이자 460,000 / 약정이자 450,000 → 차액 10,000 = 시가의 2.2% → 제외
    r = calc_deemed_interest_by_party(
        [("갑", 3_650_000_000, 450_000)], rate=0.046, days=365,
    )
    assert not r.parties[0].applied
    assert r.inclusion_amount == 0
    # 약정이자 0 → 차액 = 시가의 100% ≥ 5% → 적용
    r2 = calc_deemed_interest_by_party(
        [("갑", 3_650_000_000, 0)], rate=0.046, days=365,
    )
    assert r2.parties[0].applied
