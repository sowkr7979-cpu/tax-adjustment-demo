"""조특 세액공제·감면 카탈로그·산식 구조 단위 테스트."""
from src.rules.tax_credit_catalog import (
    lookup_credit_spec,
    calc_sme_special_reduction,
    calc_rnd_credit,
    calc_integrated_investment_credit,
)


# ── 분류 카탈로그 (최저한세·농특세 자동판정) ──────────────────────────────────

def test_sme_special_reduction_classification():
    """중소기업특별세액감면: 최저한세 적용·농특세 비과세 (농특세법§4 3호)."""
    spec = lookup_credit_spec("중소기업특별세액감면")
    assert spec is not None
    assert spec.subject_to_min_tax is True
    assert spec.farm_surtax_taxable is False


def test_integrated_investment_classification():
    """통합투자세액공제: 최저한세 적용·농특세 과세."""
    spec = lookup_credit_spec("통합투자세액공제")
    assert spec.subject_to_min_tax is True
    assert spec.farm_surtax_taxable is True


def test_lookup_partial_match_and_miss():
    assert lookup_credit_spec("통합투자") is not None      # 부분 일치
    assert lookup_credit_spec("존재하지않는공제") is None


# ── 산식 구조 ────────────────────────────────────────────────────────────────

def test_sme_special_reduction_amount_and_cap():
    """산출세액 × 감면율, 한도 적용."""
    assert calc_sme_special_reduction(business_income_tax=100_000_000, reduction_rate=0.20) == 20_000_000
    # 한도 1,500만 → 2,000만이 한도로 제한
    assert calc_sme_special_reduction(
        business_income_tax=100_000_000, reduction_rate=0.20, cap=15_000_000,
    ) == 15_000_000


def test_rnd_credit_picks_larger_of_current_or_increase():
    """당기분과 증가분 중 큰 값."""
    # 당기분 = 1억×25% = 2,500만 / 증가분 = 4,000만×40% = 1,600만 → 당기분 채택
    assert calc_rnd_credit(
        current_expense=100_000_000, rate=0.25,
        increase_expense=40_000_000, increase_rate=0.40,
    ) == 25_000_000


def test_integrated_investment_base_plus_extra():
    """기본공제 + 직전 3년 평균 초과분 추가공제."""
    # 기본 = 1억×10% = 1,000만 / 추가 = (1억 − 6,000만)×3% = 120만
    assert calc_integrated_investment_credit(
        investment=100_000_000, base_rate=0.10,
        prior_3yr_avg=60_000_000, extra_rate=0.03,
    ) == 10_000_000 + 1_200_000


def test_integrated_investment_no_extra_when_below_average():
    """당기 투자가 직전 3년 평균 이하면 추가공제 0."""
    assert calc_integrated_investment_credit(
        investment=50_000_000, base_rate=0.10,
        prior_3yr_avg=80_000_000, extra_rate=0.03,
    ) == 5_000_000
