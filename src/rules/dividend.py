"""수입배당금 익금불산입 — 법인세법 제18조의2."""
from dataclasses import dataclass


# 출자비율별 익금불산입 비율 (법§18의2①)
_EXCLUSION_RATE = [
    (1.00, 1.00),   # 100%: 완전자법인 → 전액 익금불산입
    (0.80, 0.80),   # 80% 이상
    (0.20, 0.40),   # 20% 이상 80% 미만
    (0.00, 0.20),   # 20% 미만
]


@dataclass
class DividendResult:
    dividend_income: int
    ownership_ratio: float
    exclusion_rate: float
    exclusion_amount: int
    taxable_amount: int


def calc_dividend_exclusion(
    *,
    dividend_income: int,
    ownership_ratio: float,
) -> DividendResult:
    """배당 수취법인의 주식 보유비율에 따른 익금불산입 비율 적용."""
    rate = 0.0
    for threshold, excl_rate in _EXCLUSION_RATE:
        if ownership_ratio >= threshold:
            rate = excl_rate
            break
    exclusion = int(dividend_income * rate)
    return DividendResult(
        dividend_income=dividend_income,
        ownership_ratio=ownership_ratio,
        exclusion_rate=rate,
        exclusion_amount=exclusion,
        taxable_amount=dividend_income - exclusion,
    )
