"""기업업무추진비 한도 계산 단위 테스트."""
import pytest
from src.rules.entertainment import calc_entertainment


def test_sme_base_limit():
    r = calc_entertainment(
        total_expense=40_000_000,
        card_expense=40_000_000,
        revenue=1_000_000_000,
        is_sme=True,
    )
    assert r.base_limit == 36_000_000
    assert r.total_limit == 36_000_000 + int(1_000_000_000 * 0.003)
    assert r.excess == max(0, 40_000_000 - r.total_limit)


def test_general_base_limit():
    r = calc_entertainment(
        total_expense=15_000_000,
        card_expense=15_000_000,
        revenue=500_000_000,
        is_sme=False,
    )
    assert r.base_limit == 12_000_000
    assert r.excess == max(0, 15_000_000 - r.total_limit)


def test_culture_expense_additional_limit():
    r = calc_entertainment(
        total_expense=50_000_000,
        card_expense=50_000_000,
        culture_expense=5_000_000,
        revenue=5_000_000_000,
        is_sme=True,
    )
    assert r.culture_limit > 0
    assert r.total_limit == r.base_limit + r.revenue_limit + r.culture_limit


def test_no_receipt_full_disallowance():
    r = calc_entertainment(
        total_expense=20_000_000,
        card_expense=15_000_000,
        no_receipt_expense=5_000_000,
        revenue=2_000_000_000,
        is_sme=True,
    )
    assert r.no_receipt_disallowed == 5_000_000


def test_revenue_over_10b():
    r = calc_entertainment(
        total_expense=50_000_000,
        card_expense=50_000_000,
        revenue=30_000_000_000,
        is_sme=False,
    )
    expected_rev = 30_000_000 + int((30_000_000_000 - 10_000_000_000) * 0.002)
    assert r.revenue_limit == expected_rev


def test_zero_expense():
    r = calc_entertainment(
        total_expense=0, card_expense=0,
        revenue=1_000_000_000, is_sme=True,
    )
    assert r.excess == 0
