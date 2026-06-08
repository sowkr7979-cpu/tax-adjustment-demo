"""기업업무추진비(접대비) 한도 계산 — 법인세법 제25조.

법§25④: 한도 = 기본금액(월수 안분) + 수입금액 × 적용률
법§25⑤: 부동산임대업 주업 등 특정법인(영§42② 요건 모두 충족)은
        ④ 각 호 합계액의 100분의 50만 한도로 인정 (2018.12.24 신설)
"""
from dataclasses import dataclass

from src.utils.constants import ENTERTAINMENT_BASE_SME, ENTERTAINMENT_BASE_GENERAL


@dataclass
class EntertainmentResult:
    total_expense: int
    card_expense: int
    culture_expense: int
    traditional_expense: int
    base_limit: int
    revenue_limit: int
    culture_limit: int
    traditional_limit: int
    total_limit: int
    no_receipt_disallowed: int   # 증빙불비 (적격증빙 미수취 건당 3만원 초과분, 법§25②)
    excess: int                  # 한도초과액
    is_specified_corp: bool = False  # 특정법인 (법§25⑤ — 한도 50%)
    months: int = 12                 # 사업연도 월수 (기본금액 안분)
    related_revenue: int = 0         # 특수관계인 거래 수입금액 (법§25④2호 단서 — 적용률 산출액의 10%)
    general_revenue_limit: int = 0   # 일반 수입금액분 한도
    related_revenue_limit: int = 0   # 특수관계 수입금액분 한도 (×10% 적용 후)


def _revenue_limit(revenue: int) -> int:
    if revenue <= 10_000_000_000:
        return int(revenue * 0.003)
    elif revenue <= 50_000_000_000:
        return 30_000_000 + int((revenue - 10_000_000_000) * 0.002)
    return 110_000_000 + int((revenue - 50_000_000_000) * 0.0003)


def calc_entertainment(
    *,
    total_expense: int,
    card_expense: int,
    culture_expense: int = 0,
    traditional_expense: int = 0,
    no_receipt_expense: int = 0,
    revenue: int,
    is_sme: bool,
    is_specified_corp: bool = False,
    months: int = 12,
    related_revenue: int = 0,
) -> EntertainmentResult:
    """
    total_expense: 기업업무추진비 합계 (증빙불비 포함)
    card_expense: 법인카드·신용카드 지출
    culture_expense: 문화비
    traditional_expense: 전통시장 지출
    no_receipt_expense: 증빙불비 지출 (적격증빙 미수취 건당 3만원 초과) → 전액 손금불산입
    is_specified_corp: 특정법인 (영§42②: 지배주주 50% 초과 + 부동산임대 주업 등
                       + 상시근로자 5인 미만) → 한도 합계 × 50% (법§25⑤)
    months: 사업연도 월수 — 기본금액은 월수/12로 안분 (법§25④1호)
    related_revenue: 특수관계인 거래 수입금액 — 법§25④2호 단서:
                     해당 수입금액에 적용률을 곱한 금액의 100분의 10만 한도 인정.
                     (특수관계 수입금액은 높은 구간부터 적용하는 통상 계산:
                      한도 = f(일반수입금액) + [f(전체) − f(일반)] × 10%)
    """
    base_annual = ENTERTAINMENT_BASE_SME if is_sme else ENTERTAINMENT_BASE_GENERAL
    base = int(base_annual * months / 12)
    related_revenue = min(max(0, related_revenue), max(0, revenue))
    general_revenue = max(0, revenue - related_revenue)
    general_limit = _revenue_limit(general_revenue)
    related_limit = int((_revenue_limit(revenue) - general_limit) * 0.10)
    rev_limit = general_limit + related_limit
    base_rev = base + rev_limit
    # 법§25⑤ — 특정법인은 ④ 각 호 합계액의 50%만 인정
    if is_specified_corp:
        base_rev = base_rev // 2

    culture_limit = min(culture_expense, base_rev)
    traditional_limit = min(traditional_expense, base_rev)
    total_limit = base_rev + culture_limit + traditional_limit

    eligible = total_expense - no_receipt_expense
    excess = max(0, eligible - total_limit)

    return EntertainmentResult(
        total_expense=total_expense,
        card_expense=card_expense,
        culture_expense=culture_expense,
        traditional_expense=traditional_expense,
        base_limit=base,
        revenue_limit=rev_limit,
        culture_limit=culture_limit,
        traditional_limit=traditional_limit,
        total_limit=total_limit,
        no_receipt_disallowed=no_receipt_expense,
        excess=excess,
        is_specified_corp=is_specified_corp,
        months=months,
        related_revenue=related_revenue,
        general_revenue_limit=general_limit,
        related_revenue_limit=related_limit,
    )
