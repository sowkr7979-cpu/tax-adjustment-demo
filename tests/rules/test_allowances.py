"""충당금·퇴직연금 단위 테스트."""
from src.rules.allowances import (
    calc_retirement_allowance, calc_bad_debt_allowance, calc_pension_deduction,
)


def test_retirement_allowance_full_denial():
    """퇴직급여충당금 현행 한도 0% — 설정액 전액 부인."""
    r = calc_retirement_allowance(company_balance=30_000_000)
    assert r.statutory_limit == 0
    assert r.excess == 30_000_000


def test_bad_debt_floor_1pct():
    """대손충당금 한도 = 채권 × max(1%, 실적률)."""
    r = calc_bad_debt_allowance(
        receivable_balance=1_000_000_000, actual_bad_rate=0.005, company_balance=15_000_000,
    )
    assert r.applied_rate == 0.01
    assert r.limit == 10_000_000
    assert r.excess == 5_000_000


# ── 퇴직연금 부담금 손금산입 (영§44의2④) ──────────────────────────────────────

def test_pension_deduction_estimate_binding():
    """추계액 한도가 예치금보다 작을 때 — 추계액 기준으로 손금산입."""
    r = calc_pension_deduction(
        estimate=80_000_000,
        fund_balance=100_000_000,
        prior_deducted=30_000_000,
    )
    # 추계액 한도 80M < 예치금 100M → ceiling 80M, 당기 = 80M − 30M = 50M
    assert r.estimate_limit == 80_000_000
    assert r.ceiling == 80_000_000
    assert r.deduction == 50_000_000


def test_pension_deduction_fund_binding():
    """예치금이 추계액보다 작을 때 — 예치금이 한도를 제한."""
    r = calc_pension_deduction(
        estimate=100_000_000,
        fund_balance=70_000_000,
        prior_deducted=20_000_000,
    )
    # ceiling = min(100M, 70M) = 70M, 당기 = 70M − 20M = 50M
    assert r.ceiling == 70_000_000
    assert r.deduction == 50_000_000


def test_pension_deduction_provision_reduces_limit():
    """세무상 퇴직급여충당금 잔액은 추계액 한도에서 차감."""
    r = calc_pension_deduction(
        estimate=100_000_000,
        fund_balance=100_000_000,
        tax_provision_balance=40_000_000,
    )
    # 추계액 한도 = 100M − 40M = 60M
    assert r.estimate_limit == 60_000_000
    assert r.deduction == 60_000_000


def test_pension_deduction_no_negative():
    """직전 손금누계가 한도를 넘으면 당기 손금산입 0 (음수 방지)."""
    r = calc_pension_deduction(
        estimate=50_000_000,
        fund_balance=50_000_000,
        prior_deducted=60_000_000,
    )
    assert r.deduction == 0
