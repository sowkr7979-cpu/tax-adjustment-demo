"""소득금액 → 과세표준 → 산출세액 계산."""
from __future__ import annotations
from datetime import date
from dataclasses import dataclass

from src.utils.constants import (
    get_tax_rate_table,
    LOSS_CARRYFORWARD_SME_RATE,
    LOSS_CARRYFORWARD_GENERAL_RATE,
)
from src.utils.models import TaxAdjustmentResult


@dataclass
class TaxBaseResult:
    net_income: int
    add_back: int
    deduct: int
    business_income: int
    loss_deduction: int
    non_taxable: int
    income_deduction: int
    tax_base: int
    tax_rate_table_from: date
    gross_tax: int


def calc_business_income(
    *,
    net_income: int,
    add_back: int,
    deduct: int,
) -> int:
    return net_income + add_back - deduct


def eligible_carryforward_total(
    carryforward_losses: list[tuple[int, int]],
    fiscal_year_end: date,
) -> int:
    """공제기한 내 이월결손금 합계 (법§13, 부칙).

    공제기한: 2020.1.1 이후 개시 사업연도 발생분 15년,
      2009.1.1~2019.12.31 발생분 10년, 그 이전 발생분 5년.
    """
    total = 0
    for origin_year, amount in carryforward_losses:
        if origin_year >= 2020:
            expiry_years = 15
        elif origin_year >= 2009:
            expiry_years = 10
        else:
            expiry_years = 5
        if (fiscal_year_end.year - origin_year) >= expiry_years:
            continue
        total += amount
    return total


def calc_tax_base(
    *,
    business_income: int,
    carryforward_losses: list[tuple[int, int]],  # [(발생연도, 금액)]
    is_sme: bool,
    non_taxable: int = 0,
    income_deduction: int = 0,
    fiscal_year_end: date,
) -> tuple[int, int]:
    """
    반환: (과세표준, 실제 공제된 이월결손금)
    carryforward_losses: 발생 연도 오래된 것부터 정렬하여 전달
    이월결손금 공제기한 (법§13, 부칙): 2020.1.1 이후 개시 사업연도 발생분 15년,
      2009.1.1~2019.12.31 발생분 10년, 그 이전 발생분 5년
    """
    limit_rate = LOSS_CARRYFORWARD_SME_RATE if is_sme else LOSS_CARRYFORWARD_GENERAL_RATE
    max_deductible = int(business_income * limit_rate)

    total_loss = eligible_carryforward_total(carryforward_losses, fiscal_year_end)

    actual_deduction = min(total_loss, max_deductible, business_income)
    tax_base = max(0, business_income - actual_deduction - non_taxable - income_deduction)
    return tax_base, actual_deduction


def calc_gross_tax(
    *,
    tax_base: int,
    fiscal_year_start: date,
) -> tuple[int, date]:
    """산출세액 = 과세표준 × 세율 - 누진공제. 반환: (세액, 적용 세율 테이블 시행일)"""
    table = get_tax_rate_table(fiscal_year_start)
    gross = 0
    for bracket in table.brackets:
        if bracket.upper is None or tax_base <= bracket.upper:
            gross = int(tax_base * bracket.rate) - bracket.deduction
            break
    return max(0, gross), table.effective_from


def compute_all(
    result: TaxAdjustmentResult,
    *,
    net_income: int,
    carryforward_losses: list[tuple[int, int]],
    fiscal_year_end: date,
    tax_credits: list,
    surtax: int = 0,
    prepaid_tax: int = 0,
) -> TaxAdjustmentResult:
    """TaxAdjustmentResult의 집계 필드를 채운다."""
    from src.rules.tax_credit import calc_final_tax

    result.net_income = net_income
    result.business_income = calc_business_income(
        net_income=net_income,
        add_back=result.total_add_back,
        deduct=result.total_deduct,
    )
    result.tax_base, _ = calc_tax_base(
        business_income=result.business_income,
        carryforward_losses=carryforward_losses,
        is_sme=result.is_sme,
        fiscal_year_end=fiscal_year_end,
    )
    result.gross_tax, _ = calc_gross_tax(
        tax_base=result.tax_base,
        fiscal_year_start=result.fiscal_year_start,
    )
    credit_result = calc_final_tax(
        gross_tax=result.gross_tax,
        tax_credits=tax_credits,
        tax_base=result.tax_base,
        is_sme=result.is_sme,
        surtax=surtax,
        prepaid_tax=prepaid_tax,
    )
    result.min_tax = credit_result["최저한세액"]
    result.tax_credits_min_subject = credit_result["최저한세_적용_감면합계"]
    result.tax_credits_post_min = credit_result["최저한세_미적용_감면합계"]
    result.excluded_credits = credit_result["배제된_감면"]
    result.surtax = surtax
    result.prepaid_tax = prepaid_tax
    result.final_tax_due = credit_result["차감납부세액"]
    return result
