"""전년 대비 증감분석 — 손익계산서 당기/전기 비교 (규칙 기반, LLM 불필요).

실무 원칙: 회계사는 당기 금액만 보지 않는다 — 전년 대비 급증·비율 변화가
검토 우선순위를 정한다. 보고서형 손익계산서의 '전기' 열에서 자동 추출.
"""
from __future__ import annotations

import pandas as pd

# 세무조정 관점 주시 계정 (급증 시 경고)
_WATCH_KW = (
    "기업업무추진비", "접대비", "기부금", "지급수수료", "차량유지비",
    "복리후생비", "이자비용", "감가상각비", "세금과공과", "잡손실", "수선비",
)

# 급증 판정 기준: 증감률 30% 이상 그리고 증가액 1천만원 이상
_SURGE_RATE = 0.30
_SURGE_ABS = 10_000_000


def _norm_name(s: str) -> str:
    return str(s).replace(" ", "").strip()


def yoy_table(income_df, prev_income_df=None) -> "pd.DataFrame | None":
    """손익계산서 계정별 당기/전기/증감/증감률 표.

    전기 값 출처 (우선순위):
      1. 별도 업로드한 전기 손익계산서 (prev_income_df의 '당기금액' = 전기 값)
      2. 당기 손익계산서에 포함된 '전기' 열 (당기/전기 2단 양식)
    둘 다 없으면 None.
    """
    if income_df is None or income_df.empty or "당기금액" not in income_df.columns:
        return None
    df = income_df.copy()
    df = df[~df.get("합계행", pd.Series(False, index=df.index)).fillna(False)] \
        if "합계행" in df.columns else df

    # 전기 값 매핑 구성
    prev_map: dict[str, int] = {}
    prev_src = ""
    if (prev_income_df is not None and not prev_income_df.empty
            and "당기금액" in prev_income_df.columns):
        for _, r in prev_income_df.iterrows():
            nm = _norm_name(r.get("계정명", ""))
            if nm:
                prev_map[nm] = prev_map.get(nm, 0) + int(r["당기금액"] or 0)
        prev_src = "전기 손익계산서 업로드"
    if not prev_map and "전기금액" in df.columns and (df["전기금액"] != 0).any():
        for _, r in df.iterrows():
            nm = _norm_name(r.get("계정명", ""))
            if nm:
                prev_map[nm] = prev_map.get(nm, 0) + int(r["전기금액"] or 0)
        prev_src = "당기 손익계산서의 전기 열"
    if not prev_map:
        return None

    rows = []
    seen = set()
    for _, r in df.iterrows():
        nm = _norm_name(r.get("계정명", ""))
        if not nm or nm in seen:
            continue
        seen.add(nm)
        cur = int(r["당기금액"] or 0)
        prev = prev_map.get(nm, 0)
        if cur == 0 and prev == 0:
            continue
        rows.append({"계정명": str(r["계정명"]).strip(), "당기": cur, "전기": prev})
    # 전기에만 있고 당기에 사라진 계정 (소멸 항목도 분석 대상)
    for nm, prev in prev_map.items():
        if nm not in seen and prev != 0:
            rows.append({"계정명": nm, "당기": 0, "전기": prev})

    if not rows:
        return None
    out = pd.DataFrame(rows)
    out["증감"] = out["당기"] - out["전기"]
    out["증감률(%)"] = out.apply(
        lambda r: round(r["증감"] / abs(r["전기"]) * 100, 1) if r["전기"] else None,
        axis=1,
    )
    out.attrs["prev_source"] = prev_src
    # 손익계산서 양식(파싱) 순서를 그대로 유지 — 증감액 크기순으로 재정렬하지 않는다.
    # (전기에만 있던 소멸 계정은 당기 계정 뒤에 이어진다.)
    return out.reset_index(drop=True)


def bs_opening_check(cur_bs, prev_bs, tolerance: int = 1000) -> "pd.DataFrame | None":
    """당기 B/S 기초잔액 ↔ 전기 B/S 기말잔액 대사 (분석적 검토 기본 절차).

    불일치 계정만 반환 — 전기 재무제표 미업로드 시 None.
    불일치는 ① 파싱 오류 ② 전기 수정 ③ 계정 재분류 신호로, 적수 계산의
    기초잔액 신뢰성과도 직결된다.
    """
    if cur_bs is None or prev_bs is None or cur_bs.empty or prev_bs.empty:
        return None
    if "기초잔액" not in cur_bs.columns or "기말잔액" not in prev_bs.columns:
        return None

    def _sum_by_name(df, col):
        out: dict[str, int] = {}
        for _, r in df.iterrows():
            if bool(r.get("합계행", False)):
                continue
            nm = _norm_name(r.get("계정명", ""))
            if nm:
                out[nm] = out.get(nm, 0) + int(r[col] or 0)
        return out

    cur_open = _sum_by_name(cur_bs, "기초잔액")
    prev_close = _sum_by_name(prev_bs, "기말잔액")
    rows = []
    for nm in sorted(set(cur_open) | set(prev_close)):
        a, b = cur_open.get(nm, 0), prev_close.get(nm, 0)
        if abs(a - b) > tolerance and (a or b):
            rows.append({
                "계정명": nm,
                "당기 기초잔액": a,
                "전기 기말잔액": b,
                "차이": a - b,
            })
    if not rows:
        return pd.DataFrame(columns=["계정명", "당기 기초잔액", "전기 기말잔액", "차이"])
    return pd.DataFrame(rows).sort_values("차이", key=lambda s: s.abs(),
                                          ascending=False).reset_index(drop=True)


def yoy_flags(table: "pd.DataFrame", revenue_cur: int = 0, revenue_prev: int = 0) -> list[str]:
    """급증·비율 변화 경고 목록 (검토 우선순위 제안)."""
    flags: list[str] = []
    if table is None or table.empty:
        return flags
    for _, r in table.iterrows():
        nm = str(r["계정명"]).replace(" ", "")
        if not any(k in nm for k in _WATCH_KW):
            continue
        cur, prev, diff = int(r["당기"]), int(r["전기"]), int(r["증감"])
        if prev > 0 and diff >= _SURGE_ABS and diff / prev >= _SURGE_RATE:
            flags.append(
                f"⚠ {r['계정명']} 급증 — 전기 {prev:,} → 당기 {cur:,} "
                f"(+{diff / prev:.0%}). 성격 변동·세무조정 누락 여부 검토"
            )
        elif prev == 0 and cur >= _SURGE_ABS:
            flags.append(f"⚠ {r['계정명']} 신규 발생 {cur:,}원 — 전기 없음, 성격 확인 필요")
    # 매출 대비 비율 변화 (수익성 외 — 접대비·복리후생 비율)
    if revenue_cur and revenue_prev:
        for kw in ("기업업무추진비", "접대비", "복리후생비"):
            row = table[table["계정명"].str.replace(" ", "").str.contains(kw, regex=False)]
            if row.empty:
                continue
            cur_r = int(row["당기"].iloc[0]) / revenue_cur
            prev_r = int(row["전기"].iloc[0]) / revenue_prev
            if prev_r > 0 and cur_r > prev_r * 1.5 and cur_r - prev_r > 0.001:
                flags.append(
                    f"⚠ {row['계정명'].iloc[0]} 매출 대비 비율 상승 — "
                    f"전기 {prev_r:.2%} → 당기 {cur_r:.2%}"
                )
    return flags
