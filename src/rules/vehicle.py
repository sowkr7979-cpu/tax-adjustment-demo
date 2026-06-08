"""업무용승용차 비용 세무조정 — 법인세법 제27조의2, 시행령 제50조의2.

영§50의2⑦: 운행기록부 미작성 시 업무사용비율 =
  관련비용 ≤ 1,500만원 → 100% / 초과 → 1,500만원 ÷ 관련비용
영§50의2⑮: 특정법인(영§42② 요건 모두 충족)은
  "1,500만원"→"500만원", "800만원"→"400만원"
법§27의2③·영§50의2⑦: 한도는 사업연도 월수/12로 안분.
"""
from dataclasses import dataclass

from src.utils.constants import (
    VEHICLE_DEPRECIATION_ANNUAL_LIMIT,
    VEHICLE_DEPRECIATION_LIMIT_SPECIFIED,
    VEHICLE_NO_LOGBOOK_LIMIT,
    VEHICLE_NO_LOGBOOK_LIMIT_SPECIFIED,
)


@dataclass
class VehicleResult:
    vehicle_id: str
    has_insurance: bool
    has_logbook: bool
    business_use_ratio: float
    depreciation: int
    other_expense: int
    prior_deferred_depr: int
    personal_use_disallowed: int        # 개인 사용분 전액 손금불산입
    depreciation_limit_excess: int      # 800만원(특정법인 400만원) 한도 초과 → 이월 (유보)
    business_other_expense_allowed: int # 기타 비용 업무사용분 (한도 없음)
    total_disallowed: int
    is_specified_corp: bool = False     # 특정법인 (영§50의2⑮ — 한도 50%)
    depreciation_limit: int = VEHICLE_DEPRECIATION_ANNUAL_LIMIT  # 적용된 감가상각 한도
    no_logbook_limit: int = 0           # 운행기록부 미작성 시 적용된 전액인정 한도


def calc_vehicle(
    *,
    vehicle_id: str,
    depreciation: int,
    other_expense: int,
    business_use_ratio: float,
    has_insurance: bool,
    has_logbook: bool,
    prior_deferred_depr: int = 0,
    is_specified_corp: bool = False,
    months: int = 12,
) -> VehicleResult:
    """
    1. 전용보험 미가입 → 전액 손금불산입 (영§50의2④1호)
    2. 운행기록부 없음 → 업무사용비율 = min(1, 1,500만원/관련비용) (영§50의2⑦)
       — 특정법인은 1,500만원 대신 500만원 (영§50의2⑮)
    3. 감가상각비: 업무사용분 + 전기이월분의 연 800만원 한도 (법§27의2③)
       — 특정법인은 400만원, 사업연도 1년 미만 시 월수/12 안분
    4. 기타비용: 업무사용비율 인정분 전액 손금 (별도 한도 없음)
    """
    depr_limit_annual = (
        VEHICLE_DEPRECIATION_LIMIT_SPECIFIED if is_specified_corp
        else VEHICLE_DEPRECIATION_ANNUAL_LIMIT
    )
    no_log_annual = (
        VEHICLE_NO_LOGBOOK_LIMIT_SPECIFIED if is_specified_corp
        else VEHICLE_NO_LOGBOOK_LIMIT
    )
    depr_limit = int(depr_limit_annual * months / 12)
    no_log_limit = int(no_log_annual * months / 12)

    total = depreciation + other_expense
    if not has_insurance:
        return VehicleResult(
            vehicle_id=vehicle_id, has_insurance=False, has_logbook=has_logbook,
            business_use_ratio=0.0, depreciation=depreciation, other_expense=other_expense,
            prior_deferred_depr=prior_deferred_depr,
            personal_use_disallowed=total, depreciation_limit_excess=0,
            business_other_expense_allowed=0, total_disallowed=total,
            is_specified_corp=is_specified_corp,
            depreciation_limit=depr_limit, no_logbook_limit=no_log_limit,
        )

    if has_logbook:
        ratio = business_use_ratio
    else:
        # 영§50의2⑦ — 운행기록부 미작성 시
        ratio = 1.0 if total <= no_log_limit else (no_log_limit / total if total else 1.0)

    biz_depr = int(depreciation * ratio)
    personal_depr = depreciation - biz_depr
    biz_other = int(other_expense * ratio)
    personal_other = other_expense - biz_other

    # 감가상각비 + 전기이월분 vs 한도 (800만 / 특정법인 400만, 월수 안분)
    total_depr = biz_depr + prior_deferred_depr
    allowed_depr = min(total_depr, depr_limit)
    deferred = max(0, total_depr - depr_limit)

    personal_disallowed = personal_depr + personal_other
    total_disallowed = personal_disallowed + deferred

    return VehicleResult(
        vehicle_id=vehicle_id, has_insurance=True, has_logbook=has_logbook,
        business_use_ratio=ratio, depreciation=depreciation, other_expense=other_expense,
        prior_deferred_depr=prior_deferred_depr,
        personal_use_disallowed=personal_disallowed,
        depreciation_limit_excess=deferred,
        business_other_expense_allowed=biz_other,
        total_disallowed=total_disallowed,
        is_specified_corp=is_specified_corp,
        depreciation_limit=depr_limit, no_logbook_limit=no_log_limit,
    )
