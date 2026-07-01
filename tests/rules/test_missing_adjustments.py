from datetime import date

from src.forms.summary_rows import adjustment_rows
from src.rules.coverage import run_coverage_check
from src.rules.legal_basis import ADJUSTMENT_LEGAL_BASIS
from src.rules.other_adjustments import (
    calc_unfair_transaction_general,
    calc_stock_based_compensation_excess,
    calc_construction_progress_adjustment,
    calc_treasury_stock_disposal,
    calc_proper_purpose_reserve,
)
from src.utils.models import TaxAdjustmentResult


def _result(**kw):
    return TaxAdjustmentResult(
        fiscal_year_start=date(2024, 1, 1),
        fiscal_year_end=date(2024, 12, 31),
        is_sme=True,
        **kw,
    )


def test_unfair_transaction_general_calc_and_wiring():
    assert calc_unfair_transaction_general(market_value=1_000, transaction_value=700) == 300
    rows, _ = adjustment_rows(_result(unfair_transaction=300))
    assert any(r[1] == "부당행위계산 부인" and r[2] == 300 for r in rows)


def test_stock_based_compensation_calc_and_wiring():
    assert calc_stock_based_compensation_excess(
        booked_expense=120_000_000, deductible_amount=90_000_000
    ) == 30_000_000
    rows, _ = adjustment_rows(_result(stock_compensation_excess=30_000_000))
    assert any("주식매수선택권" in r[1] and r[2] == 30_000_000 for r in rows)
    assert "stock_compensation_excess" in ADJUSTMENT_LEGAL_BASIS


def test_construction_progress_calc_and_wiring():
    assert calc_construction_progress_adjustment(tax_revenue=150, book_revenue=100) == 50
    assert calc_construction_progress_adjustment(tax_revenue=80, book_revenue=100) == -20
    add, ded = adjustment_rows(_result(
        construction_revenue_add=50,
        construction_revenue_excluded=20,
    ))
    assert any(r[1] == "작업진행률 수익인식" and r[2] == 50 for r in add)
    assert any(r[1] == "작업진행률 수익인식" and r[2] == 20 for r in ded)


def test_treasury_stock_disposal_calc_and_wiring():
    assert calc_treasury_stock_disposal(booked_gain=10, booked_loss=7) == (10, 7)
    add, ded = adjustment_rows(_result(
        treasury_stock_gain_excluded=10,
        treasury_stock_loss_disallowed=7,
    ))
    assert any(r[1] == "자기주식처분손실" and r[2] == 7 for r in add)
    assert any(r[1] == "자기주식처분이익" and r[2] == 10 for r in ded)


def test_proper_purpose_reserve_calc_and_wiring():
    assert calc_proper_purpose_reserve(booked_reserve=100, deductible_limit=80) == (80, 20)
    add, ded = adjustment_rows(_result(
        proper_purpose_reserve_deduction=80,
        proper_purpose_reserve_excess=20,
    ))
    assert any(r[1] == "고유목적사업준비금 한도초과" and r[2] == 20 for r in add)
    assert any(r[1] == "고유목적사업준비금" and r[2] == 80 for r in ded)


def test_coverage_catalog_contains_missing_adjustments():
    items = {r.item for r in run_coverage_check([], set())}
    assert "부당행위계산 부인" in items
    assert "주식매수선택권·주식기준보상 비용" in items
    assert "작업진행률 수익인식" in items
    assert "자기주식처분손익" in items
    assert "고유목적사업준비금" in items
