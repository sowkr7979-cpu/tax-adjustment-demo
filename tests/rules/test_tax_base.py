"""과세표준·산출세액 단위 테스트."""
from datetime import date
import pytest
from src.rules.tax_base import calc_business_income, calc_tax_base, calc_gross_tax
from src.rules.tax_credit import calc_final_tax
from src.utils.models import TaxCredit


def test_business_income():
    assert calc_business_income(net_income=100, add_back=30, deduct=10) == 120


# ── 과세표준 ──────────────────────────────────────────────────────────────────

def test_tax_base_sme_full_deduction():
    """중소기업 이월결손금 100% 공제."""
    base, deducted = calc_tax_base(
        business_income=100_000_000,
        carryforward_losses=[(2020, 60_000_000)],
        is_sme=True,
        fiscal_year_end=date(2025, 12, 31),
    )
    assert deducted == 60_000_000
    assert base == 40_000_000


def test_tax_base_general_80pct():
    """일반법인 이월결손금 80% 한도."""
    base, deducted = calc_tax_base(
        business_income=100_000_000,
        carryforward_losses=[(2020, 100_000_000)],
        is_sme=False,
        fiscal_year_end=date(2025, 12, 31),
    )
    assert deducted == 80_000_000
    assert base == 20_000_000


def test_loss_carryforward_expired():
    """공제기한 초과 이월결손금은 공제 불가 (2009년 전 발생 = 5년)."""
    base, deducted = calc_tax_base(
        business_income=100_000_000,
        carryforward_losses=[(2000, 50_000_000)],  # 2000년 발생 → 5년 = 2005년 만료
        is_sme=True,
        fiscal_year_end=date(2025, 12, 31),
    )
    assert deducted == 0
    assert base == 100_000_000


def test_loss_carryforward_10yr_tier():
    """2009~2019 발생분은 10년 — 11년 경과 만료, 7년 경과 공제 가능."""
    # 2014년 발생 → 2025년이면 11년 경과 ≥ 10 → 만료
    _, expired = calc_tax_base(
        business_income=100_000_000,
        carryforward_losses=[(2014, 30_000_000)],
        is_sme=True,
        fiscal_year_end=date(2025, 12, 31),
    )
    assert expired == 0
    # 2018년 발생 → 2025년이면 7년 경과 < 10 → 공제 가능
    _, alive = calc_tax_base(
        business_income=100_000_000,
        carryforward_losses=[(2018, 30_000_000)],
        is_sme=True,
        fiscal_year_end=date(2025, 12, 31),
    )
    assert alive == 30_000_000


# ── 산출세액 ─────────────────────────────────────────────────────────────────

def test_gross_tax_2025_first_bracket():
    """2025년 개시, 과세표준 1억 → 9%."""
    gross, _ = calc_gross_tax(
        tax_base=100_000_000, fiscal_year_start=date(2025, 1, 1),
    )
    assert gross == int(100_000_000 * 0.09) - 0


def test_gross_tax_2026_first_bracket():
    """2026년 개시, 과세표준 1억 → 10%."""
    gross, _ = calc_gross_tax(
        tax_base=100_000_000, fiscal_year_start=date(2026, 1, 1),
    )
    assert gross == int(100_000_000 * 0.10) - 0


def test_gross_tax_2025_second_bracket():
    """2025년 개시, 과세표준 5억 → 2억×9% + 3억×19% - 2천만."""
    gross, _ = calc_gross_tax(
        tax_base=500_000_000, fiscal_year_start=date(2025, 1, 1),
    )
    expected = int(500_000_000 * 0.19) - 20_000_000
    assert gross == expected


# ── 최저한세 ─────────────────────────────────────────────────────────────────

def test_min_tax_sme():
    """중소기업 최저한세 7%."""
    r = calc_final_tax(
        gross_tax=50_000_000,
        tax_credits=[TaxCredit("중소기업감면", 40_000_000, True)],
        tax_base=700_000_000,
        is_sme=True,
    )
    expected_min = int(700_000_000 * 0.07)
    assert r["최저한세액"] == expected_min
    assert r["배제된_감면"] == max(0, expected_min - (50_000_000 - 40_000_000))


def test_min_tax_general_under_100b():
    """일반법인, 과세표준 100억(10,000,000,000) 이하 → 10%."""
    r = calc_final_tax(
        gross_tax=1_500_000_000,
        tax_credits=[TaxCredit("통합투자", 500_000_000, True)],
        tax_base=8_000_000_000,   # 80억 — 100억 이하 구간
        is_sme=False,
    )
    assert r["최저한세율"] == 0.10


def test_min_tax_general_over_100b():
    """일반법인, 과세표준 1,000억 초과 → 17%."""
    r = calc_final_tax(
        gross_tax=30_000_000_000,
        tax_credits=[],
        tax_base=200_000_000_000,
        is_sme=False,
    )
    assert r["최저한세율"] == 0.17


def test_post_min_tax_credit():
    """최저한세 미적용 감면은 최저한세 후 차감."""
    r = calc_final_tax(
        gross_tax=10_000_000,
        tax_credits=[
            TaxCredit("최저한세적용감면", 3_000_000, True),
            TaxCredit("최저한세외감면", 2_000_000, False),
        ],
        tax_base=100_000_000,
        is_sme=True,
    )
    # min_tax = 7,000,000 / after_min_credit = max(10M-3M, 7M) = 7M
    # post_credit = 7M - 2M = 5M
    assert r["최저한세_미적용_감면합계"] == 2_000_000
    assert r["최종_세액"] == max(0, r["최저한세액"] - 2_000_000)
