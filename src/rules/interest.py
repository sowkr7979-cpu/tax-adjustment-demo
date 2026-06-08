"""지급이자 손금불산입 — 법인세법 제28조."""
from dataclasses import dataclass


@dataclass
class InterestDisallowanceResult:
    total_interest: int
    unknown_creditor_disallowed: int   # §28①1호: 채권자불분명 사채이자 → 기타사외유출(원천세분)·대표자상여
    nonreal_name_disallowed: int       # §28①2호: 비실명 채권·증권이자 → 기타사외유출(원천세분)·대표자상여
    construction_capitalized: int      # §28①3호: 건설자금이자 → 유보(취득원가 가산)
    non_business_ratio: float
    non_business_disallowed: int       # §28①4호: 업무무관자산 → 기타사외유출
    total_disallowed: int


def calc_interest_disallowance(
    *,
    total_interest: int,
    unknown_creditor_interest: int,
    construction_interest: int,
    non_business_asset: int,
    total_asset: int,
    nonreal_name_interest: int = 0,
) -> InterestDisallowanceResult:
    """
    적용 순서 (법§28①, ③ — 영§55 우선순위):
    1호 채권자불분명 사채이자 → 전액 손금불산입
    2호 비실명 채권·증권이자(소득세법§16①1·2·5·8호 중 지급받은 자 불분명) → 전액 손금불산입
    3호 건설자금이자 → 자본화 처리 (유보)
    4호 업무무관자산 비율 = 1·2·3호 제외 기준이자로 산정

    nonreal_name_interest (2호): law.go.kr 법§28①2호 원문 확인 — 채권자불분명(1호)과
      별개의 독립 손금불산입 항목. 소득처분은 1호와 동일(원천세 상당액 기타사외유출, 잔액 대표자상여).
    """
    after_excl = max(
        0,
        total_interest - unknown_creditor_interest - nonreal_name_interest - construction_interest,
    )
    ratio = non_business_asset / total_asset if total_asset else 0.0
    non_biz_disallowed = int(after_excl * ratio)

    return InterestDisallowanceResult(
        total_interest=total_interest,
        unknown_creditor_disallowed=unknown_creditor_interest,
        nonreal_name_disallowed=nonreal_name_interest,
        construction_capitalized=construction_interest,
        non_business_ratio=round(ratio, 6),
        non_business_disallowed=non_biz_disallowed,
        total_disallowed=(
            unknown_creditor_interest + nonreal_name_interest
            + construction_interest + non_biz_disallowed
        ),
    )
