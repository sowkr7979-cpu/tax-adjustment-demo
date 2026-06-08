"""과세표준·산출세액 단위 테스트."""
from datetime import date
import pytest
from src.rules.tax_base import (
    calc_business_income, calc_tax_base, calc_gross_tax, compute_all,
    calc_land_transfer_tax,
)
from src.rules.tax_credit import calc_final_tax
from src.utils.models import TaxCredit, TaxAdjustmentResult


def test_business_income():
    assert calc_business_income(net_income=100, add_back=30, deduct=10) == 120


def test_compute_all_pipeline_applies_credits_surtax_prepaid():
    """compute_all이 세액공제·가산세·기납부세액을 차감납부세액에 반영한다 (Critical#1 회귀)."""
    r = TaxAdjustmentResult(
        fiscal_year_start=date(2024, 1, 1),
        fiscal_year_end=date(2024, 12, 31),
        is_sme=True,
    )
    compute_all(
        r,
        net_income=200_000_000,        # 가산·차감조정 0 → 과세표준 2억
        carryforward_losses=[],
        fiscal_year_end=date(2024, 12, 31),
        tax_credits=[TaxCredit(name="R&D세액공제", amount=3_000_000, subject_to_min_tax=False)],
        surtax=1_000_000,
        prepaid_tax=2_000_000,
    )
    assert r.tax_base == 200_000_000
    assert r.tax_credits_post_min == 3_000_000
    assert r.surtax == 1_000_000
    assert r.prepaid_tax == 2_000_000
    # 산출세액 − 최저한세미적용 감면 + 가산세 − 기납부세액 (산출세액 > 최저한세이므로 배제 없음)
    assert r.final_tax_due == max(
        0, r.gross_tax - 3_000_000 + 1_000_000 - 2_000_000
    )
    assert r.final_tax_due < r.gross_tax   # 순 차감 효과 확인


def test_farm_surtax_only_on_taxable_credits():
    """농특세 = 농특세 과세대상 감면(farm_surtax_taxable)만 × 20% (농특세법§5①·§4 비과세)."""
    r = TaxAdjustmentResult(
        fiscal_year_start=date(2024, 1, 1),
        fiscal_year_end=date(2024, 12, 31),
        is_sme=True,
    )
    compute_all(
        r,
        net_income=500_000_000,
        carryforward_losses=[],
        fiscal_year_end=date(2024, 12, 31),
        tax_credits=[
            # 농특세 과세대상 (예: 통합투자세액공제) 10,000,000
            TaxCredit(name="통합투자세액공제", amount=10_000_000,
                      subject_to_min_tax=True, farm_surtax_taxable=True),
            # 농특세 비과세 (예: 중소기업특별세액감면 조특§7) 5,000,000
            TaxCredit(name="중소기업특별세액감면", amount=5_000_000,
                      subject_to_min_tax=False, farm_surtax_taxable=False),
        ],
    )
    # 농특세 = 10,000,000 × 20% = 2,000,000 (비과세 감면 5,000,000은 제외)
    assert r.farm_surtax == 2_000_000


def test_farm_surtax_excludes_minimum_tax_disallowed():
    """최저한세로 배제된 감면은 실제 감면받지 못하므로 농특세 과세표준에서 제외."""
    r = TaxAdjustmentResult(
        fiscal_year_start=date(2024, 1, 1),
        fiscal_year_end=date(2024, 12, 31),
        is_sme=True,
    )
    # 과세표준 1억 → 산출세액 9,000,000, 최저한세 7,000,000.
    # 과세대상 감면 5,000,000 (전액 최저한세 적용) → 감면후 4,000,000 < 7,000,000
    #   → 3,000,000 배제 → 실제 감면 2,000,000 → 농특세 = 2,000,000 × 20% = 400,000
    compute_all(
        r,
        net_income=100_000_000,
        carryforward_losses=[],
        fiscal_year_end=date(2024, 12, 31),
        tax_credits=[
            TaxCredit(name="투자세액공제", amount=5_000_000,
                      subject_to_min_tax=True, farm_surtax_taxable=True),
        ],
    )
    assert r.excluded_credits == 3_000_000
    assert r.farm_surtax == 400_000


def test_land_transfer_tax_rates():
    """법§55의2 세율: 비사업용토지 10%(미등기 40%)·주택별장 20%·조합원입주권분양권 20%."""
    assert calc_land_transfer_tax(100_000_000, "비사업용토지") == 10_000_000
    assert calc_land_transfer_tax(100_000_000, "비사업용토지", unregistered=True) == 40_000_000
    assert calc_land_transfer_tax(100_000_000, "주택별장") == 20_000_000
    assert calc_land_transfer_tax(100_000_000, "주택별장", unregistered=True) == 40_000_000
    assert calc_land_transfer_tax(100_000_000, "조합원입주권분양권") == 20_000_000
    assert calc_land_transfer_tax(0, "비사업용토지") == 0
    assert calc_land_transfer_tax(-5_000, "비사업용토지") == 0


def test_compute_all_adds_land_transfer_tax():
    """토지등 양도소득 법인세는 최저한세·감면과 무관하게 차감납부세액에 추가된다."""
    r = TaxAdjustmentResult(
        fiscal_year_start=date(2024, 1, 1),
        fiscal_year_end=date(2024, 12, 31),
        is_sme=True,
    )
    compute_all(
        r,
        net_income=200_000_000,
        carryforward_losses=[],
        fiscal_year_end=date(2024, 12, 31),
        tax_credits=[],
        land_transfer_tax=calc_land_transfer_tax(50_000_000, "비사업용토지"),  # 5,000,000
    )
    assert r.land_transfer_tax == 5_000_000
    assert r.final_tax_due == r.gross_tax + 5_000_000  # 일반 산출세액 + §55의2


def test_compute_all_empty_credits_unchanged():
    """세액공제·가산세·기납부세액이 없으면 차감납부세액 = 산출세액 (최저한세 미달 없을 때)."""
    r = TaxAdjustmentResult(
        fiscal_year_start=date(2024, 1, 1),
        fiscal_year_end=date(2024, 12, 31),
        is_sme=True,
    )
    compute_all(
        r,
        net_income=200_000_000,
        carryforward_losses=[],
        fiscal_year_end=date(2024, 12, 31),
        tax_credits=[],
    )
    assert r.final_tax_due == r.gross_tax


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
