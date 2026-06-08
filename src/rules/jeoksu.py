"""적수(積數) 계산 — 일별 잔액 × 경과일수 합계.

법령상 적수 기준 항목 (law.go.kr 원문 확인):
  가지급금 인정이자 (영§89⑤): 가지급금 적수 × 이자율 × 1/365
  업무무관자산 지급이자 (영§53②③): 자산가액·차입금을 적수로 계산, 동일인 가수금 상계
  간주임대료 (조특령§132①⑤): 보증금·차입금·자기자본 적수,
    "매월말 현재의 잔액에 경과일수를 곱하여 계산할 수 있다"

분개장의 거래 날짜·금액으로 일별 잔액을 재구성해 실제 적수를 계산한다.
기초잔액은 재무상태표 기초잔액 또는 수기 입력으로 보충한다.
"""
from __future__ import annotations

from datetime import date

from src.utils.models import JournalLine


def jeoksu_from_deltas(
    deltas: list[tuple[date, int]],
    fy_start: date,
    fy_end: date,
    opening: int = 0,
    floor_zero: bool = True,
) -> int:
    """일자별 증감 목록 → 적수 (Σ 일별잔액).

    deltas: [(거래일, 증감액)] — 같은 날 여러 건 허용
    opening: 사업연도 개시일 전일 잔액 (기초잔액)
    floor_zero: 음수 잔액 구간은 0으로 처리 (가지급금 등 자산 적수)
    거래일이 사업연도 밖이면 개시일 이전分은 opening에 합산, 종료일 이후는 무시.
    """
    if fy_end < fy_start:
        return 0
    bal = opening
    events: dict[date, int] = {}
    for d, amt in deltas:
        if d < fy_start:
            bal += amt
        elif d <= fy_end:
            events[d] = events.get(d, 0) + amt

    total = 0
    cur = fy_start
    for d in sorted(events):
        days = (d - cur).days
        if days > 0:
            total += max(0, bal) if floor_zero else bal
            total += (max(0, bal) if floor_zero else bal) * (days - 1)
        bal += events[d]
        cur = d
    # 마지막 이벤트일부터 종료일까지 (이벤트일 당일 포함)
    days = (fy_end - cur).days + 1
    total += (max(0, bal) if floor_zero else bal) * days
    return total


def lines_to_deltas(
    lines: list[JournalLine], debit_positive: bool = True,
) -> list[tuple[date, int]]:
    """분개 라인 → 일자별 증감. 자산(가지급금 등)은 차변+, 부채(차입금·보증금)는 대변+."""
    out: list[tuple[date, int]] = []
    for ln in lines:
        amt = (ln.debit - ln.credit) if debit_positive else (ln.credit - ln.debit)
        if amt:
            out.append((ln.date, amt))
    return out


def account_jeoksu(
    journals: list[JournalLine],
    name_keywords: tuple[str, ...],
    fy_start: date,
    fy_end: date,
    opening: int = 0,
    debit_positive: bool = False,
) -> int:
    """계정명 키워드로 분개를 모아 적수 계산 (차입금·임대보증금 등 — 대변+ 기본)."""
    lines = [
        ln for ln in journals
        if any(k in ln.account_name.replace(" ", "") for k in name_keywords)
    ]
    return jeoksu_from_deltas(
        lines_to_deltas(lines, debit_positive=debit_positive),
        fy_start, fy_end, opening=opening,
    )


def fy_days(fy_start: date, fy_end: date) -> int:
    return max(1, (fy_end - fy_start).days + 1)
