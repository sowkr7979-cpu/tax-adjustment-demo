"""고객 자료요청 리스트 자동 생성 + 세무조정 후보 위험도 평가.

실무 원칙: 계산이 막혔을 때 "계산 불가"로 끝내지 않고
"세무조정 진행을 위해 고객에게 요청할 자료 목록"을 만들어 준다.
위험도(High/Medium/Low)는 회계사가 어디부터 볼지 정하는 용도 —
특수관계·증빙불비·대표자·금액 크기를 기준으로 한 결정론적 규칙.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DataRequest:
    item: str       # 요청할 자료
    reason: str     # 왜 필요한가 (무엇이 막히는지)
    related: str    # 관련 세무조정 (법령)
    risk: str       # High / Medium / Low


def build_data_requests(loader, mi, company, agg, has_prev_proj: bool,
                        net_income_confirmed: bool = False) -> list[DataRequest]:
    """현재 업로드·입력 상태를 점검해 누락 자료 요청 목록을 만든다.

    loader: SmartALoader / mi: ManualInput / company: CompanyInfo
    agg: JournalAggregates (분개장 집계 — 없으면 None)
    has_prev_proj: 전년도 .taxproj 승계 여부
    net_income_confirmed: 사용자가 당기순이익을 직접 입력했거나 '실제로 0원'임을
        확인한 상태 — True면 손익계산서 재요청을 하지 않는다
        ("0원이 맞다"고 확인했는데 "손익계산서 다시 주세요"라고 하는 모순 방지)
    """
    out: list[DataRequest] = []
    journals = getattr(loader, "journals", None) or []

    def _has_acct(*kws: str) -> bool:
        return any(
            any(k in ln.account_name.replace(" ", "") for k in kws) for ln in journals
        )

    # 전년도 세무조정 자료
    if not has_prev_proj and not (mi.prior_reserves or mi.carryforward_losses):
        out.append(DataRequest(
            "전년도 세무조정계산서 (자본금과적립금조정명세서 갑·을 포함)",
            "전기 유보잔액·이월결손금·감가상각 부인누계가 없으면 당기 조정의 출발값이 누락됩니다",
            "유보 관리 전반, 법§13(이월결손금)", "High",
        ))

    # 손익계산서 — 당기순이익 (수기 입력·0원 확인 시에는 재요청하지 않음)
    if (not net_income_confirmed
            and (loader.income_statement is None or loader.get_net_income() == 0)):
        out.append(DataRequest(
            "손익계산서 ('당기순이익' 행 포함 양식)",
            "당기순이익을 인식하지 못하면 세액 계산을 시작할 수 없습니다 (자동 추정 금지 원칙)",
            "소득금액 계산 전체", "High",
        ))

    # 접대비 증빙
    if agg is not None and agg.entertainment.total_expense > 0 and agg.entertainment.evidence_unknown:
        out.append(DataRequest(
            "법인카드 사용내역·지출 증빙 (건별 카드/세금계산서 구분)",
            f"기업업무추진비 {agg.entertainment.total_expense:,}원이 있으나 분개장에 증빙 정보가 없어 "
            f"건당 3만원 초과 증빙불비 판정이 불가합니다",
            "기업업무추진비 (법§25②)", "High",
        ))

    # 감가상각 — 상각률·내용연수 누락
    _fa = getattr(loader, "fixed_assets", None) or []
    _rate_missing = [a for a in _fa if a.depr_rate <= 0 and not a.useful_life]
    if _rate_missing:
        out.append(DataRequest(
            f"고정자산 내용연수·상각방법 자료 ({len(_rate_missing)}개 자산)",
            "상각률·내용연수가 없어 상각범위액(영§26②)을 산식으로 계산하지 못하고 대장값에 의존 중입니다",
            "감가상각 시부인 (법§23)", "Medium",
        ))

    # 가지급금 ↔ 특수관계인 목록
    if _has_acct("가지급금", "대여금") and not mi.related_parties:
        out.append(DataRequest(
            "주주명부·특수관계인 명세 (임원 포함)",
            "가지급금·대여금 분개가 있으나 특수관계인 목록이 비어 있어 "
            "인정이자·업무무관이자 대상 선별이 불가합니다",
            "인정이자 (법§52), 지급이자 4호 (법§28)", "High",
        ))

    # 이자비용 ↔ 차입금 명세
    if agg is not None and agg.interest_expense > 0 and loader.account_statement is None:
        out.append(DataRequest(
            "차입금 명세서 (금융기관별 잔액·이자율·차입기간)",
            f"이자비용 {agg.interest_expense:,}원이 있으나 차입금 명세(계정별명세서)가 없어 "
            f"적수 기반 4호 비율·가중평균차입이자율 산정이 근사치에 머뭅니다",
            "지급이자 (법§28), 인정이자 이자율 (영§89③)", "Medium",
        ))

    # 업무용승용차 — 운행기록부·보험
    if (agg is not None and agg.vehicle_expense > 0) or mi.vehicle_depreciation > 0:
        if not mi.vehicle_has_logbook:
            out.append(DataRequest(
                "차량운행기록부 + 업무전용 자동차보험 가입증명",
                "운행기록부 미작성 시 업무사용비율이 min(100%, 1,500만/관련비용)으로 제한됩니다 (영§50의2⑦)",
                "업무용승용차 (법§27의2)", "Medium",
            ))

    # 기부금 — 미분류
    _unclassified = sum(
        1 for v in (mi.donation_line_classes or {}).values() if v == "미분류"
    )
    if _unclassified:
        out.append(DataRequest(
            f"기부금 영수증·기부처 목록 (미분류 {_unclassified}건)",
            "특례/일반/비지정 분류가 안 된 기부금은 한도 계산에서 제외되어 있습니다",
            "기부금 (법§24)", "Medium",
        ))

    # 간주임대료 — 건설비
    if mi.rental_deposit > 0 and company.is_rental_main and not mi.rental_construction_cost:
        out.append(DataRequest(
            "임대용 건물 취득원가(건설비) 명세 (토지 제외)",
            "건설비상당액이 없으면 보증금 적수 전액에 이자율이 적용되어 간주익금이 과대계산됩니다",
            "간주임대료 (조특령§132⑤⑥)", "Medium",
        ))

    # 퇴직연금
    if agg is not None and agg.pension_provision > 0 and not mi.pension_db_asset:
        out.append(DataRequest(
            "퇴직연금(DB형) 운용자산 보고서",
            "퇴직급여충당금 설정액이 있으나 연금 운용자산 정보가 없어 "
            "퇴직연금 손금산입(신고조정) 검토가 누락될 수 있습니다",
            "퇴직급여충당금 (법§33, 영§60)", "Medium",
        ))

    # 채권잔액 (대손충당금 한도)
    if agg is not None and agg.bad_debt_provision > 0 and not mi.receivable_balance:
        out.append(DataRequest(
            "채권 잔액 명세 (매출채권·미수금 등 설정대상 채권)",
            "대손충당금 설정액이 있으나 채권잔액이 없어 한도(채권×1%)가 0으로 계산됩니다",
            "대손충당금 (법§34)", "High",
        ))

    return out


# ── 위험도 평가 (전수 검토 체크리스트·조정 후보용) ──────────────────────────────

_HIGH_RISK_ITEMS = (
    "가지급금", "부당행위", "증빙", "업무무관", "채권자불분명", "징벌적",
)


def assess_risk(item_name: str, amount: int, status: str = "",
                has_related_party: bool = False) -> str:
    """결정론적 위험도: High / Medium / Low.

    기준: 특수관계·증빙불비·대표자성 항목은 금액과 무관하게 High,
    금액 5천만 이상 High / 1천만 이상 Medium / 그 외 Low.
    '검토필요' 상태는 한 단계 상향.
    """
    base = "Low"
    if any(k in item_name for k in _HIGH_RISK_ITEMS) and amount > 0:
        return "High"
    if has_related_party and amount > 0:
        return "High"
    if amount >= 50_000_000:
        base = "High"
    elif amount >= 10_000_000:
        base = "Medium"
    if status == "검토필요" and base == "Low" and amount > 0:
        base = "Medium"
    return base
