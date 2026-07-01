"""소급공제법인세액환급신청서 (법인세법 시행규칙 [별지 제68호서식]).

법§72·영§110 결손금 소급공제 환급의 신청서 표시 구조 — 화면 표시용 단일 소스.
환급세액 산식은 `src/rules/loss_carryback.py`가 단일 산출(규칙엔진 전용, ADR-002).
이 빌더는 그 결과(LossCarrybackResult)를 별지68호 란 구조로 배치만 한다.
"""
from __future__ import annotations
from datetime import date

from src.rules.loss_carryback import LossCarrybackResult

FORM_TITLE = "소급공제법인세액환급신청서"
FORM_BYL = "법인세법 시행규칙 [별지 제68호서식]"


def build_refund_request(
    *,
    company,
    fy_start: date,
    fy_end: date,
    lcb: LossCarrybackResult,
) -> dict:
    """별지 제68호 소급공제법인세액환급신청서 표시 구조 반환.

    company: CompanyInfo (법인명·사업자번호·대표자·업종·소재지).
    fy_start/fy_end: 당기(결손 발생) 사업연도. 직전 사업연도는 각 1년 전.
    lcb: compute_loss_carryback 결과 (직전 과표·공제감면·당기결손금 포함).
    """
    prior_start = fy_start.replace(year=fy_start.year - 1)
    prior_end = fy_end.replace(year=fy_end.year - 1)

    # ① 신청인
    applicant = [
        {"항목": "① 법인명", "내용": getattr(company, "name", "") or ""},
        {"항목": "② 사업자등록번호", "내용": getattr(company, "business_no", "") or ""},
        {"항목": "③ 대표자", "내용": getattr(company, "representative", "") or ""},
        {"항목": "④ 업종(코드)", "내용": getattr(company, "industry_code", "") or ""},
        {"항목": "⑤ 소재지", "내용": getattr(company, "address", "") or ""},
        {"항목": "⑥ 결손금이 발생한 사업연도", "내용": f"{fy_start} ~ {fy_end}"},
    ]

    # ② 환급신청 내용 (법§72①1·2호·영§110①)
    refund_rows = [
        {"란": "⑦ 직전 사업연도", "금액": f"{prior_start} ~ {prior_end}"},
        {"란": "⑧ 직전 사업연도 과세표준", "금액": f"{lcb.prior_tax_base:,}"},
        {"란": "⑨ 직전 사업연도 산출세액 (토지등양도소득 법인세 제외)", "금액": f"{lcb.step1:,}"},
        {"란": "⑩ 직전 사업연도 공제·감면세액", "금액": f"{lcb.prior_credit_exemption:,}"},
        {"란": "⑪ 직전 사업연도 법인세액 (⑨ − ⑩) = 환급 한도", "금액": f"{lcb.refund_limit:,}"},
        {"란": "⑫ 소급공제 결손금액", "금액": f"{lcb.applied_loss:,}"},
        {"란": "⑬ 소급공제 후 과세표준 (⑧ − ⑫)",
         "금액": f"{max(0, lcb.prior_tax_base - lcb.applied_loss):,}"},
        {"란": "⑭ 소급공제 후 산출세액 (⑬ × 직전 세율)", "금액": f"{lcb.step2:,}"},
        {"란": "⑮ 환급신청 세액 = min(⑨ − ⑭, ⑪)",
         "금액": f"{lcb.refund:,}" + ("" if lcb.eligible else " (요건 미충족)")},
    ]

    # 계산근거 (산식·근거조문 — 실제 값 대입) — 감사추적용
    _refund_before = max(0, lcb.step1 - lcb.step2)
    calc_basis = [
        "직전 과표·산출세액·공제감면(⑧⑨⑩)은 회계사 입력값 또는 전년 .taxproj 승계 — "
        "직전 사업연도 신고서(과세표준및세액조정계산서)와 대조 필요",
        f"당기 결손금 = max(0, −각사업연도소득) = {lcb.current_loss:,}원 "
        "(본 보고서 1.핵심세액지표·3.세목별 세무조정에서 도출, 법§14②)",
        f"① 직전 산출세액 ⑨ = {lcb.step1:,}원 (§55의2 토지등양도소득 법인세 제외, 법§72①1호)",
        f"소급공제 결손금 ⑫ = {lcb.applied_loss:,}원 (상한 min(당기 결손금, 직전 과표) "
        f"= {lcb.max_carryback_loss:,}원 — 법§72①2호 '해당 사업연도 결손금 상당액'·직전 과표 한도, "
        "영§110⑤ 경정 시 과표 초과분 배제)",
        f"② 소급공제 후 산출세액 ⑭ = (직전 과표 {lcb.prior_tax_base:,} − 소급공제 결손금 {lcb.applied_loss:,}) "
        f"× 직전 세율 = {lcb.step2:,}원 (법§72①2호)"
        + (" — 직전 세율테이블 미수록: 회계사 직접 입력값" if lcb.needs_manual_step2 else ""),
        f"환급 한도 ⑪ = 직전 산출세액 {lcb.step1:,} − 직전 공제·감면세액 {lcb.prior_credit_exemption:,} "
        f"= {lcb.refund_limit:,}원 (영§110①, 가산세 제외)",
        (
            f"환급신청 세액 ⑮ = min(⑨ − ⑭, ⑪) = min({_refund_before:,}, {lcb.refund_limit:,}) "
            f"= {lcb.refund:,}원 (법§72①)"
            if lcb.eligible else
            "환급신청 세액 ⑮ = 0원 (요건 미충족 — 아래 사유 참조, 법§72①④)"
        ),
    ]

    notes: list[str] = list(lcb.reasons)
    notes.append(
        "추징 주의(법§72⑤·영§110④): 추후 결손금 경정 감소·직전 경정·중소기업 탈락 시 "
        "환급세액에 이자상당액(1일 10만분의 22)을 더해 징수됩니다.")
    notes.append("근거: 법§72(001563/007200)·영§110(003608/011000). 신청 여부·금액은 회계사·납세자가 확정.")

    return {
        "title": FORM_TITLE,
        "byl": FORM_BYL,
        "applicant": applicant,
        "refund_rows": refund_rows,
        "calc_basis": calc_basis,
        "current_loss": lcb.current_loss,
        "refund": lcb.refund,
        "eligible": lcb.eligible,
        "needs_manual_step2": lcb.needs_manual_step2,
        "notes": notes,
    }
