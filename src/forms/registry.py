"""별지서식 레지스트리 — 서식 번호는 이 파일에만 정의."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date


@dataclass
class FormEntry:
    key: str
    name: str
    byl_no: str            # 별지 번호 표시
    byl_seq: str = ""      # API bylSeq (확인 후 채움)
    verified: bool = False
    verified_date: date | None = None
    effective_from: date | None = None
    download_url: str = ""
    api_response_hash: str = ""


FORM_REGISTRY: dict[str, FormEntry] = {
    # ✅ 확인 완료
    "TAX_BASE_REPORT": FormEntry(
        key="TAX_BASE_REPORT", name="법인세 과세표준 및 세액신고서",
        byl_no="별지제1호서식", verified=True,
    ),
    "CAPITAL_ADJUST_A": FormEntry(
        key="CAPITAL_ADJUST_A", name="자본금과 적립금 조정명세서(갑)",
        byl_no="별지제50호서식(갑)", verified=True,
    ),
    "CAPITAL_ADJUST_B": FormEntry(
        key="CAPITAL_ADJUST_B", name="자본금과 적립금 조정명세서(을)",
        byl_no="별지제50호서식(을)", verified=True,
    ),
    "REFUND_REQUEST": FormEntry(
        key="REFUND_REQUEST", name="소급공제법인세액환급신청서",
        byl_no="별지제68호서식", verified=True,
    ),
    # ⚠️ API 확인 전 잠정값
    "BALANCE_SHEET": FormEntry(
        key="BALANCE_SHEET", name="표준재무상태표",
        byl_no="별지제3호의2서식",
    ),
    "INCOME_STATEMENT": FormEntry(
        key="INCOME_STATEMENT", name="표준손익계산서",
        byl_no="별지제3호의3서식",
    ),
    "INCOME_ADJUST_SUM": FormEntry(
        key="INCOME_ADJUST_SUM", name="소득금액조정합계표 및 명세서",
        byl_no="별지제15호서식",
    ),
    "ENTERTAINMENT_A": FormEntry(
        key="ENTERTAINMENT_A", name="기업업무추진비 조정명세서(갑)",
        byl_no="별지제16호서식(갑)",
    ),
    "ENTERTAINMENT_B": FormEntry(
        key="ENTERTAINMENT_B", name="기업업무추진비 조정명세서(을)",
        byl_no="별지제16호서식(을)",
    ),
    "DEPRECIATION": FormEntry(
        key="DEPRECIATION", name="감가상각비 조정명세서",
        byl_no="별지제20호서식",
    ),
    "DONATION": FormEntry(
        key="DONATION", name="기부금조정명세서",
        byl_no="별지제21호서식", byl_seq="18055559", verified=True,
    ),
    "DONATION_DETAIL": FormEntry(
        key="DONATION_DETAIL", name="기부금명세서",
        byl_no="별지제22호서식", byl_seq="18055561", verified=True,
    ),
    "MIN_TAX": FormEntry(
        key="MIN_TAX", name="최저한세 조정계산서",
        byl_no="별지제4호서식",
    ),
    "TAX_CREDIT_SUM": FormEntry(
        key="TAX_CREDIT_SUM", name="세액공제·감면 합계표",
        byl_no="별지제8호서식",
    ),
    "DEEMED_INTEREST": FormEntry(
        key="DEEMED_INTEREST", name="가지급금 등의 인정이자 조정명세서",
        byl_no="별지제19호서식",
    ),
    "BAD_DEBT": FormEntry(
        key="BAD_DEBT", name="대손충당금 및 대손금 조정명세서",
        byl_no="별지제26호서식",
    ),
    "RETIREMENT_ALLOW": FormEntry(
        key="RETIREMENT_ALLOW", name="퇴직급여충당금 조정명세서",
        byl_no="별지제27호서식",
    ),
    "VEHICLE_EXPENSE": FormEntry(
        key="VEHICLE_EXPENSE", name="업무용승용차 관련비용 명세서",
        byl_no="별지제27호의2서식",
    ),
}


def recommend_forms(
    has_depreciation: bool,
    has_entertainment: bool,
    has_donation: bool,
    has_pension: bool,
    has_bad_debt: bool,
    has_interest: bool,
    has_forex: bool,
    has_dividend: bool,
    has_vehicle: bool,
    has_tax_credit: bool,
    is_sme: bool,
    has_loss_carryback: bool = False,
) -> list[FormEntry]:
    """계정 존재 여부에 따라 필요 서식 추천."""
    keys = ["TAX_BASE_REPORT", "BALANCE_SHEET", "INCOME_STATEMENT",
            "CAPITAL_ADJUST_A", "CAPITAL_ADJUST_B", "INCOME_ADJUST_SUM"]
    if has_depreciation:
        keys.append("DEPRECIATION")
    if has_entertainment:
        keys += ["ENTERTAINMENT_A", "ENTERTAINMENT_B"]
    if has_donation:
        keys.append("DONATION")
    if has_pension:
        keys.append("RETIREMENT_ALLOW")
    if has_bad_debt:
        keys.append("BAD_DEBT")
    if has_interest:
        keys.append("DEEMED_INTEREST")
    if has_vehicle:
        keys.append("VEHICLE_EXPENSE")
    if has_tax_credit:
        keys += ["TAX_CREDIT_SUM", "MIN_TAX"]
    if has_loss_carryback:
        keys.append("REFUND_REQUEST")
    return [FORM_REGISTRY[k] for k in keys if k in FORM_REGISTRY]
