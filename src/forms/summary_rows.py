"""소득금액조정합계표(별지 제15호 구조) 행 구성 — 화면·PDF 공용 단일 소스."""
from __future__ import annotations

from src.utils.models import TaxAdjustmentResult
from src.rules.disposition import resolve_disposition, split_unknown_creditor_interest

# 결산조정사항: 장부에 계상해야 손금 인정 (한도 시부인) — 그 외는 신고조정
CLOSING_ADJ = {
    "감가상각비 한도초과", "감가상각 전기부인액 추인",
    "퇴직급여충당금 한도초과", "대손충당금 한도초과",
}


def adj_type(name: str) -> str:
    return "결산조정" if name in CLOSING_ADJ else "신고조정"


def adjustment_rows(
    r: TaxAdjustmentResult,
    choices: dict | None = None,
) -> tuple[list[tuple], list[tuple]]:
    """(가산조정 행, 차감조정 행) — (구분, 항목, 금액, 근거, 소득처분).

    choices: 소득처분 귀속자 선택 (영§106). None이면 레거시 라벨(하위호환).
      키: "인정이자|{상대방}", "부당행위계산 부인", "업무용승용차 관련비용",
          "복리후생비 (열거 외)" → 귀속자유형 / "채권자불분명 사채이자|원천세" → 원천세 상당액(int)
    """
    legacy = choices is None
    ch = choices or {}

    def _disp(key: str, default: str) -> str:
        return default if legacy else resolve_disposition(ch.get(key))

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
        ("손금불산입", "업무용승용차 개인사용분",   r.vehicle_disallowed - r.vehicle_depr_excess, "법§27의2", _disp("업무용승용차 개인사용분", "상여 등")),
        ("손금불산입", "업무용승용차 감가상각 한도초과", r.vehicle_depr_excess,  "법§27의2③", "유보"),
        ("손금불산입", "건설자금이자",             r.interest_construction,    "법§28①3호", "유보"),
        ("손금불산입", "업무무관자산 지급이자",     r.interest_non_business,    "법§28①4호", "기타사외유출"),
        ("손금불산입", "기부금 한도초과·비지정",    r.donation_excess,          "법§24",    "기타사외유출"),
        ("손금불산입", "유가증권 평가손실",         r.securities_loss_disallowed, "영§75",  "유보"),
        ("손금불산입", "재고자산 평가 조정",        r.inventory_adjustment,     "영§74",    "유보"),
        ("손금불산입", "복리후생비 (열거 외)",      r.welfare_disallowed,       "영§45",    _disp("복리후생비 (열거 외)", "상여 등")),
        ("손금불산입", "공동경비 분담 초과",        r.joint_expense_excess,     "영§48",    "기타사외유출"),
        ("손금불산입", "업무무관비용",             r.non_business_expense,     "법§27",    "기타사외유출"),
        ("손금불산입", "징벌적 손해배상금",         r.punitive_damages,         "법§21의2", "기타사외유출"),
        ("익금산입",   "간주임대료",               r.deemed_rental,            "조특법§138", "기타사외유출"),
        ("익금산입",   "부당행위계산 부인",         r.unfair_transaction,       "법§52, 영§88", _disp("부당행위계산 부인", "배당·상여 등")),
        ("익금산입",   "전기 △유보 추인",          r.prior_reserve_reversal_add, "법§34③ 등", "유보"),
    ]

    # 채권자불분명 사채이자 — 원천세 상당액=기타사외유출 / 잔액=대표자상여 (영§106)
    if r.interest_unknown_creditor:
        if legacy:
            add_items.append(("손금불산입", "채권자불분명 사채이자", r.interest_unknown_creditor,
                              "법§28①1호", "대표자상여 등"))
        else:
            _wh = int(ch.get("채권자불분명 사채이자|원천세", 0) or 0)
            for _amt, _disp_v in split_unknown_creditor_interest(r.interest_unknown_creditor, _wh):
                add_items.append(("손금불산입", "채권자불분명 사채이자", _amt, "법§28①1호", _disp_v))

    # 비실명 채권·증권이자 (법§28①2호) — 채권자불분명과 동일 처분(원천세=기타사외유출/잔액=대표자상여)
    if r.interest_nonreal_name:
        if legacy:
            add_items.append(("손금불산입", "비실명 채권·증권이자", r.interest_nonreal_name,
                              "법§28①2호", "대표자상여 등"))
        else:
            _wh2 = int(ch.get("비실명 채권·증권이자|원천세", 0) or 0)
            for _amt, _disp_v in split_unknown_creditor_interest(r.interest_nonreal_name, _wh2):
                add_items.append(("손금불산입", "비실명 채권·증권이자", _amt, "법§28①2호", _disp_v))

    # 가지급금 인정이자 — 거래상대방별 처분 (영§106). 상대방 합이 총액과 일치할 때만 분리.
    if r.deemed_interest:
        _parties = [] if legacy else (r.deemed_interest_parties or [])
        if _parties and sum(int(p.get("amount", 0)) for p in _parties) == r.deemed_interest:
            for p in _parties:
                _nm = str(p.get("name", ""))
                add_items.append(("익금산입", f"가지급금 인정이자 ({_nm})", int(p.get("amount", 0)),
                                  "법§52, 영§89", resolve_disposition(ch.get(f"인정이자|{_nm}"))))
        else:
            add_items.append(("익금산입", "가지급금 인정이자", r.deemed_interest, "법§52, 영§89",
                              _disp("가지급금 인정이자", "상여 등")))
    deduct_items = [
        ("손금산입",   "감가상각 전기부인액 추인",  r.depreciation_approved,    "법§23",    "△유보"),
        ("손금산입",   "전기 유보 추인",           r.prior_reserve_reversal_deduct, "법§34③ 등", "△유보"),
        ("손금산입",   "기부금 이월액 당기 공제",   r.donation_carryforward_deduction, "법§24⑤⑥", "기타"),
        ("손금산입",   "퇴직연금 부담금",          r.pension_deduction,        "영§44의2", "△유보"),
        ("익금불산입", "수입배당금",               r.dividend_exclusion,       "법§18의2", "기타"),
        ("익금불산입", "외화환산이익 (평가 미신고)", r.forex_gain_excluded,     "법§42③",   "△유보"),
        ("익금불산입", "파생상품 평가이익 (미신고)", r.derivative_gain_excluded, "영§76",   "△유보"),
        ("익금불산입", "유가증권 평가이익",         r.securities_gain_excluded, "영§75",   "△유보"),
        ("익금불산입", "자산수증익·채무면제익 (이월결손금 보전)", r.debt_relief_offset, "법§18 6호", "기타"),
        ("익금불산입", "국세환급금 이자",          r.refund_interest_excluded, "법§18 4호", "기타"),
        ("익금불산입", "부가가치세 매출세액",       r.vat_output_excluded,      "법§18 5호", "기타"),
    ]
    return add_items, deduct_items
