"""중소기업 결손금 소급공제에 따른 환급세액 계산 (법§72, 영§110).

법§72① 중소기업 내국법인이 각 사업연도에 결손금이 발생하면 직전 사업연도
법인세액(영§110① — 직전 산출세액 − 직전 공제·감면세액)을 한도로 다음을 환급 신청할 수 있다.
  환급세액 = ① 직전 산출세액(§55의2 토지등양도 제외)
            − ② (직전 과세표준 − 소급공제 결손금) × 직전 §55① 세율
제약: 소급공제 결손금 ≤ min(당기 결손금, 직전 과세표준)
  — 당기 결손금 상당액은 법§72①2호('소급공제를 받으려는 해당 사업연도의 결손금 상당액'),
    직전 과표 초과분 배제는 영§110⑤(경정 시) 취지.
요건(법§72④, ①): 중소기업 + 당기·직전 모두 기한내 신고.

AI는 신청 여부를 확정하지 않는다 — 환급가능세액 초안·근거·검토포인트만 제시(ADR-002).
세액 계산은 규칙 엔진 전용.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta

from src.rules.tax_base import calc_gross_tax

# 직전 세율테이블 수록 하한 — 이 이전 개시 사업연도는 _RATE_TABLES에 과거 세율이 없어
# 엔진이 2호를 자동 계산하면 잘못된 세율이 적용된다(constants._RATE_TABLES는 2023·2026만 수록).
RATE_TABLE_FLOOR = date(2023, 1, 1)


@dataclass
class LossCarrybackResult:
    eligible: bool                  # 환급 신청 가능(요건 충족 + 한도>0)
    refund: int                     # 환급가능세액 (min[1호−2호, 한도])
    refund_limit: int               # 한도 = 직전 산출세액 − 직전 공제·감면세액 (영§110①)
    applied_loss: int               # 실제 소급공제에 적용한 결손금
    max_carryback_loss: int         # 소급공제 가능 결손금 상한 = min(당기결손금, 직전 과표)
    step1: int                      # 1호 = 직전 산출세액(토지등양도 제외)
    step2: int                      # 2호 = (직전 과표 − 적용결손금) × 직전 세율
    prior_tax_base: int             # 직전 사업연도 과세표준 (별지68호 ⑧ 표시용)
    prior_credit_exemption: int     # 직전 공제·감면세액 (별지68호 ⑩ 표시용)
    current_loss: int               # 당기 결손금 (별지68호 표시용)
    prior_rate_table_from: date | None  # 2호 계산에 적용된 세율테이블 시행일 (override 시 None)
    limit_binds: bool               # 한도가 환급액을 제한했는가
    needs_manual_step2: bool        # 직전 세율테이블 미수록 → 회계사 2호 입력 필요
    reasons: list[str] = field(default_factory=list)  # 불가·주의 사유


def compute_loss_carryback(
    *,
    is_sme: bool,
    current_loss: int,
    prior_tax_base: int,
    prior_gross_tax: int,
    prior_credit_exemption: int,
    prior_fiscal_start: date,
    requested_loss: int | None = None,
    both_filed_on_time: bool = True,
    manual_step2_override: int | None = None,
) -> LossCarrybackResult:
    """결손금 소급공제 환급가능세액 계산.

    current_loss: 당기 결손금 = max(0, −각사업연도소득) (각사업연도결손금 기준).
    prior_gross_tax: 직전 산출세액 — §55의2 토지등양도 법인세 제외분 (영§110①).
    prior_credit_exemption: 직전 공제·감면세액 (가산세는 제외 — 한도는 산출세액 기준).
    prior_fiscal_start: 직전 사업연도 개시일 — 2호의 §55① 세율을 그 시점 테이블로 적용.
    requested_loss: 회계사가 신청하는 소급공제 결손금. None이면 상한 전액.
    manual_step2_override: 직전<2023 등 세율테이블 미수록 시 회계사가 직접 산정한 2호 금액.
    """
    reasons: list[str] = []

    refund_limit = max(0, prior_gross_tax - prior_credit_exemption)
    max_carryback_loss = max(0, min(current_loss, prior_tax_base))

    # ── 요건·게이트 ──
    if not is_sme:
        reasons.append("중소기업이 아니므로 소급공제 대상이 아님 (법§72①).")
    if not both_filed_on_time:
        reasons.append("당기·직전 사업연도 모두 기한내 신고한 경우에만 적용 (법§72④).")
    if current_loss <= 0:
        reasons.append("당기 결손금이 없어 소급공제 대상이 아님.")
    if prior_gross_tax <= 0 or refund_limit <= 0:
        reasons.append("직전 사업연도 납부할 법인세액(한도)이 없어 환급액이 없음 (영§110①).")

    eligible = (
        is_sme and both_filed_on_time
        and current_loss > 0 and prior_gross_tax > 0
        and refund_limit > 0 and max_carryback_loss > 0
    )
    if not eligible:
        return LossCarrybackResult(
            eligible=False, refund=0, refund_limit=refund_limit,
            applied_loss=0, max_carryback_loss=max_carryback_loss,
            step1=max(0, prior_gross_tax), step2=0,
            prior_tax_base=prior_tax_base, prior_credit_exemption=prior_credit_exemption,
            current_loss=current_loss, prior_rate_table_from=None,
            limit_binds=False, needs_manual_step2=False, reasons=reasons,
        )

    # 적용 결손금: 신청액(기본 상한 전액)을 상한으로 클램프
    applied_loss = max_carryback_loss if requested_loss is None else max(0, min(requested_loss, max_carryback_loss))

    step1 = prior_gross_tax  # 1호 (토지등양도 제외분 — 호출부에서 보장)

    # ── 2호: (직전 과표 − 적용결손금) × 직전 세율 ──
    needs_manual_step2 = False
    prior_rate_table_from: date | None = None
    if manual_step2_override is not None:
        step2 = max(0, manual_step2_override)
    elif prior_fiscal_start < RATE_TABLE_FLOOR:
        # 과거 세율테이블 미수록 — 임의 세율 적용 금지. 회계사 2호 입력 전까지 보수적으로 0 환급.
        needs_manual_step2 = True
        reasons.append(
            f"직전 사업연도({prior_fiscal_start.year})의 세율테이블이 엔진에 미수록 — "
            "2호((직전 과표−결손금)×직전 세율)를 회계사가 직접 입력해야 정확합니다.")
        step2 = step1  # 환급 0으로 보수 처리 (입력 전 과대 환급 방지)
    else:
        step2, prior_rate_table_from = calc_gross_tax(
            tax_base=max(0, prior_tax_base - applied_loss),
            fiscal_year_start=prior_fiscal_start,
        )

    refund_before_limit = max(0, step1 - step2)
    refund = min(refund_before_limit, refund_limit)
    limit_binds = refund_before_limit > refund_limit

    if applied_loss < max_carryback_loss:
        reasons.append(
            f"신청 결손금({applied_loss:,}원)이 상한({max_carryback_loss:,}원) 미만 — "
            "잔여 결손금은 이월공제(법§13①1호) 대상으로 남습니다.")
    if limit_binds:
        reasons.append(
            f"환급액이 직전 법인세액 한도({refund_limit:,}원)에 의해 제한됨 — "
            "한도 초과 결손금은 이월공제로 검토하세요.")

    return LossCarrybackResult(
        eligible=True, refund=refund, refund_limit=refund_limit,
        applied_loss=applied_loss, max_carryback_loss=max_carryback_loss,
        step1=step1, step2=step2,
        prior_tax_base=prior_tax_base, prior_credit_exemption=prior_credit_exemption,
        current_loss=current_loss, prior_rate_table_from=prior_rate_table_from,
        limit_binds=limit_binds, needs_manual_step2=needs_manual_step2, reasons=reasons,
    )


def compute_loss_carryback_from_manual(
    mi, *, is_sme: bool, fy_start: date, current_loss: int,
) -> LossCarrybackResult:
    """수기입력(ManualInput)·당기 사업연도 개시일에서 인자를 구성해 compute_loss_carryback 호출.

    calc/output 3개 호출부의 동일한 인자 포장을 한곳으로 모은다(산식 불변, 포장 전용).
    직전 사업연도 개시일은 1년 전 — 2/29 개시는 평년으로 보정.
    """
    try:
        prior_start = fy_start.replace(year=fy_start.year - 1)
    except ValueError:                       # 2/29 개시 등 — 직전연도 평년
        prior_start = fy_start - timedelta(days=365)
    return compute_loss_carryback(
        is_sme=is_sme,
        current_loss=current_loss,
        prior_tax_base=int(mi.loss_carryback_prior_tax_base or 0),
        prior_gross_tax=int(mi.loss_carryback_prior_gross_tax or 0),
        prior_credit_exemption=int(mi.loss_carryback_prior_credit or 0),
        prior_fiscal_start=prior_start,
        requested_loss=(int(mi.loss_carryback_requested_loss) or None),
        both_filed_on_time=bool(mi.loss_carryback_both_filed),
        manual_step2_override=(int(mi.loss_carryback_step2_override) or None),
    )
