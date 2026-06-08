"""충당금 세무조정 — 퇴직급여충당금(법법§33), 대손충당금(법법§34)."""
from dataclasses import dataclass


@dataclass
class RetirementAllowanceResult:
    company_balance: int
    statutory_limit: int   # 현행 0%
    excess: int


@dataclass
class PensionDeductionResult:
    estimate: int               # 퇴직급여추계액 (일시퇴직·보험수리 중 큰 금액)
    tax_provision_balance: int  # 기말 세무상 퇴직급여충당금 잔액
    fund_balance: int           # 기말 퇴직연금 운용자산(사외 예치금) 잔액
    prior_deducted: int         # 직전까지 손금산입 누계 (영§44의2④2호)
    estimate_limit: int         # 추계액 기준 한도 = 추계액 − 세무상 퇴충
    ceiling: int                # min(추계액 한도, 예치금 잔액)
    deduction: int              # 당기 손금산입액 (△유보)


@dataclass
class BadDebtAllowanceResult:
    receivable_balance: int
    actual_bad_rate: float
    applied_rate: float
    limit: int
    company_balance: int
    excess: int


def calc_retirement_allowance(
    *,
    company_balance: int,
    pension_asset: int = 0,
) -> RetirementAllowanceResult:
    """퇴직급여충당금 한도 = 0% (현행 법령§60). 전액 손금불산입."""
    statutory_limit = 0
    excess = max(0, company_balance - statutory_limit)
    return RetirementAllowanceResult(
        company_balance=company_balance,
        statutory_limit=statutory_limit,
        excess=excess,
    )


def calc_pension_deduction(
    *,
    estimate: int,
    fund_balance: int,
    prior_deducted: int = 0,
    tax_provision_balance: int = 0,
) -> PensionDeductionResult:
    """확정급여형(DB) 퇴직연금 부담금 손금산입 — 영§44의2④ (law.go.kr 원문 확인).

    영§44의2④: 손금산입 한도 = [제1호 또는 제1호의2 중 큰 금액] − 제2호
      제1호    = 일시퇴직기준 추계액 − 해당 사업연도종료일 현재 퇴직급여충당금
      제1호의2 = 보험수리기준 추계액(근퇴법§16①1호 등) − 퇴직급여충당금
      제2호    = 직전 사업연도종료일까지 지급한 부담금 (= 기 손금산입 누계)
    당기 손금산입액 = min(추계액 한도, 예치금 잔액) − 직전까지 손금산입 누계.
      (확정기여형 DC 부담금은 영§44의2③ 전액 손금 — 본 함수 범위 밖)
      음수이면 0 (전기 과다 손금산입분 익금산입은 별도 검토 — 본 함수 범위 밖).

    estimate: 일시퇴직·보험수리 추계액 중 큰 금액 (회계사 입력)
    fund_balance: 기말 퇴직연금 운용자산(사외 예치금) 잔액
    prior_deducted: 직전 사업연도종료일까지 손금산입한 부담금 누계 (영§44의2④2호)
    tax_provision_balance: 기말 세무상 퇴직급여충당금 잔액 (현행 한도 0% → 통상 0)
    """
    estimate_limit = max(0, estimate - tax_provision_balance)
    ceiling = min(estimate_limit, fund_balance)
    deduction = max(0, ceiling - prior_deducted)
    return PensionDeductionResult(
        estimate=estimate,
        tax_provision_balance=tax_provision_balance,
        fund_balance=fund_balance,
        prior_deducted=prior_deducted,
        estimate_limit=estimate_limit,
        ceiling=ceiling,
        deduction=deduction,
    )


def calc_bad_debt_allowance(
    *,
    receivable_balance: int,
    actual_bad_rate: float,
    company_balance: int,
) -> BadDebtAllowanceResult:
    """대손충당금: 채권잔액 × max(1%, 대손실적률)."""
    applied_rate = max(0.01, actual_bad_rate)
    limit = int(receivable_balance * applied_rate)
    excess = max(0, company_balance - limit)
    return BadDebtAllowanceResult(
        receivable_balance=receivable_balance,
        actual_bad_rate=actual_bad_rate,
        applied_rate=applied_rate,
        limit=limit,
        company_balance=company_balance,
        excess=excess,
    )
