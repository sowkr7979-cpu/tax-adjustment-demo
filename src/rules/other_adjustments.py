"""기타 세무조정 — 벌과금(법법§21), 임원상여(법법§26), 외화환산(법법§42)."""
from dataclasses import dataclass


@dataclass
class ForexResult:
    account_code: str
    foreign_currency: str
    foreign_amount: float
    period_end_rate: float
    book_value: int
    tax_value: int
    adjustment: int     # 양수: 익금산입, 음수: 손금산입


def calc_penalty(penalty_total: int) -> int:
    """벌과금·과태료: 전액 손금불산입 (법§21)."""
    return penalty_total


def calc_officer_bonus_excess(
    *,
    paid_bonus: int,
    approved_limit: int,
) -> int:
    """임원 상여금 정관·주총 한도 초과분 손금불산입 (법§26)."""
    return max(0, paid_bonus - approved_limit)


def calc_officer_retirement_excess(
    *,
    paid_amount: int,
    tenure_years: float,
    last_salary: int,
    allowance_rate: float = 0.1,
) -> int:
    """
    임원 퇴직금 한도초과 계산.
    한도 = 직전 1년간 총급여액 × 1/10 × 근속연수
    """
    limit = int(last_salary * allowance_rate * tenure_years)
    return max(0, paid_amount - limit)


def calc_forex_adjustment(
    *,
    account_code: str,
    foreign_currency: str,
    foreign_amount: float,
    period_end_rate: float,
    book_value: int,
) -> ForexResult:
    """외화자산·부채 기말 평가차손익 세무조정 (법§42)."""
    tax_value = int(foreign_amount * period_end_rate)
    adjustment = tax_value - book_value
    return ForexResult(
        account_code=account_code,
        foreign_currency=foreign_currency,
        foreign_amount=foreign_amount,
        period_end_rate=period_end_rate,
        book_value=book_value,
        tax_value=tax_value,
        adjustment=adjustment,
    )
