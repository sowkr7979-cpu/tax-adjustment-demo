"""세무 컨설팅 토픽 엔진 — 회사정보·재무제표·세무조정 결과 기반 결정론적 발굴.

설계 원칙 (KICPA·law·security 리뷰 합의):
  - 토픽·회사 숫자·법령 근거는 **규칙엔진이 결정론적으로** 산출 (LLM 환각 배제).
  - 권고는 [현재상황]→[근거]→[결론(시나리오)]→[참고자료] 4섹션.
  - **결론은 '검토바람'으로 끝내지 않고 구체적 시나리오(행동·효과·요건·리스크)를 제시**한다.
  - 단, **시나리오는 복수 대안 옵션**이며 채택·확정은 회계사 판단 (ADR-002 — AI 판단 확정 금지).
  - 시나리오 effect의 금액은 규칙엔진 산출값만 인용 — 신규 금액 생성 금지(산출 불가 시 방향만).
  - LLM(consultant.py)은 scenario.action의 톤만 다듬는다 — effect·요건·숫자·법령엔 손대지 않는다.

산출물은 5·6단계 '세무 컨설팅 코멘트' 레이어로 표시되며, 회계사가 채택/기각 후 확정한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 이월결손금 공제기한 (법§13 부칙) — 소멸 임박 판정용
from src.rules.tax_base import eligible_carryforward_total  # noqa: F401  (기한 로직 일관성 참조)

# 시나리오는 대안 옵션이며 확정이 아님 — 렌더·PDF 공통 고정 문구 (ADR-002)
SCENARIO_DISCLAIMER = "아래 시나리오는 대안 옵션이며, 채택·확정은 회계사 판단입니다."


@dataclass
class Scenario:
    """[결론] 권고 시나리오 한 개 — 행동·효과·요건·리스크 (대안 옵션)."""
    name: str            # "시나리오 A: 가지급금 조기 회수"
    action: str          # 행동 — 회계사가 클라이언트에 제시할 구체 조치 (LLM 톤 다듬기 대상)
    effect: str          # 효과 — 회사 숫자 기반(규칙엔진 산출값만) 또는 방향
    requirement: str = ""  # 요건 — 법령 요건
    risk: str = ""         # 리스크 — 선택 시 부작용
    needs_law_check: bool = False   # 요건 충족이 사실판단 → "회계사 확인 필요"


@dataclass
class ConsultingTopic:
    category: str        # "리스크" | "특례·감면" | "정책"
    title: str
    severity: str        # "높음" | "중간" | "낮음"
    situation: str       # [현재상황] 회사 숫자 기반 발견 (규칙엔진 산출 — LLM 아님)
    basis: str           # [근거] 법령 + 산출 논리 (규칙엔진)
    scenarios: list[Scenario] = field(default_factory=list)  # [결론] 대안 옵션
    legal_basis: str = ""   # 조문 매핑 (basis 보조 — 키워드·PDF 표시용)
    severity_note: str = ""
    status: str = "검토필요 (요건 확인·미확정 — 채택·확정은 회계사 판단)"   # ADR-002
    keywords: tuple = ()                    # 참고파일 RAG 검색어 (reference_retriever)
    references: list = field(default_factory=list)  # [참고자료] enrich로 채워지는 발췌


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
    _fy_year = fiscal_year_end.year
    topics: list[ConsultingTopic] = []

    # ── 리스크 ────────────────────────────────────────────────────────────────
    # 1. 가지급금/가수금 정리 — 인정이자 + 4호이자 + 대표자상여 동시 리스크
    _loan_opening = sum(int(p.get("opening", 0)) for p in (mi.related_loan_parties or [])) \
        or mi.related_loan_balance or mi.related_loan_opening
    if r.deemed_interest or r.interest_non_business or _loan_opening:
        topics.append(ConsultingTopic(
            category="리스크", severity="높음",
            title="특수관계인 가지급금 정리",
            situation=(
                f"가지급금 인정이자 익금산입 {r.deemed_interest:,}원, "
                f"업무무관자산 지급이자 손금불산입 {r.interest_non_business:,}원이 발생했습니다. "
                "미회수 시 대표자 상여 처분 리스크가 함께 존재합니다."
            ),
            basis=(
                "인정이자(법§52·영§88①6호·89③)·업무무관자산 지급이자 손금불산입(법§28①4호·영§53)·"
                "미회수분 대표자 상여 처분(영§106①)이 동시에 적용됩니다."
            ),
            scenarios=[
                Scenario(
                    name="시나리오 A — 조기 회수·가수금 상계",
                    action="결산일 전 가지급금을 현금 회수하거나 동일인 가수금과 상계합니다.",
                    effect="차기 인정이자 익금산입·업무무관 지급이자 손금불산입이 소멸하고 대표자 상여처분 "
                           "리스크가 제거됩니다(감소액은 회수 시점·금액 확정 후 재계산).",
                    requirement="가수금 상계는 동일인 요건(영§53③ — 지급이자 적수계산상 상계). "
                                "인정이자는 거래상대방별로 계산(상대방 간 통산 금지).",
                    risk="대표 개인자금 회수 시 자금출처. 연말 일시상환 후 연초 재대여는 부당행위로 부인될 수 있습니다.",
                    needs_law_check=True,
                ),
                Scenario(
                    name="시나리오 B — 약정이자율 상향(회수 곤란 시)",
                    action="약정이자율을 가중평균차입이자율(또는 요건 충족 시 당좌대출이자율) 이상으로 설정·수취합니다.",
                    effect="적정이자율 적용 시 시가차액이 발생하지 않아 인정이자 익금산입액이 축소됩니다"
                           "(금액은 영§89③ 기준율로 재계산).",
                    requirement="적정이자율은 가중평균차입이자율이 원칙이며, 당좌대출이자율은 선택요건 충족 시 적용(영§89③).",
                    risk="법인 이자수익 과세·대표 이자부담. 이자율 기준·당좌대출이자율 선택요건 확인이 필요합니다.",
                    needs_law_check=True,
                ),
            ],
            legal_basis="법§28①4호, 법§52, 영§88①6호·89③, 영§53③, 영§106①",
            keywords=("가지급금", "인정이자", "특수관계", "가수금", "지급이자"),
        ))

    # 2. 소득처분(대표자 상여) 최소화
    if r.deemed_interest or r.interest_unknown_creditor or (r.vehicle_disallowed - r.vehicle_depr_excess) > 0:
        topics.append(ConsultingTopic(
            category="리스크", severity="중간",
            title="소득처분(대표자 상여) 최소화",
            situation=(
                "사외유출 항목(가지급금 인정이자·채권자불분명이자·승용차 개인사용분 등)이 "
                "대표자 상여로 처분되면 대표자 종합소득세까지 추가로 발생할 수 있습니다."
            ),
            basis="귀속자별 소득처분(영§106① — 주주 배당·임원 상여·법인 기타사외유출). "
                  "귀속 불분명 시 대표자 상여로 의제됩니다.",
            scenarios=[
                Scenario(
                    name="시나리오 A — 귀속자 확정·증빙 보완",
                    action="사외유출 항목의 실질 귀속자를 확정하고(주주→배당·임원→상여·법인→기타사외유출), "
                           "계약서·영수증으로 손금성을 입증합니다.",
                    effect="상여처분 축소 시 대표자 종합소득세·gross-up 부담이 감소합니다.",
                    requirement="귀속이 불분명하면 대표자 상여로 의제(영§106①).",
                    risk="사후 귀속 변경은 수정신고·경정청구를 동반합니다.",
                ),
                Scenario(
                    name="시나리오 B — 가지급금 회수 연계",
                    action="대표자 귀속 가지급금을 회수하여 상여 처분 대상 자체를 줄입니다('가지급금 정리' 토픽 연계).",
                    effect="사외유출액 자체가 축소되어 대표자 상여 처분이 감소합니다.",
                    requirement="회수·상계 요건은 가지급금 정리 토픽과 동일.",
                    risk="연말 일시회수 후 재대여는 부당행위 소지.",
                    needs_law_check=True,
                ),
            ],
            legal_basis="영§106①",
            keywords=("소득처분", "상여", "사외유출", "대표자", "귀속"),
        ))

    # 3. 업무무관자산 보유
    if getattr(mi, "non_business_asset_balance", 0):
        topics.append(ConsultingTopic(
            category="리스크", severity="중간",
            title="업무무관자산 보유",
            situation=f"업무무관자산 잔액 {mi.non_business_asset_balance:,}원으로 지급이자 손금불산입이 발생합니다.",
            basis="업무무관자산(비업무용 부동산·서화·골동품·자동차 등, 영§49) 보유 시 "
                  "관련 지급이자 손금불산입(법§28①4호)·업무무관비용 손금불산입(법§27).",
            scenarios=[
                Scenario(
                    name="시나리오 A — 처분",
                    action="비업무용 부동산·서화·회원권 등 업무무관자산을 처분합니다.",
                    effect="처분 후 차기 지급이자 손금불산입 해당분이 소멸합니다.",
                    risk="처분손익 과세. 비사업용토지면 토지등 양도소득 추가과세(법§55의2)가 연계됩니다.",
                    needs_law_check=True,
                ),
                Scenario(
                    name="시나리오 B — 업무 관련성 확보",
                    action="임대 전환 등 실제 업무사용을 입증해 업무무관 판정에서 제외합니다.",
                    effect="업무관련 자산으로 인정되면 지급이자 손금불산입이 해소됩니다.",
                    requirement="업무무관자산 판정기준(영§49) 충족 여부 확인.",
                    risk="사용 실질 입증 부담.",
                    needs_law_check=True,
                ),
            ],
            legal_basis="법§27, 법§28①4호, 영§49·53",
            keywords=("업무무관", "비업무용", "지급이자", "부동산"),
        ))

    # ── 특례·감면 ─────────────────────────────────────────────────────────────
    # 4. 중소기업 감면·특례 누락 검토 (고용 세액공제는 efYd 분기)
    if getattr(company, "is_sme", False):
        # 조특§29의7(고용증대)은 2024 과세연도 한정 → 2025년 이후는 통합고용 §29의8
        if _fy_year <= 2024:
            _emp = Scenario(
                name="시나리오 B — 고용증대 세액공제(조특§29의7)",
                action="상시근로자 증가 인원을 산정해 고용증대 세액공제를 적용합니다.",
                effect="증가 인원당 공제(청년·정규직 가산), 3년 사후관리.",
                requirement="상시근로자 수 전기 대비 증가. 조특§29의7은 2024 과세연도까지 적용.",
                risk="사후 인원 감소 시 추징. 공제율·중복배제 확인 필요.",
                needs_law_check=True,
            )
        else:
            _emp = Scenario(
                name="시나리오 B — 통합고용 세액공제(조특§29의8)",
                action="상시근로자 증가 인원을 산정해 통합고용 세액공제를 적용합니다(2025년 이후 §29의7 대체).",
                effect="증가 인원당 공제, 사후관리.",
                requirement="상시근로자 수 전기 대비 증가. 2025년 이후 개시 사업연도는 §29의8 적용.",
                risk="사후 인원 감소 시 추징. 공제율·중복배제 확인 필요.",
                needs_law_check=True,
            )
        topics.append(ConsultingTopic(
            category="특례·감면", severity="중간",
            title="중소기업 세액감면·공제 적용 검토",
            situation="중소기업에 해당합니다. 중소기업 대상 세액감면·공제 중 당기 미적용 항목이 있을 수 있습니다.",
            basis="통합투자세액공제(조특§24)·고용 세액공제(조특§29의7·29의8)·중소기업특별세액감면(조특§7) 등은 "
                  "최저한세(조특§132)·중복배제 한도 내에서 적용됩니다.",
            scenarios=[
                Scenario(
                    name="시나리오 A — 통합투자세액공제(조특§24)",
                    action="당기 사업용 유형자산 투자액을 확인해 기본공제를 적용합니다.",
                    effect="산출세액에서 직접 차감(최저한세 적용 후) — 금액은 투자액 입력 후 산출.",
                    requirement="투자완료·자산명세, 최저한세(조특§132) 한도 내.",
                    risk="2년 내 처분 시 추징.",
                    needs_law_check=True,
                ),
                _emp,
                Scenario(
                    name="시나리오 C — 감면·공제 택일(중복배제 확인)",
                    action="중소기업특별세액감면(조특§7)과 투자·고용 공제 중 유리한 것을 택일합니다.",
                    effect="산출세액 감면 또는 공제 — 더 큰 절세효과를 선택.",
                    requirement="감면·공제 중복배제·최저한세 한도 확인.",
                    risk="중복배제·최저한세로 실익이 축소될 수 있습니다.",
                    needs_law_check=True,
                ),
            ],
            legal_basis="조특§7·10·24·29의7·29의8·132 (요건·중복배제 확인 필요)",
            keywords=("중소기업", "세액감면", "통합투자", "고용증대", "연구", "특별세액감면"),
        ))

    # 5. 이월결손금 소멸 임박
    for item in (mi.carryforward_losses or []):
        oy, amt = int(item.get("year", 0) or 0), int(item.get("amount", 0) or 0)
        if not oy or not amt:
            continue
        years_left = _loss_expiry_years(oy) - (_fy_year - oy)
        if 0 < years_left <= 1:
            _sme = getattr(company, "is_sme", False)
            topics.append(ConsultingTopic(
                category="특례·감면", severity="높음",
                title="이월결손금 소멸 임박",
                situation=f"{oy}년 발생 이월결손금 {amt:,}원이 차기({years_left}년 내) 공제기한 만료로 소멸 예정입니다.",
                basis=f"이월결손금은 발생 후 {_loss_expiry_years(oy)}년 이내 공제(법§13①1호), "
                      f"공제한도는 {'중소기업 100%' if _sme else '일반법인 80%'}. "
                      "중소기업은 직전 사업연도 소급공제(법§72)도 가능합니다.",
                scenarios=[
                    Scenario(
                        name="시나리오 A — 당기 소득으로 흡수",
                        action="소멸 예정 결손금을 당기 각사업연도소득에서 우선 공제합니다.",
                        effect="소멸분 절세(흡수액 × 세율 — 금액은 과세표준·세율로 산출).",
                        requirement=f"공제한도 {'중소기업 100%' if _sme else '일반법인 80%'}(법§13①).",
                        risk="당기 소득이 부족하면 일부만 흡수됩니다.",
                        needs_law_check=True,
                    ),
                    Scenario(
                        name="시나리오 B — 소득 조기 실현(소득 부족 시)",
                        action="자산처분·수익인식 시기 조정으로 당기 소득을 늘려 소멸 전 결손금과 매칭합니다.",
                        effect="결손금 활용 + 처분이익 상쇄.",
                        risk="인위적 시기조정의 정당성·자산 매각 비용. 부당행위 소지 검토 필요.",
                        needs_law_check=True,
                    ),
                    Scenario(
                        name="시나리오 C — 결손금 소급공제(중소기업, 법§72)",
                        action="직전 사업연도 법인세 환급을 신청합니다.",
                        effect="즉시 현금 환급.",
                        requirement="중소기업 한정·직전연도 납부세액 존재·신고기한 내 신청(법§72).",
                        risk="소급은 직전 1년 한정 — 소멸 임박분 전액을 흡수하지 못할 수 있습니다.",
                        needs_law_check=True,
                    ),
                ],
                legal_basis="법§13①1호, 법§72",
                keywords=("이월결손금", "결손금", "소급공제", "공제기한"),
            ))

    # ── 정책 ──────────────────────────────────────────────────────────────────
    # 6. 기업업무추진비 한도초과 — 지출·증빙 정책
    if r.entertainment_excess:
        topics.append(ConsultingTopic(
            category="정책", severity="낮음",
            title="기업업무추진비 한도초과",
            situation=f"기업업무추진비 한도초과 {r.entertainment_excess:,}원이 손금불산입되었습니다.",
            basis="한도는 수입금액·법인 규모로 정해집니다(법§25④⑤). 문화기업업무추진비는 별도 추가한도(조특§136③)가 있습니다.",
            scenarios=[
                Scenario(
                    name="시나리오 A — 적격증빙·문화비 별도한도 활용",
                    action="건당 3만원 초과 지출은 적격증빙(신용카드·세금계산서)을 수취하고, "
                           "문화기업업무추진비 별도한도를 활용합니다.",
                    effect="비적격→적격 전환분과 문화비 별도한도 활용분이 손금으로 인정됩니다"
                           "(한도 자체는 수입금액·규모로 고정).",
                    requirement="적격증빙 요건·문화비 범위(조특§136③).",
                    risk="기본한도 자체는 증빙만으로 늘지 않으므로 과대 기대는 금물입니다.",
                ),
            ],
            legal_basis="법§25④·⑤, 조특§136③",
            keywords=("기업업무추진비", "접대비", "한도", "증빙", "문화비"),
        ))

    # 7. 감가상각비 한도초과 — 정보성(추인)
    if r.depreciation_excess:
        topics.append(ConsultingTopic(
            category="정책", severity="낮음",
            title="감가상각비 한도초과",
            situation=f"감가상각비 한도초과 {r.depreciation_excess:,}원이 부인(유보)되었습니다.",
            basis="상각부인액은 영구 손금부인이 아니라, 향후 시인부족액 발생 연도에 추인되는 유보 항목입니다(법§23, 영§26~31).",
            scenarios=[
                Scenario(
                    name="시나리오 A — 추인 대기(별도 조치 불요)",
                    action="부인액은 향후 한도 미달(시인부족) 연도에 자동 추인되므로 별도 조치가 필요 없습니다.",
                    effect="차기 이후 손금으로 추인됩니다(영구 손금부인 아님).",
                    requirement="상각방법·내용연수 신고 유지.",
                    risk="없음(정보성).",
                ),
                Scenario(
                    name="시나리오 B — 신고조정 정비",
                    action="상각방법·내용연수 신고와 즉시상각의제 적용 여부를 점검합니다.",
                    effect="상각 정책 정비로 향후 한도 활용도를 높일 수 있습니다.",
                    requirement="상각방법·내용연수 신고(영§26~28).",
                    risk="없음.",
                ),
            ],
            legal_basis="법§23, 영§26~31",
            keywords=("감가상각", "내용연수", "즉시상각", "상각방법"),
        ))

    # 8. 부동산임대·양도 관련
    if getattr(company, "is_rental_main", False) or r.deemed_rental:
        topics.append(ConsultingTopic(
            category="정책", severity="낮음",
            title="부동산임대·양도 관련 검토",
            situation=f"부동산임대업 주업이거나 간주임대료 {r.deemed_rental:,}원이 발생했습니다.",
            basis="임대보증금 간주익금(조특§138·조특령§132)은 보증금 운용 금융수익으로 차감되며, "
                  "토지등 양도 시 추가과세(법§55의2)·비사업용토지 여부를 사전 검토해야 합니다.",
            scenarios=[
                Scenario(
                    name="시나리오 A — 보증금 운용수익으로 간주익금 축소",
                    action="임대보증금을 금융자산으로 운용해 운용수익을 계상합니다.",
                    effect=f"간주익금({r.deemed_rental:,}원)이 운용수익만큼 차감됩니다.",
                    requirement="추계 외 실제 운용수익(이자·배당 등) 입증.",
                    risk="운용수익 자체는 과세됩니다.",
                ),
                Scenario(
                    name="시나리오 B — 토지등 양도 사전검토",
                    action="토지등 양도 전 비사업용토지 해당 여부와 추가과세(법§55의2)를 사전 진단합니다.",
                    effect="추가과세 대상·세율을 사전에 파악해 양도 시기·구조를 조정할 수 있습니다.",
                    requirement="비사업용토지 판정(보유기간·지목·사용현황).",
                    risk="양도 시점 추가과세.",
                    needs_law_check=True,
                ),
            ],
            legal_basis="조특§138, 조특령§132, 법§55의2",
            keywords=("부동산임대", "간주임대료", "보증금", "양도", "비사업용토지"),
        ))

    topics.sort(key=lambda t: (_CAT_ORDER.get(t.category, 9), _SEV_ORDER.get(t.severity, 9)))
    return topics
