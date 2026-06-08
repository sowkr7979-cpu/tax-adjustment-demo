"""가산세 산정 단위 테스트 — 국세기본법§47의2~4."""
from src.rules.penalty_surtax import (
    calc_no_filing_penalty,
    calc_under_report_penalty,
    calc_late_payment_penalty,
    aggregate_surtax,
)


# ── 무신고가산세 (§47의2) ─────────────────────────────────────────────────────

def test_no_filing_general_rate():
    """일반 무신고 20% (수입금액 기준이 더 작을 때)."""
    assert calc_no_filing_penalty(10_000_000, revenue=0) == 2_000_000


def test_no_filing_corp_revenue_floor():
    """법인은 수입금액×0.07%와 비교해 큰 금액 (§47의2②1호나목)."""
    # 세액 20% = 200만 vs 수입 100억×0.07% = 700만 → 700만
    assert calc_no_filing_penalty(10_000_000, revenue=10_000_000_000) == 7_000_000


def test_no_filing_fraud_and_offshore():
    """부정 40%, 역외부정 60%."""
    assert calc_no_filing_penalty(10_000_000, fraud=True) == 4_000_000
    assert calc_no_filing_penalty(10_000_000, fraud=True, offshore=True) == 6_000_000


# ── 과소신고가산세 (§47의3) ───────────────────────────────────────────────────

def test_under_report_general():
    """일반 과소신고 10%."""
    assert calc_under_report_penalty(10_000_000) == 1_000_000


def test_under_report_with_fraud_portion():
    """부정분 40% + 일반분 10%."""
    # 부정 400만×40% + 일반 600만×10% = 160만 + 60만 = 220만
    assert calc_under_report_penalty(10_000_000, fraud_portion=4_000_000) == 2_200_000


# ── 납부지연가산세 (§47의4) ───────────────────────────────────────────────────

def test_late_payment_daily():
    """미납세액 × 일수 × 22/100,000."""
    # 1,000만 × 100일 × 0.00022 = 220,000
    assert calc_late_payment_penalty(10_000_000, 100) == 220_000
    assert calc_late_payment_penalty(10_000_000, 0) == 0
    assert calc_late_payment_penalty(0, 100) == 0


# ── 합산 ─────────────────────────────────────────────────────────────────────

def test_aggregate_surtax_total():
    r = aggregate_surtax(
        under_report_tax=10_000_000, under_report_fraud_portion=4_000_000,
        unpaid_tax=10_000_000, unpaid_days=100,
        other_manual=500_000,
    )
    assert r.under_report == 2_200_000
    assert r.late_payment == 220_000
    assert r.other_manual == 500_000
    assert r.total == 2_200_000 + 220_000 + 500_000
