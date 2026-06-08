"""소득처분 결정 — 영§106① (law.go.kr 원문 확인, efYd=2024-12-31).

영§106①1호: 사외유출이 분명한 경우 귀속자에 따라
  가. 주주등(임원·직원인 주주 제외) → 배당
  나. 임원·직원 → 상여
  다. 법인·사업영위 개인 → 기타사외유출
  라. 가~다 외의 자 → 기타소득
  단서. 귀속 불분명 → 대표자 상여
2호: 사외유출되지 않은 경우 → 사내유보

귀속자 확정은 회계사 판단(ADR-002) — 본 모듈은 선택된 귀속자 유형을 처분으로 매핑만 한다.
"""
from __future__ import annotations

# 귀속자 유형 (UI 선택지) — 영§106①1호 각 목 + 단서
ATTRIBUTION_TYPES = ["주주", "임원·직원", "법인등", "기타", "불분명"]

_ATTR_TO_DISPOSITION = {
    "주주": "배당",            # 가목
    "임원·직원": "상여",       # 나목
    "법인등": "기타사외유출",  # 다목
    "기타": "기타소득",        # 라목
    "불분명": "대표자상여",    # 1호 단서
}

# 귀속자 미선택 시 표시 (임의 확정 금지)
UNSET_DISPOSITION = "(귀속자 미정 — 검토필요)"


def resolve_disposition(attribution: str | None) -> str:
    """귀속자 유형 → 소득처분. 미선택/미지정이면 UNSET 표시."""
    if not attribution:
        return UNSET_DISPOSITION
    return _ATTR_TO_DISPOSITION.get(attribution, UNSET_DISPOSITION)


def split_unknown_creditor_interest(
    amount: int, withholding_equiv: int = 0,
) -> list[tuple[int, str]]:
    """채권자불분명 사채이자 처분 — 영§106①, 소득세 원천징수 연계.

    원천징수세액 상당액은 국가 귀속 → 기타사외유출, 잔액은 대표자 상여.
    withholding_equiv(원천세 상당액)이 0이면 전액 대표자상여(분리는 검토).
    반환: [(금액, 처분)] (금액 0 항목 제외)
    """
    wh = max(0, min(int(withholding_equiv), int(amount)))
    out = []
    if wh:
        out.append((wh, "기타사외유출"))
    rest = int(amount) - wh
    if rest:
        out.append((rest, "대표자상여"))
    return out
