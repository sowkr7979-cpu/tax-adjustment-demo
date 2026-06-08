"""업무용승용차 근거분개 ↔ 차량 매칭 (차량번호 기준).

목적: 업무용승용차 관련비용 근거분개를 차량별로 정확히 귀속한다.
  - 분개의 차량번호(차량번호 컬럼 또는 적요)가 **등록 차량과 정확히 일치**할 때만 그 차량 건으로 본다.
  - 적요·차량번호에 **다른 차량의 번호**가 식별되면 해당 차량 근거에서 제외(오매칭 방지).
  - 차량번호·차종을 식별할 수 없는 분개(공통 유지비 등)는 **우선 포함**한다.

세무조정 금액(agg.vehicle_expense)은 계정과목 기준으로 별도 집계되므로 이 필터는 금액을 바꾸지 않는다 —
근거분개 '표시'의 정확성(감사추적)만 개선한다.
"""
from __future__ import annotations

import re

from src.utils.models import JournalLine, FixedAsset

# 한국 자동차 번호판: (지역) 2~3자리 + 한글 1자 + 4자리. 예: 12가3456 / 123허4567 / 서울12가3456.
# 공백은 사전 제거 후 매칭한다.
_PLATE_RE = re.compile(r"\d{2,3}[가-힣]\d{4}")


def extract_plate(text: str | None) -> str | None:
    """문자열에서 차량번호(번호판) 토큰을 추출. 없으면 None.

    공백 제거 후 정규식 매칭 — '12가 3456', '12가3456' 모두 '12가3456'으로 정규화.
    """
    if not text:
        return None
    m = _PLATE_RE.search(str(text).replace(" ", ""))
    return m.group(0) if m else None


def line_plate(ln: JournalLine) -> str | None:
    """분개 라인의 차량번호 — 차량번호 컬럼 우선, 없으면 적요에서 추출."""
    return extract_plate(getattr(ln, "vehicle_no", "")) or extract_plate(ln.description)


def registered_plates(assets: list[FixedAsset]) -> set[str]:
    """업무용승용차로 체크된 자산명에서 추출한 차량번호 집합."""
    plates = set()
    for a in assets:
        p = extract_plate(a.asset_name)
        if p:
            plates.add(p)
    return plates


def filter_vehicle_lines(
    lines: list[JournalLine],
    plates: set[str],
) -> tuple[list[JournalLine], list[JournalLine]]:
    """업무용승용차 근거분개 풀을 (표시용 kept, 타차량 foreign)으로 분리.

    규칙:
      - 차량번호 식별 불가(공통) → kept (우선 포함).
      - 식별된 번호가 등록 차량과 일치 → kept.
      - 식별된 번호가 등록 차량에 없음(= 다른 차량) → foreign (해당 차량 근거에서 제외).
    plates가 비어 있으면(등록 차량의 번호를 알 수 없음) 타차량 판정이 불가하므로 전부 kept로 둔다.
    """
    if not plates:
        return list(lines), []
    kept: list[JournalLine] = []
    foreign: list[JournalLine] = []
    for ln in lines:
        p = line_plate(ln)
        if p is None or p in plates:
            kept.append(ln)        # 식별불가(공통) 또는 등록 차량 일치 → 포함
        else:
            foreign.append(ln)     # 등록 외 다른 차량번호 → 제외
    return kept, foreign


def attribute_by_vehicle(
    assets: list[FixedAsset],
    lines: list[JournalLine],
) -> dict[str, list[JournalLine]]:
    """차량(asset_code)별 정확 매칭 분개. 공통(번호 식별불가) 라인은 '__공통__' 키에 모은다."""
    plate_of = {a.asset_code: extract_plate(a.asset_name) for a in assets}
    per: dict[str, list[JournalLine]] = {a.asset_code: [] for a in assets}
    per["__공통__"] = []
    for ln in lines:
        p = line_plate(ln)
        if p is None:
            per["__공통__"].append(ln)
            continue
        matched = [code for code, ap in plate_of.items() if ap and ap == p]
        for code in matched:
            per[code].append(ln)
        # 매칭 없으면(다른 차량) 어느 차량에도 귀속하지 않는다
    return per
