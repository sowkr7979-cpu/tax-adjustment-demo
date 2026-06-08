"""소득금액조정합계표(별지 제15호 구조) 행 구성 — 화면·PDF 공용 단일 소스."""
from __future__ import annotations

from src.utils.models import TaxAdjustmentResult

# 결산조정사항: 장부에 계상해야 손금 인정 (한도 시부인) — 그 외는 신고조정
CLOSING_ADJ = {
    "감가상각비 한도초과", "감가상각 전기부인액 추인",
    "퇴직급여충당금 한도초과", "대손충당금 한도초과",
}


def adj_type(name: str) -> str:
    return "결산조정" if name in CLOSING_ADJ else "신고조정"


def adjustment_rows(r: TaxAdjustmentResult) -> tuple[list[tuple], list[tuple]]:
    """(가산조정 행, 차감조정 행) — (구분, 항목, 금액, 근거, 소득처분)."""
    add_items = [
        ("손금불산입", "감가상각비 한도초과",      r.depreciation_excess,      "법§23",    "유보"),
        ("손금불산입", "기업업무추진비 한도초과",   r.entertainment_excess,     "법§25④",   "기타사외유출"),
        ("손금불산입", "기업업무추진비 증빙불비",   r.entertainment_no_receipt, "법§25②",   "기타사외유출"),
        ("손금불산입", "퇴직급여충당금 한도초과",   r.pension_excess,           "법§33",    "유보"),
        ("손금불산입", "대손충당금 한도초과",      r.bad_debt_excess,          "법§34",    "유보"),
        ("손금불산입", "벌과금·과태료·가산세",     r.penalty,                  "법§21",    "기타사외유출"),
        ("손금불산입", "법인세비용",               r.corporate_tax_expense,    "법§21 1호", "기타사외유출"),
        ("손금불산입", "외화환산손실 (평가 미신고)", r.forex_loss_disallowed,   "법§42③",   "유보"),
        ("손금불산입", "파생상품 평가손실 (미신고)", r.derivative_loss_disallowed, "영§76",  "유보"),
        ("손금불산입", "임원 상여금 한도초과",      r.officer_bonus_excess,     "법§26, 영§43", "상여"),
        ("손금불산입", "임원 퇴직금 한도초과",      r.officer_retirement_excess, "법§26, 영§44", "상여"),
        ("손금불산입", "업무용승용차 관련비용",     r.vehicle_disallowed,       "법§27의2", "상여 등"),
        ("손금불산입", "채권자불분명 사채이자",     r.interest_unknown_creditor, "법§28①1호", "대표자상여 등"),
        ("손금불산입", "건설자금이자",             r.interest_construction,    "법§28①3호", "유보"),
        ("손금불산입", "업무무관자산 지급이자",     r.interest_non_business,    "법§28①4호", "기타사외유출"),
        ("손금불산입", "기부금 한도초과·비지정",    r.donation_excess,          "법§24",    "기타사외유출"),
        ("손금불산입", "유가증권 평가손실",         r.securities_loss_disallowed, "영§75",  "유보"),
        ("손금불산입", "재고자산 평가 조정",        r.inventory_adjustment,     "영§74",    "유보"),
        ("손금불산입", "복리후생비 (열거 외)",      r.welfare_disallowed,       "영§45",    "상여 등"),
        ("손금불산입", "공동경비 분담 초과",        r.joint_expense_excess,     "영§48",    "기타사외유출"),
        ("손금불산입", "업무무관비용",             r.non_business_expense,     "법§27",    "기타사외유출"),
        ("손금불산입", "징벌적 손해배상금",         r.punitive_damages,         "법§21의2", "기타사외유출"),
        ("익금산입",   "가지급금 인정이자",        r.deemed_interest,          "법§52, 영§89", "상여 등"),
        ("익금산입",   "간주임대료",               r.deemed_rental,            "조특법§138", "기타사외유출"),
        ("익금산입",   "부당행위계산 부인",         r.unfair_transaction,       "법§52, 영§88", "배당·상여 등"),
    ]
    deduct_items = [
        ("손금산입",   "감가상각 전기부인액 추인",  r.depreciation_approved,    "법§23",    "△유보"),
        ("손금산입",   "퇴직연금 부담금",          r.pension_deduction,        "영§44의2", "△유보"),
        ("익금불산입", "수입배당금",               r.dividend_exclusion,       "법§18의2", "기타"),
        ("익금불산입", "외화환산이익 (평가 미신고)", r.forex_gain_excluded,     "법§42③",   "△유보"),
        ("익금불산입", "파생상품 평가이익 (미신고)", r.derivative_gain_excluded, "영§76",   "△유보"),
        ("익금불산입", "유가증권 평가이익",         r.securities_gain_excluded, "영§75",   "△유보"),
    ]
    return add_items, deduct_items
