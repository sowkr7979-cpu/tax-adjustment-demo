"""건별 질문형 수기입력 — 항목별 질문 스펙 카탈로그.

각 ReviewItemSpec은 법령 요건을 질문 흐름·게이트로 선언한다(law-compliance 리뷰 반영).
스펙은 코드 정의(람다 포함)이므로 .taxproj엔 답(answers)만 저장한다.
"""
from __future__ import annotations

from src.ui.review_questions import Question, DispositionRule, ReviewItemSpec


# ── 부당행위계산 부인 (법§52, 영§88③, 영§89) ─────────────────────────────────
# 거래유형 → 영§88① 각 호. 영§88③(시가차액 3억 또는 5%) 적용 대상은 1·3·6·7·9호.
#   금전 대여(6호)는 '인정이자' 트랙에서 거래상대방별 적수로 계산(통산금지) → 여기서 제외.
_UNFAIR_TYPES_GATED = ("고가매입(1호)", "저가양도(3호)", "고가차용(7호)", "기타 부당행위(9호)")
_UNFAIR_TYPES_FULL = ("무수익자산 매입·비용부담(2호)", "자본거래(8호)")  # 게이트 없이 전액 부인
_UNFAIR_TYPES = ("해당없음",) + _UNFAIR_TYPES_GATED + _UNFAIR_TYPES_FULL


def _unfair_diff(a: dict) -> int:
    """부인액 = |시가 − 거래가액| (이전된 이익). 무상이전은 거래가액 0."""
    if a.get("type") in ("해당없음", None):
        return 0
    return abs(int(a.get("market", 0) or 0) - int(a.get("deal", 0) or 0))


def _unfair_gate(a: dict) -> bool:
    """영§88③: 1·3·6·7·9호는 차액 ≥ 3억 또는 시가 5% 이상일 때만 적용.
    2·4·5·8호(무수익자산·자본거래 등)는 게이트 없이 전액 부인."""
    t = a.get("type")
    if t in _UNFAIR_TYPES_FULL:
        return True
    if t in _UNFAIR_TYPES_GATED:
        diff = _unfair_diff(a)
        market = int(a.get("market", 0) or 0)
        return diff >= 300_000_000 or (market > 0 and diff >= market * 0.05)
    return False  # 해당없음 등


def unfair_transaction_spec() -> ReviewItemSpec:
    return ReviewItemSpec(
        key="부당행위계산 부인",
        legal_basis="법§52, 영§88③, 영§89",
        unit="line",
        detect_account_keywords=(),  # 특수관계인 거래는 거래처 매칭으로 calc/ui에서 후보 추출
        questions=[
            Question(
                "type", "거래유형 (영§88①)", "select", options=_UNFAIR_TYPES,
                help="금전 대여(영§88①6호)는 여기서 입력하지 마세요 — '가지급금 인정이자'에서 "
                     "거래상대방별 적수로 계산됩니다(상대방 간 통산 금지, 영§88③).",
            ),
            Question(
                "market", "시가 (원, 영§89)", "amount",
                show_when=(("type", _UNFAIR_TYPES_GATED + _UNFAIR_TYPES_FULL),),
                help="감정가액·상증법 평가 등으로 산정한 시가. 무상이전이면 이전된 자산의 시가.",
            ),
            Question(
                "deal", "거래가액 (원)", "amount",
                show_when=(("type", _UNFAIR_TYPES_GATED + _UNFAIR_TYPES_FULL),),
                help="실제 거래가액. 무상이전이면 0.",
            ),
            Question(
                "who", "귀속자 (영§106 소득처분)", "select",
                options=("주주", "임원·직원", "법인등", "불분명"),
                show_when=(("type", _UNFAIR_TYPES_GATED + _UNFAIR_TYPES_FULL),),
                help="귀속자에 따라 배당/상여/기타사외유출. 불분명 시 대표자상여.",
            ),
        ],
        amount_fn=_unfair_diff,
        gate_fn=_unfair_gate,
        disposition=DispositionRule(
            by_question="who",
            mapping={"주주": "배당", "임원·직원": "상여", "법인등": "기타사외유출",
                     "불분명": "대표자상여"},
        ),
        target_label="부당행위계산 부인",
        add_or_deduct="add",
        reserve_field=None,  # 사외유출 — 을표 비대상
    )


# ── 복리후생비 (영§45①) ──────────────────────────────────────────────────────
# 영§45① 열거 8항목(직장체육·문화·회식·우리사주·건강/요양보험·어린이집·고용보험·경조사 등)은
# 손금 인정 → '열거 외 비용'만 손금불산입(1차 게이트), 그 뒤 귀속자로 소득처분(영§106).
_WELFARE_CATEGORIES = (
    "직장체육비(1호)", "직장문화비(2호)", "직장회식비(2의2호)", "우리사주조합운영비(3호)",
    "건강·장기요양보험 사용자부담(5호)", "직장어린이집 운영비(6호)", "고용보험 사용자부담(7호)",
    "경조사비 등 유사비용(8호)", "열거 외 비용",
)
_WELFARE_WHO = ("임원·직원(상여)", "주주(배당)", "불분명(대표자상여)")


def welfare_spec() -> ReviewItemSpec:
    return ReviewItemSpec(
        key="복리후생비 (열거 외)",
        legal_basis="영§45①",
        unit="line",
        detect_account_keywords=("복리후생비", "복리시설비"),
        questions=[
            Question(
                "category", "지출 성격 (영§45① 열거)", "select", options=_WELFARE_CATEGORIES,
                help="1~8호 열거항목(경조사비 등 사회통념상 유사비용 포함)은 손금 인정. "
                     "'열거 외 비용'만 손금불산입 검토 대상.",
            ),
            Question(
                "amount", "손금불산입 금액 (원)", "amount",
                show_when=(("category", "열거 외 비용"),),
            ),
            Question(
                "who", "귀속자 (영§106 소득처분)", "select", options=_WELFARE_WHO,
                show_when=(("category", "열거 외 비용"),),
                help="임직원 귀속=상여, 주주=배당, 불분명=대표자상여.",
            ),
        ],
        amount_fn=lambda a: int(a.get("amount", 0) or 0) if a.get("category") == "열거 외 비용" else 0,
        gate_fn=lambda a: a.get("category") == "열거 외 비용",
        disposition=DispositionRule(
            by_question="who",
            mapping={"임원·직원(상여)": "상여", "주주(배당)": "배당",
                     "불분명(대표자상여)": "대표자상여"},
        ),
        target_label="복리후생비 (열거 외)",
        add_or_deduct="add",
        reserve_field=None,
    )


# ── 의제배당 (법§16①) ────────────────────────────────────────────────────────
# 사유별: 1·4·5·6호 = 교부재산가액 − 주식취득가액(초과분), 2호(무상증자) = 교부주식가액 전부
# (취득가액 차감 없음). 2호 단서: 상법§459① 자본준비금·자산재평가적립금 자본전입은 제외(게이트).
_DD_CAUSES = (
    "감자·소각·퇴사(1호)", "잉여금 자본전입=무상증자(2호)",
    "해산·잔여재산분배(4호)", "합병(5호)", "분할(6호)",
)
_DD_COST_CAUSES = ("감자·소각·퇴사(1호)", "해산·잔여재산분배(4호)", "합병(5호)", "분할(6호)")


def deemed_dividend_spec():
    return ReviewItemSpec(
        key="의제배당",
        legal_basis="법§16①",
        unit="line",
        detect_account_keywords=("의제배당",),
        questions=[
            Question("cause", "의제배당 사유 (법§16①)", "select", options=_DD_CAUSES),
            Question(
                "excluded_reserve",
                "자본전입 재원이 상법§459① 자본준비금 또는 자산재평가적립금인가?", "select",
                options=("예(의제배당 제외)", "아니오(이익잉여금 등)"),
                show_when=(("cause", "잉여금 자본전입=무상증자(2호)"),),
                help="법§16①2호 단서 — 자본준비금·재평가적립금 자본전입은 의제배당 아님. "
                     "단 자산재평가법§13①1호 토지 재평가차액은 제외의 예외(=의제배당 대상).",
            ),
            Question("received", "교부 재산·주식 가액 (원)", "amount",
                     show_when=(("cause", _DD_CAUSES),)),
            Question("cost", "주식 취득가액 (원)", "amount",
                     show_when=(("cause", _DD_COST_CAUSES),),
                     help="감자·해산·합병·분할만 차감. 무상증자(2호)는 취득가액 차감 없음."),
        ],
        amount_fn=lambda a: (
            int(a.get("received", 0) or 0)
            if a.get("cause") == "잉여금 자본전입=무상증자(2호)"
            else max(0, int(a.get("received", 0) or 0) - int(a.get("cost", 0) or 0))
        ),
        gate_fn=lambda a: not (
            a.get("cause") == "잉여금 자본전입=무상증자(2호)"
            and a.get("excluded_reserve") == "예(의제배당 제외)"
        ),
        disposition=None,  # 익금산입(자기 익금) — 소득처분 不요
        target_label="의제배당",
        add_or_deduct="add",
        reserve_field=None,
    )


# ── 재고자산 평가 (영§74④) ───────────────────────────────────────────────────
# 무신고/임의평가/변경무신고 → 선입선출(매매목적 부동산=개별법). 단서: 신고방법 평가액이
# 선입선출보다 크면 신고방법 적용. 적법신고면 조정 없음. 처분 유보(reserve_field로 을표 연계).
_INV_FILING = ("적법신고", "무신고", "신고방법 외 평가", "변경 무신고")
_INV_NEED_FILED = ("신고방법 외 평가", "변경 무신고")          # 신고방법 평가액 비교 필요
_INV_NEED_FIFO = ("무신고", "신고방법 외 평가", "변경 무신고")  # 선입선출 평가액 필요


def _inventory_amount(a: dict) -> int:
    """세무상 평가액 − 장부평가액 (가산 유보). 영§74④ 단서 max() 반영, add-only."""
    fs = a.get("filing_status")
    book = int(a.get("book_value", 0) or 0)
    if fs in (None, "적법신고"):
        return 0
    fifo = int(a.get("fifo_value", 0) or 0)
    if fs == "무신고":
        tax = fifo                                  # 무신고=선입선출(부동산 개별법), 단서 미적용
    else:  # 신고방법 외 평가·변경 무신고 → 단서: max(선입선출, 신고방법 평가액)
        tax = max(fifo, int(a.get("filed_method_value", 0) or 0))
    return max(0, tax - book)                        # 평가감 부인분(가산). 과대계상은 별도(수기)


def inventory_spec():
    return ReviewItemSpec(
        key="재고자산 평가",
        legal_basis="법§42, 영§74④",
        unit="category",
        questions=[
            Question("filing_status", "평가방법 신고 상태", "select", options=_INV_FILING),
            Question("is_realestate", "매매 목적 보유 부동산인가? (무신고 시 개별법)", "yesno",
                     show_when=(("filing_status", _INV_NEED_FIFO),)),
            Question("book_value", "회사 장부상 평가액 (원)", "amount",
                     show_when=(("filing_status", _INV_NEED_FIFO),)),
            Question("filed_method_value", "신고한 평가방법에 의한 평가액 (원)", "amount",
                     show_when=(("filing_status", _INV_NEED_FILED),),
                     help="영§74④ 단서 — 신고방법 평가액이 선입선출보다 크면 신고방법 적용."),
            Question("fifo_value", "선입선출법(부동산=개별법) 평가액 (원)", "amount",
                     show_when=(("filing_status", _INV_NEED_FIFO),)),
        ],
        amount_fn=_inventory_amount,
        gate_fn=lambda a: a.get("filing_status") not in (None, "적법신고"),
        disposition=None,             # 유보 (사외유출 아님) — summary_rows 기존 행이 유보 표기
        target_label="재고자산 평가 조정",
        add_or_deduct="add",
        reserve_field="inventory_adjustment",  # 을표 연계 (자본금과적립금(을) 유보)
    )


# ── 임원 퇴직금 한도초과 (영§44④⑤) ──────────────────────────────────────────
# 정관에 금액·계산기준(위임 퇴직급여규정 포함)이 있으면 그 금액이 한도(영§44④1호·⑤).
# 없으면 퇴직 전 1년 총급여 × 1/10 × 근속연수(2호). 초과액 손금불산입(상여).
def _officer_retire_excess(a: dict) -> int:
    paid = int(a.get("paid_amount", 0) or 0)
    if a.get("has_articles") == "있음":
        limit = int(a.get("articles_limit", 0) or 0)
    else:
        salary = int(a.get("total_salary_1y", 0) or 0)
        years = float(a.get("service_years", 0) or 0)
        limit = int(salary * 0.1 * years)
    return max(0, paid - limit)


def officer_retirement_spec():
    return ReviewItemSpec(
        key="임원 퇴직금 한도초과",
        legal_basis="법§26, 영§44④⑤",
        unit="item",
        questions=[
            Question("has_articles",
                     "정관에 임원 퇴직급여 금액·계산기준이 있는가? (위임 퇴직급여규정 포함)",
                     "select", options=("있음", "없음"), help="영§44④1호·⑤ — 있으면 정관금액이 한도."),
            Question("articles_limit", "정관규정상 퇴직급여 한도액 (원)", "amount",
                     show_when=(("has_articles", "있음"),)),
            Question("total_salary_1y", "퇴직 전 1년 총급여액 (원, 손금불산입 상여 제외)", "amount",
                     show_when=(("has_articles", "없음"),),
                     help="영§44④2호 — 손금불산입된 임원상여(영§43)는 제외."),
            Question("service_years", "근속연수 (년)", "number",
                     show_when=(("has_articles", "없음"),)),
            Question("paid_amount", "실제 지급 퇴직급여 (원)", "amount"),
        ],
        amount_fn=_officer_retire_excess,
        disposition=None,             # 상여 (사외유출) — summary_rows 기존 행이 상여 표기
        target_label="임원 퇴직금 한도초과",
        add_or_deduct="add",
        reserve_field=None,
    )


# ── 임원 상여 한도초과 (영§43②) ──────────────────────────────────────────────
# 정관·주총·사원총회·이사회 결의 급여지급기준 초과 상여금 손금불산입. 기준 없으면 전액(기준=0).
# 직원이면 영§43② 미적용(게이트 탈락).
def officer_bonus_spec():
    return ReviewItemSpec(
        key="임원 상여금 한도초과",
        legal_basis="법§26, 영§43②",
        unit="item",
        questions=[
            Question("is_officer", "지급대상이 임원인가? (직원이면 미적용)", "yesno"),
            Question("has_standard",
                     "정관·주총·사원총회·이사회 결의로 정한 급여지급기준이 있는가?", "select",
                     options=("있음", "없음"), show_when=(("is_officer", True),),
                     help="영§43② — 기준 없으면 지급액 전액이 손금불산입(기준=0)."),
            Question("standard_amount", "급여지급기준상 한도액 (원)", "amount",
                     show_when=(("is_officer", True), ("has_standard", "있음"))),
            Question("paid_amount", "실제 지급 상여금 (원)", "amount",
                     show_when=(("is_officer", True),)),
        ],
        amount_fn=lambda a: max(0, int(a.get("paid_amount", 0) or 0)
                                - (int(a.get("standard_amount", 0) or 0)
                                   if a.get("has_standard") == "있음" else 0)),
        gate_fn=lambda a: a.get("is_officer") is True,
        disposition=None,             # 상여 (사외유출) — summary_rows 기존 행이 상여 표기
        target_label="임원 상여금 한도초과",
        add_or_deduct="add",
        reserve_field=None,
    )


# 항목키 → 스펙 팩토리 (UI/calc 공용 레지스트리)
REVIEW_SPECS = {
    "부당행위계산 부인": unfair_transaction_spec,
    "복리후생비 (열거 외)": welfare_spec,
    "의제배당": deemed_dividend_spec,
    "재고자산 평가": inventory_spec,
    "임원 퇴직금 한도초과": officer_retirement_spec,
    "임원 상여금 한도초과": officer_bonus_spec,
}
