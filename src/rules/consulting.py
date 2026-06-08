"""세무 컨설팅 토픽 엔진 — 회사정보·재무제표·세무조정 결과 기반 결정론적 발굴.

설계 원칙 (KICPA·security 리뷰 합의):
  - 토픽·회사 숫자·법령 근거는 **규칙엔진이 결정론적으로** 산출 (LLM 환각 배제).
  - LLM은 (선택) 켜진 토픽의 서술만 다듬는다 — 숫자·요건·금액은 만들지 않는다.
  - 모든 토픽은 **검토필요(미확정)** — AI가 적용을 확정하지 않는다 (ADR-002).
  - 리스크 코멘트 우선(안전마진 큼) → 특례·감면 → 정책.

산출물은 6단계 '세무 컨설팅 코멘트' 레이어로 표시되며, 회계사가 채택/기각 후 확정한다.
"""
from __future__ import annotations

from dataclasses import dataclass

# 이월결손금 공제기한 (법§13 부칙) — 소멸 임박 판정용
from src.rules.tax_base import eligible_carryforward_total  # noqa: F401  (기한 로직 일관성 참조)


@dataclass
class ConsultingTopic:
    category: str        # "리스크" | "특례·감면" | "정책"
    title: str
    finding: str         # 회사 숫자 기반 발견 (규칙엔진 산출 — LLM 아님)
    suggestion: str      # 권고 (검토 후보)
    legal_basis: str     # 법령/참고파일 근거
    severity: str        # "높음" | "중간" | "낮음"
    status: str = "검토필요 (요건 확인·미확정)"   # ADR-002 — 항상 미확정


_SEV_ORDER = {"높음": 0, "중간": 1, "낮음": 2}
_CAT_ORDER = {"리스크": 0, "특례·감면": 1, "정책": 2}


def _loss_expiry_years(origin_year: int) -> int:
    if origin_year >= 2020:
        return 15
    if origin_year >= 2009:
        return 10
    return 5


def build_consulting_topics(*, company, manual_input, result, fiscal_year_end) -> list[ConsultingTopic]:
    """회사정보·수기입력·세무조정 결과 → 컨설팅 토픽 리스트 (결정론적).

    company: CompanyInfo (is_sme, is_specified_corp, industry_code, is_rental_main)
    manual_input: ManualInput (carryforward_losses, related_loan_balance, ...)
    result: TaxAdjustmentResult (조정 금액·세액)
    fiscal_year_end: date
    """
    mi, r = manual_input, result
    topics: list[ConsultingTopic] = []

    # ── 리스크 ────────────────────────────────────────────────────────────────
    # 1. 가지급금/가수금 정리 — 최고가치·최빈도 (인정이자 + 4호이자 + 대표자상여 동시 리스크)
    _loan_opening = sum(int(p.get("opening", 0)) for p in (mi.related_loan_parties or [])) \
        or mi.related_loan_balance or mi.related_loan_opening
    if r.deemed_interest or r.interest_non_business or _loan_opening:
        topics.append(ConsultingTopic(
            category="리스크",
            title="특수관계인 가지급금 정리",
            finding=(
                f"가지급금 인정이자 익금산입 {r.deemed_interest:,}원, "
                f"업무무관자산 지급이자 손금불산입 {r.interest_non_business:,}원이 발생했습니다."
            ),
            suggestion=(
                "가지급금을 조기 회수하면 인정이자 익금산입·지급이자 손금불산입·대표자 상여 "
                "처분 리스크를 함께 줄일 수 있습니다. 동일인 가수금이 있으면 상계 가능합니다(영§53③). "
                "약정이자율을 가중평균차입이자율 이상으로 설정하면 인정이자 부담이 줄어듭니다."
            ),
            legal_basis="법§28①4호, 법§52, 영§88①6호·89③, 영§53③",
            severity="높음",
        ))

    # 2. 소득처분 — 대표자 상여 귀속 시 대표 종소세까지 (회수·증빙·귀속자 확정)
    if r.deemed_interest or r.interest_unknown_creditor or (r.vehicle_disallowed - r.vehicle_depr_excess) > 0:
        topics.append(ConsultingTopic(
            category="리스크",
            title="소득처분(대표자 상여) 최소화",
            finding=(
                "사외유출 항목(가지급금 인정이자·채권자불분명이자·승용차 개인사용분 등)이 "
                "대표자 상여로 처분되면 대표자 종합소득세까지 추가로 발생할 수 있습니다."
            ),
            suggestion=(
                "귀속자를 명확히 하고(주주→배당·임원→상여·법인→기타사외유출), 회수·증빙 보완으로 "
                "사외유출 자체를 줄이는 것이 대표자 세부담 관점에서 유리합니다."
            ),
            legal_basis="영§106①",
            severity="중간",
        ))

    # 3. 업무무관자산 보유
    if getattr(mi, "non_business_asset_balance", 0):
        topics.append(ConsultingTopic(
            category="리스크",
            title="업무무관자산 보유",
            finding=f"업무무관자산 잔액 {mi.non_business_asset_balance:,}원으로 지급이자 손금불산입이 발생합니다.",
            suggestion="업무무관자산(비업무용 부동산·서화·회원권 등)의 처분 또는 업무 관련성 확보를 검토하세요.",
            legal_basis="법§27, 법§28①4호, 영§49·53",
            severity="중간",
        ))

    # ── 특례·감면 ─────────────────────────────────────────────────────────────
    # 4. 중소기업 감면·특례 누락 검토
    if getattr(company, "is_sme", False):
        topics.append(ConsultingTopic(
            category="특례·감면",
            title="중소기업 세액감면·공제 적용 검토",
            finding="중소기업에 해당합니다. 중소기업 대상 세액감면·공제 중 당기 미적용 항목이 있을 수 있습니다.",
            suggestion=(
                "중소기업특별세액감면(조특법§7), 통합투자세액공제(조특법§24), 고용증대 세액공제"
                "(조특법§29의7), 연구·인력개발비 세액공제(조특법§10) 등의 적용 요건·중복배제를 검토하세요. "
                "참고: 2026년 중소기업세제·세정지원제도."
            ),
            legal_basis="조특법§7·10·24·29의7 (요건·중복적용 배제 확인 필요)",
            severity="중간",
        ))

    # 5. 이월결손금 소멸 임박 — 당기 이익으로 공제 가능 여부
    _fy_year = fiscal_year_end.year
    for item in (mi.carryforward_losses or []):
        oy, amt = int(item.get("year", 0) or 0), int(item.get("amount", 0) or 0)
        if not oy or not amt:
            continue
        years_left = _loss_expiry_years(oy) - (_fy_year - oy)
        if 0 < years_left <= 1:
            topics.append(ConsultingTopic(
                category="특례·감면",
                title="이월결손금 소멸 임박",
                finding=f"{oy}년 발생 이월결손금 {amt:,}원이 차기({years_left}년 내) 공제기한 만료로 소멸 예정입니다.",
                suggestion=(
                    "소멸 전 당기·차기 과세소득으로 공제하거나, 결손금 소급공제(중소기업, 법§72)·"
                    "자산처분 시기 조정 등으로 활용 가능한지 검토하세요."
                ),
                legal_basis="법§13①1호, 법§72",
                severity="높음",
            ))

    # ── 정책 ──────────────────────────────────────────────────────────────────
    # 6. 접대비/감가상각 반복 한도초과 — 지출·상각 정책
    if r.entertainment_excess:
        topics.append(ConsultingTopic(
            category="정책",
            title="기업업무추진비 한도초과",
            finding=f"기업업무추진비 한도초과 {r.entertainment_excess:,}원이 손금불산입되었습니다.",
            suggestion="한도는 법인 규모·수입금액으로 정해집니다. 지출 시기·증빙(적격) 관리와 문화비 한도 활용을 검토하세요.",
            legal_basis="법§25④·⑤",
            severity="낮음",
        ))
    if r.depreciation_excess:
        topics.append(ConsultingTopic(
            category="정책",
            title="감가상각비 한도초과",
            finding=f"감가상각비 한도초과 {r.depreciation_excess:,}원이 부인(유보)되었습니다.",
            suggestion="부인액은 향후 한도 미달 연도에 추인됩니다. 상각방법·내용연수 신고와 즉시상각의제 활용을 검토하세요.",
            legal_basis="법§23, 영§26~31",
            severity="낮음",
        ))

    # 7. 간주임대료/부동산 — 토지등 양도소득 추가과세 등
    if getattr(company, "is_rental_main", False) or r.deemed_rental:
        topics.append(ConsultingTopic(
            category="정책",
            title="부동산임대·양도 관련 검토",
            finding="부동산임대업 주업이거나 간주임대료가 발생했습니다.",
            suggestion=(
                "보증금 운용수익으로 간주익금을 줄일 수 있고, 토지등 양도 시 추가과세(법§55의2)·"
                "비사업용토지 여부를 사전 검토하세요."
            ),
            legal_basis="조특법§138, 조특령§132, 법§55의2",
            severity="낮음",
        ))

    topics.sort(key=lambda t: (_CAT_ORDER.get(t.category, 9), _SEV_ORDER.get(t.severity, 9)))
    return topics
