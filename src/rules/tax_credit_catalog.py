"""조세특례제한법 세액공제·감면 — 산식 구조 + 최저한세·농특세 자동판정 카탈로그.

설계 원칙 (CLAUDE.md):
- 변동이 잦은 '공제율·감면율'(업종·지역·규모·연도별 별표)은 하드코딩하지 않고
  호출자가 현행 별표값을 파라미터로 전달한다. 엔진은 산식 '구조'만 책임진다.
- '최저한세 적용 여부'(조특§132)·'농특세 과세 여부'(농특세법§4·§5)는 법령상 안정적
  분류이므로 카탈로그로 자동판정한다.
- 모든 항목은 회계사 최종 확인 대상(초안 보조).
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class CreditSpec:
    """세액공제·감면 항목의 법령상 분류 (산식과 무관한 안정 속성)."""
    name: str
    article: str            # 조특법 조문
    subject_to_min_tax: bool  # 조특§132 최저한세 적용대상
    farm_surtax_taxable: bool  # 농특세법§5① 과세대상 (§4 비과세 제외)
    note: str = ""


# 카탈로그 — law.go.kr 조특§132(최저한세)·농특세법§4(비과세) 분류 기준.
# 최저한세·농특세 분류가 규모(중소/일반)에 따라 갈리는 항목은 note에 명시.
SPECIAL_TAX_CREDITS: dict[str, CreditSpec] = {
    "중소기업특별세액감면": CreditSpec(
        "중소기업특별세액감면", "조특§7", subject_to_min_tax=True, farm_surtax_taxable=False,
        note="농특세 비과세 (농특세법§4 3호). 최저한세 적용대상.",
    ),
    "통합투자세액공제": CreditSpec(
        "통합투자세액공제", "조특§24", subject_to_min_tax=True, farm_surtax_taxable=True,
        note="최저한세 적용·농특세 과세대상.",
    ),
    "연구인력개발비세액공제": CreditSpec(
        "연구·인력개발비 세액공제", "조특§10", subject_to_min_tax=False, farm_surtax_taxable=False,
        note="중소기업분은 최저한세 적용배제(조특§132①3호 괄호 '중소기업이 아닌 자만 해당')·농특세 비과세. "
             "일반기업 당기분은 최저한세 적용 — 규모 확인 후 조정.",
    ),
    "고용증대세액공제": CreditSpec(
        "고용증대세액공제", "조특§29의7", subject_to_min_tax=True, farm_surtax_taxable=True,
        note="최저한세 적용·농특세 과세대상.",
    ),
    "통합고용세액공제": CreditSpec(
        "통합고용세액공제", "조특§29의8", subject_to_min_tax=True, farm_surtax_taxable=True,
        note="최저한세 적용·농특세 과세대상.",
    ),
}


def lookup_credit_spec(name: str) -> CreditSpec | None:
    """항목명으로 분류 조회 (부분 일치 허용). 미등록이면 None."""
    key = (name or "").replace(" ", "").replace("·", "")
    for spec_key, spec in SPECIAL_TAX_CREDITS.items():
        if spec_key.replace("·", "") in key or key in spec_key.replace("·", ""):
            return spec
    return None


# ── 산식 구조 (변동 율은 파라미터) ──────────────────────────────────────────────

def calc_sme_special_reduction(
    *,
    business_income_tax: int,   # 감면 대상 사업장 소득에 대한 산출세액
    reduction_rate: float,      # 감면 비율 (조특§7② 별표 — 업종·지역·규모별, 현행값 입력)
    cap: int | None = None,     # 감면 한도 (조특§7③ — 고용 감소 시 차감 등, 현행 한도 입력)
) -> int:
    """중소기업특별세액감면 (조특§7) — 산출세액 × 감면비율, 한도 적용.

    감면비율(제2호)·한도(제3호)는 업종·지역·규모·고용에 따라 정해지는 별표값이므로
    호출자가 현행 기준으로 전달한다(엔진은 구조만 계산).
    """
    amount = int(max(0, business_income_tax) * max(0.0, reduction_rate))
    if cap is not None:
        amount = min(amount, max(0, cap))
    return amount


def calc_rnd_credit(
    *,
    current_expense: int,       # 당기 발생 연구·인력개발비 (대상비용)
    rate: float,                # 당기분 공제율 (조특§10① — 중소 25% 등, 현행값 입력)
    increase_expense: int = 0,  # 증가분 = 당기 − 직전기 (증가분 방식 선택 시)
    increase_rate: float = 0.0, # 증가분 공제율
) -> int:
    """연구·인력개발비 세액공제 (조특§10) — 당기분 또는 증가분 중 선택.

    당기분 = 당기 대상비용 × 당기분 공제율.
    증가분 = (당기 − 직전기) × 증가분 공제율 (증가분 방식 선택 시).
    공제율은 규모·연도별로 다르므로 현행값을 파라미터로 받는다. 둘 중 큰 값을 반환.
    """
    current = int(max(0, current_expense) * max(0.0, rate))
    incr = int(max(0, increase_expense) * max(0.0, increase_rate)) if increase_rate > 0 else 0
    return max(current, incr)


def calc_integrated_investment_credit(
    *,
    investment: int,            # 당기 투자액 (대상 자산)
    base_rate: float,           # 기본공제율 (조특§24① — 중소 10%·중견 5%·대기업 1% 등, 현행값)
    prior_3yr_avg: int = 0,     # 직전 3년 평균 투자액
    extra_rate: float = 0.0,    # 추가공제율 (직전 3년 평균 초과분, 조특§24①2호나목)
) -> int:
    """통합투자세액공제 (조특§24) — 기본공제 + 추가공제(직전 3년 평균 초과분).

    기본공제 = 당기 투자액 × 기본공제율.
    추가공제 = max(0, 당기 투자액 − 직전 3년 평균) × 추가공제율,
              단 **기본공제액의 2배를 한도**로 한다 (조특§24①2호나목, law.go.kr 확인).
    공제율은 자산·규모·연도별 별표값이므로 현행값을 파라미터로 받는다.
    """
    base = int(max(0, investment) * max(0.0, base_rate))
    extra = 0
    if extra_rate > 0:
        excess = max(0, investment - max(0, prior_3yr_avg))
        extra = min(int(excess * extra_rate), base * 2)   # 추가공제 ≤ 기본공제 × 2
    return base + extra
