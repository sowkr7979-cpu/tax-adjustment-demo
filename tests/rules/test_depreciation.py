"""감가상각비 세무조정 단위 테스트."""
from datetime import date
import pytest
from src.rules.depreciation import calc_depreciation
from src.utils.models import FixedAsset


def _asset(**kwargs) -> FixedAsset:
    defaults = dict(
        asset_code="A001", asset_name="테스트자산",
        account_code="1", acquired_date=date(2020, 1, 1),
        category="판관비", book_value_start=100_000_000,
        accumulated_depr_start=0, denied_depr_start=0,
        deemed_depr_start=0, new_acquisition=0, disposal=0,
        useful_life=5, depr_rate=0.4, months=12,
        method="정률법", tax_depr_limit=0, company_depr=0,
        disposal_date=None,
    )
    defaults.update(kwargs)
    return FixedAsset(**defaults)


def test_declining_balance_excess():
    asset = _asset(
        method="정률법", depr_rate=0.4,
        book_value_start=50_000_000, company_depr=25_000_000,
    )
    r = calc_depreciation(asset)
    expected_limit = int(50_000_000 * 0.4 * 12 / 12)
    assert r.tax_limit == expected_limit
    assert r.excess == max(0, 25_000_000 - expected_limit)


def test_straight_line():
    asset = _asset(
        method="정액법", useful_life=5, depr_rate=0.0,   # 상각률 미기재 → 1/내용연수
        book_value_start=100_000_000, company_depr=20_000_000,
    )
    r = calc_depreciation(asset)
    assert r.tax_limit == int(100_000_000 / 5)
    assert r.excess == 0


def test_partial_month():
    asset = _asset(
        method="정률법", depr_rate=0.4,
        book_value_start=60_000_000, months=6, company_depr=15_000_000,
    )
    r = calc_depreciation(asset)
    expected = int(60_000_000 * 0.4 * 6 / 12)
    assert r.tax_limit == expected


def test_prior_denial_approved():
    """전기 부인누계가 있고 당기 여력이 생기면 시인(환입)."""
    asset = _asset(
        method="정률법", depr_rate=0.4,
        book_value_start=50_000_000, company_depr=10_000_000,
        denied_depr_start=5_000_000,
    )
    r = calc_depreciation(asset)
    # tax_limit = 20,000,000, company_depr = 10,000,000 → 여력 10,000,000
    # 시인 = min(5,000,000, 10,000,000) = 5,000,000
    assert r.approved == 5_000_000
    assert r.excess == 0


def test_explicit_tax_limit_not_trusted():
    """대장에 '세무상한도'가 기재돼 있어도 영§26② 산식으로 독립 계산하고 대사 표시.

    (회계 프로그램에 따라 이 컬럼에 당기 상각비가 들어 있는 경우가 있어 신뢰 불가)
    """
    asset = _asset(tax_depr_limit=30_000_000, company_depr=40_000_000)
    r = calc_depreciation(asset)
    # 산식: 정률법 100M × 0.4 = 40M (대장 30M 무시)
    assert r.tax_limit == 40_000_000
    assert r.ledger_limit == 30_000_000
    assert r.limit_mismatch          # 대사 경고 표시
    assert r.excess == 0
