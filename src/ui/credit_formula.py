"""세액공제·감면 산식 계산기 UI (수기입력 3단계 — manual_input에서 분리).

항목명에 조특§7·§24·§10·§29의7을 적으면 해당 산식 입력칸을 펼쳐 회계사가 인자(투자액·율·
산출세액 등)만 입력하면 규칙엔진(tax_credit_catalog.calc_*)이 공제·감면액을 산출한다.
ADR-002 — 산식 결과는 규칙엔진, 적용·확정은 회계사.
"""
from __future__ import annotations

import streamlit as st

from src.rules.tax_credit_catalog import (
    calc_sme_special_reduction, calc_rnd_credit, calc_integrated_investment_credit,
)


def credit_formula_type(name: str) -> str | None:
    """세액공제·감면 항목명 → 산식 유형 (산식 계산기 연결용). 미매칭 시 None(수기 금액)."""
    n = (name or "").replace(" ", "")
    if "중소기업특별" in n or ("중소" in n and "감면" in n) or "조특§7" in n or "조특7" in n:
        return "조특7"
    if "통합투자" in n or "조특§24" in n or "조특24" in n:
        return "조특24"
    if "연구" in n or "인력개발" in n or "조특§10" in n or "조특10" in n or "R&D" in n.upper():
        return "조특10"
    if "고용증대" in n or "조특§29의7" in n or "조특29의7" in n:
        return "조특29의7"
    return None


def render_credit_formula(ftype: str, prev: dict, company, i: int) -> tuple[int, dict]:
    """세액공제·감면 산식 입력칸 + 요건 자동검토 표시 → (산출 공제·감면액, 산식 파라미터 dict).

    회계사가 공제액을 직접 입력하는 대신, 산식의 인자(투자액·율·산출세액 등)를 입력하면
    규칙엔진(calc_*)이 금액을 산출한다 (ADR-002 — 산식 결과는 규칙엔진, 확정은 회계사).
    """
    f = dict(prev or {})
    is_sme = bool(getattr(company, "is_sme", False))
    _sme_txt = "충족 ✓" if is_sme else "미충족/미확정 ✗ (1단계 중소기업 판정 확인)"
    amount = 0
    if ftype == "조특7":
        st.caption("**중소기업특별세액감면(조특§7)** — 감면세액 = 사업소득분 산출세액 × 감면율 (한도 적용)")
        st.caption(f"요건 자동검토 — 중소기업: **{_sme_txt}** · 감면업종·소/중기업·지역·고용감소 차감은 회계사 확인 (최저한세 적용대상)")
        c1, c2, c3 = st.columns(3)
        f["business_income_tax"] = int(c1.number_input("사업소득분 산출세액(원)", min_value=0,
            value=int(f.get("business_income_tax", 0) or 0), step=100_000, key=f"tcf7b_{i}"))
        f["reduction_rate"] = float(c2.number_input("감면율(%)", min_value=0.0, max_value=100.0,
            value=float(f.get("reduction_rate", 0) or 0), step=5.0, key=f"tcf7r_{i}",
            help="조특§7①2호 — 소기업 도소매·의료 10·수도권외 30, 중기업 수도권외 15 등(회계사 확인)"))
        f["cap"] = int(c3.number_input("감면 한도(원)", min_value=0,
            value=int(f.get("cap", 100_000_000) or 100_000_000), step=10_000_000, key=f"tcf7c_{i}",
            help="기본 1억(조특§7③). 상시근로자 감소 시 1억 − 감소인원×500만"))
        amount = calc_sme_special_reduction(
            business_income_tax=f["business_income_tax"],
            reduction_rate=f["reduction_rate"] / 100, cap=f["cap"])
    elif ftype == "조특24":
        st.caption("**통합투자세액공제(조특§24)** — 기본(투자액×기본율) + 추가((투자액−직전3년평균)×추가율, 기본공제 2배 한도)")
        st.caption("요건 자동검토 — 공제대상자산 해당성(조특령§21)·신성장/국가전략 분류는 회계사 확인 (최저한세·농특세 대상)")
        c1, c2, c3, c4 = st.columns(4)
        f["investment"] = int(c1.number_input("당기 투자액(원)", min_value=0,
            value=int(f.get("investment", 0) or 0), step=1_000_000, key=f"tcf24i_{i}"))
        f["base_rate"] = float(c2.number_input("기본공제율(%)", min_value=0.0, max_value=50.0,
            value=float(f.get("base_rate", 0) or 0), step=1.0, key=f"tcf24b_{i}",
            help="조특령§21 — 중소 10·중견 5·대기업 1, 2024 임시공제 중소 12 등(율은 회계사 확인)"))
        f["prior_3yr_avg"] = int(c3.number_input("직전 3년 평균 투자액(원)", min_value=0,
            value=int(f.get("prior_3yr_avg", 0) or 0), step=1_000_000, key=f"tcf24p_{i}"))
        f["extra_rate"] = float(c4.number_input("추가공제율(%)", min_value=0.0, max_value=50.0,
            value=float(f.get("extra_rate", 10) or 10), step=1.0, key=f"tcf24e_{i}",
            help="직전 3년 초과분, 보통 10%(조특§24①2호나목)"))
        amount = calc_integrated_investment_credit(
            investment=f["investment"], base_rate=f["base_rate"] / 100,
            prior_3yr_avg=f["prior_3yr_avg"], extra_rate=f["extra_rate"] / 100)
    elif ftype == "조특10":
        st.caption("**연구·인력개발비 세액공제(조특§10)** — 당기분 또는 증가분 중 큰 값")
        st.caption(f"요건 자동검토 — 중소기업: **{_sme_txt}** "
                   f"{'→ 최저한세 배제(조특§132①3호 괄호 중소기업 제외)' if is_sme else '→ 일반기업 당기분은 최저한세 적용'}. "
                   "R&D비 인정범위(조특령§9 별표6)는 회계사 확인")
        c1, c2, c3, c4 = st.columns(4)
        f["current_expense"] = int(c1.number_input("당기 R&D비(원)", min_value=0,
            value=int(f.get("current_expense", 0) or 0), step=1_000_000, key=f"tcf10c_{i}"))
        f["rate"] = float(c2.number_input("당기분 공제율(%)", min_value=0.0, max_value=50.0,
            value=float(f.get("rate", 0) or 0), step=1.0, key=f"tcf10r_{i}", help="중소 25%(조특령§9)"))
        f["increase_expense"] = int(c3.number_input("증가분(당기−직전기, 원)", min_value=0,
            value=int(f.get("increase_expense", 0) or 0), step=1_000_000, key=f"tcf10ie_{i}"))
        f["increase_rate"] = float(c4.number_input("증가분 공제율(%)", min_value=0.0, max_value=50.0,
            value=float(f.get("increase_rate", 0) or 0), step=1.0, key=f"tcf10ir_{i}",
            help="중소 50%(조특§10①3호가목)"))
        amount = calc_rnd_credit(
            current_expense=f["current_expense"], rate=f["rate"] / 100,
            increase_expense=f["increase_expense"], increase_rate=f["increase_rate"] / 100)
    elif ftype == "조특29의7":
        st.caption("**고용증대 세액공제(조특§29의7)** — 청년등 증가×단가 + 청년등외 증가×단가 "
                   "(2024년 적용 마지막, 2025~ 통합고용 §29의8)")
        c1, c2, c3, c4 = st.columns(4)
        f["youth_n"] = int(c1.number_input("청년등 증가 인원", min_value=0,
            value=int(f.get("youth_n", 0) or 0), step=1, key=f"tcf29yn_{i}"))
        f["youth_unit"] = int(c2.number_input("청년등 1인 단가(원)", min_value=0,
            value=int(f.get("youth_unit", 11_000_000) or 11_000_000), step=1_000_000, key=f"tcf29yu_{i}",
            help="중소 1,100만(수도권밖 1,200)·중견 800·대기업 400 (조특§29의7①1호)"))
        f["other_n"] = int(c3.number_input("청년등외 증가 인원", min_value=0,
            value=int(f.get("other_n", 0) or 0), step=1, key=f"tcf29on_{i}"))
        f["other_unit"] = int(c4.number_input("청년등외 1인 단가(원)", min_value=0,
            value=int(f.get("other_unit", 7_000_000) or 7_000_000), step=1_000_000, key=f"tcf29ou_{i}",
            help="중소 수도권 700(수도권밖 770)·중견 450·대기업 0 (2호)"))
        amount = f["youth_n"] * f["youth_unit"] + f["other_n"] * f["other_unit"]
        st.caption("⚠ 2년 내 상시근로자 감소 시 공제 중단·추징(§29의7②) — 사후관리 회계사 확인")
    st.metric(f"산출 공제·감면액 #{i + 1}", f"{amount:,}원")
    return amount, f
