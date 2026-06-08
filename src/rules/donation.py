"""기부금 한도 계산 — 법인세법 제24조."""
from dataclasses import dataclass


@dataclass
class DonationResult:
    special_donation: int
    general_donation: int
    nondesignated_donation: int
    adjusted_income: int
    special_limit: int
    special_excess: int
    general_limit: int
    general_excess: int
    nondesignated_disallowed: int
    total_disallowed: int
    carryforward_special: int   # 이월공제 가능 (10년)
    carryforward_general: int   # 이월공제 가능 (10년)


def calc_donation(
    *,
    special_donation: int,
    general_donation: int,
    nondesignated_donation: int,
    adjusted_income: int,
    carryforward_loss_deduction: int = 0,
    prior_special_carryforward: int = 0,
    prior_general_carryforward: int = 0,
    is_social_enterprise: bool = False,
) -> DonationResult:
    """기부금 한도 — 법§24②2호·③2호 (law.go.kr 원문 확인, efYd=2024-12-31).

    adjusted_income: 기준소득금액
        = 차가감소득금액 + 특례기부금 + 일반기부금
          (= 특례·일반기부금을 손금에 산입하기 전의 해당 사업연도 소득금액, 법§24②2호)
    carryforward_loss_deduction: 법§13①1호 이월결손금 공제액 — 한도 base에서 차감
    is_social_enterprise: 사회적기업이면 일반기부금 한도율 20% (그 외 10%, 법§24③2호)
    """
    # 한도 기준 = 기준소득금액 − 이월결손금 (법§24②2호·③2호)
    limit_base = max(0, adjusted_income - carryforward_loss_deduction)

    # 특례기부금: limit_base × 50% (이월분 우선공제 — 법§24⑥)
    special_limit = int(limit_base * 0.5)
    special_total = special_donation + prior_special_carryforward
    special_excess = max(0, special_total - special_limit)
    special_allowed = special_total - special_excess

    # 일반기부금: (limit_base − 특례 손금산입액) × 10% (사회적기업 20%)
    general_base = max(0, limit_base - special_allowed)
    general_rate = 0.20 if is_social_enterprise else 0.10
    general_limit = int(general_base * general_rate)
    general_total = general_donation + prior_general_carryforward
    general_excess = max(0, general_total - general_limit)

    return DonationResult(
        special_donation=special_donation,
        general_donation=general_donation,
        nondesignated_donation=nondesignated_donation,
        adjusted_income=adjusted_income,
        special_limit=special_limit,
        special_excess=special_excess,
        general_limit=general_limit,
        general_excess=general_excess,
        nondesignated_disallowed=nondesignated_donation,
        total_disallowed=special_excess + general_excess + nondesignated_donation,
        carryforward_special=special_excess,
        carryforward_general=general_excess,
    )
