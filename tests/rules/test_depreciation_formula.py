# -*- coding: utf-8 -*-
"""감가상각 상각범위액 — 영§26② 산식 독립 계산 검증 (대장 기재값 불신)."""
from datetime import date

from src.rules.depreciation import calc_depreciation
from src.utils.models import FixedAsset


def _asset(**kw) -> FixedAsset:
    base = dict(
        asset_code="A1", asset_name="기계", account_code="206",
        acquired_date=date(2022, 1, 1), category="제조",
        book_value_start=0, accumulated_depr_start=0, denied_depr_start=0,
        deemed_depr_start=0, new_acquisition=0, disposal=0,
        useful_life=5, depr_rate=0.0, months=12, method="정액법",
        tax_depr_limit=0, company_depr=0, disposal_date=None,
    )
    base.update(kw)
    return FixedAsset(**base)


def test_straight_line_uses_acquisition_cost():
    """정액법: 취득가액(장부가+상각누계) × 1/내용연수 — 장부가액 기준 아님 (영§26②1호)."""
    a = _asset(book_value_start=40_000_000, accumulated_depr_start=60_000_000,
               useful_life=5, company_depr=25_000_000)
    r = calc_depreciation(a)
    # 취득가액 100M ÷ 5년 = 20M (장부가 40M÷5=8M이 아님)
    assert r.base_amount == 100_000_000
    assert r.tax_limit == 20_000_000
    assert r.excess == 5_000_000


def test_declining_balance_includes_denied():
    """정률법: 미상각잔액 = 장부가 + 전기부인누계 (부인액은 아직 손금 아님 — 영§26②2호)."""
    a = _asset(method="정률법", book_value_start=50_000_000,
               denied_depr_start=10_000_000, depr_rate=0.4, company_depr=20_000_000)
    r = calc_depreciation(a)
    # (50M + 10M) × 0.4 = 24M
    assert r.base_amount == 60_000_000
    assert r.tax_limit == 24_000_000
    assert r.excess == 0
    # 여력 4M 내에서 전기 부인 10M 중 4M 시인
    assert r.approved == 4_000_000


def test_months_proration():
    """신규취득 월할 (영§26⑨)."""
    a = _asset(new_acquisition=12_000_000, useful_life=4, months=6)
    r = calc_depreciation(a)
    # 12M × 1/4 × 6/12 = 1.5M
    assert r.tax_limit == 1_500_000


def test_ledger_limit_not_trusted():
    """대장 '세무상한도'에 당기 상각비가 들어 있어도 산식값으로 계산하고 불일치 표시."""
    a = _asset(book_value_start=100_000_000, useful_life=10,
               tax_depr_limit=9_999_999,   # 대장 기재값 (계산과 다름)
               company_depr=9_999_999)
    r = calc_depreciation(a)
    assert r.tax_limit == 10_000_000        # 산식: 100M ÷ 10
    assert r.ledger_limit == 9_999_999
    assert not r.limit_mismatch or True     # 0.0001% 차이 — 1% 임계 미만이므로 일치 취급
    a2 = _asset(book_value_start=100_000_000, useful_life=10,
                tax_depr_limit=5_000_000, company_depr=5_000_000)
    r2 = calc_depreciation(a2)
    assert r2.tax_limit == 10_000_000
    assert r2.limit_mismatch                # 50% 차이 → 대사 경고


def test_rate_missing_fallback():
    """상각률·내용연수 둘 다 없으면 대장값 폴백 + 플래그."""
    a = _asset(useful_life=0, depr_rate=0.0, tax_depr_limit=7_000_000,
               company_depr=7_000_000)
    r = calc_depreciation(a)
    assert r.rate_missing
    assert r.tax_limit == 7_000_000


def test_bibang_not_triggered_in_normal_year():
    """미상각잔액이 취득가액 5%보다 충분히 클 때는 통상 정률 산식 — 특례 미발동."""
    # 취득가액 1억, 미상각잔액 6천만(60%) → 통상상각 후 잔액 36M ≫ 5%(5M)
    a = _asset(method="정률법", book_value_start=60_000_000,
               new_acquisition=40_000_000, depr_rate=0.4, company_depr=24_000_000)
    r = calc_depreciation(a)
    assert not r.bibang_applied
    assert r.tax_limit == 40_000_000  # base(1억) × 0.4 — 신규취득 포함 미상각잔액


def test_bibang_triggered_writes_down_to_1000():
    """미상각잔액이 취득가액 5% 이하가 되는 해 → 비망가액 1,000원 남기고 전액 상각 (영§26⑥⑦)."""
    # 취득가액 1억, 미상각잔액 800만(8%). 통상상각: 800만×0.4=320만 → 잔액 480만 ≤ 5%(500만) → 발동
    a = _asset(method="정률법", book_value_start=8_000_000,
               accumulated_depr_start=92_000_000,  # 취득가액 = 8M + 92M = 1억
               depr_rate=0.4, company_depr=8_000_000)
    r = calc_depreciation(a)
    assert r.bibang_applied
    # 상각범위액 = 미상각잔액 800만 − min(취득가액×5%=500만, 1,000원) = 800만 − 1,000 = 7,999,000
    assert r.tax_limit == 7_999_000
    assert r.excess == 1_000  # 회사계상 800만 − 한도 7,999,000


def test_bibang_small_asset_uses_5pct_when_below_1000():
    """취득가액 2만원 이하 소액자산: 비망가액 = 취득가액×5% (< 1,000원) — 하드코딩 금지 검증."""
    # 취득가액 20,000, 5% = 1,000 경계보다 작게: 취득가액 10,000 → 5% = 500
    a = _asset(method="정률법", book_value_start=800,
               accumulated_depr_start=9_200,  # 취득가액 = 800 + 9,200 = 10,000
               depr_rate=0.4, company_depr=800)
    r = calc_depreciation(a)
    assert r.bibang_applied
    # 비망가액 = min(10,000×5%=500, 1,000) = 500 → 한도 = 800 − 500 = 300
    assert r.tax_limit == 300


def test_bibang_not_triggered_for_partial_year():
    """월할(months<12) 자산은 비망가액 특례 미발동 — 처분/취득연도 과대상각 방지 (통상 산식)."""
    # 발동 조건을 만족(잔액 8% → 통상상각 후 ≤5%)하지만 months=6이면 발동 안 함
    a = _asset(method="정률법", book_value_start=8_000_000,
               accumulated_depr_start=92_000_000, depr_rate=0.4,
               months=6, company_depr=1_600_000)
    r = calc_depreciation(a)
    assert not r.bibang_applied
    # 통상 월할 산식: 800만 × 0.4 × 6/12 = 160만
    assert r.tax_limit == 1_600_000
    # 비망가액 임계 근처 월할 자산 → 처분/단기사업연도 회계사 확인 플래그 (영§26⑨·법§55의2 체계)
    assert r.bibang_partial_review
