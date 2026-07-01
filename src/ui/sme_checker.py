"""중소기업 판정 워크시트 UI 컴포넌트 (Streamlit)."""
from __future__ import annotations
import streamlit as st


# 업종별 매출액 기준 (원) — 중소기업기본법 시행령 별표1
SME_REVENUE_LIMIT: dict[str, int] = {
    "제조업":              150_000_000_000,   # 1,500억
    "건설업":              100_000_000_000,   # 1,000억
    "도소매업":            100_000_000_000,   # 1,000억
    "서비스업(일반)":       60_000_000_000,   #   600억
    "전문과학기술서비스업":  60_000_000_000,   #   600억
    "정보통신업":           80_000_000_000,   #   800억
    "숙박음식업":           40_000_000_000,   #   400억
    "기타":                60_000_000_000,   #   600억
}

MAX_ASSET = 500_000_000_000  # 자산총액 5,000억원


def ksic_to_industry(induty_code: str) -> str:
    """DART induty_code(KSIC 5자리) → SME 업종 분류."""
    try:
        n = int(str(induty_code).strip()[:2])
    except (ValueError, TypeError):
        return "기타"
    if 10 <= n <= 33:
        return "제조업"
    if n in (41, 42):
        return "건설업"
    if n in (45, 46, 47):
        return "도소매업"
    if n in (55, 56):
        return "숙박음식업"
    if 58 <= n <= 63:
        return "정보통신업"
    if 70 <= n <= 73:
        return "전문과학기술서비스업"
    if n in (64, 65, 66):
        return "기타"   # 금융·보험
    return "서비스업(일반)"


def _dart_badge(year: str | None = None) -> str:
    label = f"DART {year}년 공시" if year else "DART 자동입력"
    return (
        '<span style="font-size:11px;background:#e8f0fe;'
        'color:#1a73e8;border-radius:5px;padding:1px 6px;margin-left:6px;'
        f'font-weight:600;">{label}</span>'
    )


def render_sme_checker(prefill: dict | None = None) -> dict:
    """
    중소기업 판정 6개 항목 입력 폼.

    prefill 키:
      industry       str   DART 업종 분류 (ksic_to_industry 결과)
      revenue        int   DART 매출액 (원)
      total_assets   int   DART 자산총계 (원)
      shareholders   list  [{"nm","relate","ownership_pct"}, ...]
      has_controlling_entity  bool  지배기업 존재 여부 추정

    반환: {"is_sme": bool, "notes": str, "inputs": dict}
    """
    pf = prefill or {}
    has_prefill = bool(pf)

    st.subheader("중소기업 판정 워크시트")
    if has_prefill:
        st.markdown(
            '<p style="font-size:13px;color:#1a73e8;margin-top:-0.5rem;">'
            '아래 항목은 DART 공시 데이터로 자동입력되었습니다. '
            '확인 후 필요 시 수정하세요.</p>',
            unsafe_allow_html=True,
        )
    else:
        st.caption(
            "DART corp_cls(유가/코스닥 등)는 세법상 중소기업 판정값이 아닙니다. "
            "아래 6개 항목을 직접 입력·확인해 주세요."
        )

    # ── 1. 업종 ───────────────────────────────────────────────────────────────
    industry_options = list(SME_REVENUE_LIMIT.keys())
    pf_industry = pf.get("industry", "")
    industry_idx = (
        industry_options.index(pf_industry)
        if pf_industry in industry_options else 0
    )

    lbl1 = "1. 업종 (중분류)"
    if pf_industry:
        st.markdown(f"{lbl1} {_dart_badge()}", unsafe_allow_html=True)
        industry = st.selectbox(
            lbl1, options=industry_options,
            index=industry_idx, label_visibility="collapsed",
            help="DART induty_code(KSIC)에서 자동 분류됨. 필요 시 수정하세요.",
        )
    else:
        industry = st.selectbox(
            lbl1, options=industry_options,
            help="매출액 기준이 업종별로 다릅니다.",
        )

    # ── 2. 매출액 ─────────────────────────────────────────────────────────────
    pf_revenue = pf.get("revenue") or 0
    lbl2 = "2. 당기 매출액 (원)"
    if pf.get("revenue") is not None:
        st.markdown(f"{lbl2} {_dart_badge(pf.get('fin_year'))}", unsafe_allow_html=True)
        revenue = st.number_input(
            lbl2, min_value=0, value=int(pf_revenue), step=1_000_000,
            label_visibility="collapsed",
            help="관계기업 합산 매출액으로 판정 필요 시 관계기업 분 포함",
        )
    else:
        revenue = st.number_input(
            lbl2, min_value=0, step=1_000_000,
            help="관계기업 합산 매출액으로 판정 필요 시 관계기업 분 포함",
        )

    # ── 3. 자산총액 ───────────────────────────────────────────────────────────
    pf_assets = pf.get("total_assets") or 0
    lbl3 = "3. 자산총액 (원)"
    if pf.get("total_assets") is not None:
        st.markdown(f"{lbl3} {_dart_badge(pf.get('fin_year'))}", unsafe_allow_html=True)
        total_asset = st.number_input(
            lbl3, min_value=0, value=int(pf_assets), step=1_000_000,
            label_visibility="collapsed",
        )
    else:
        total_asset = st.number_input(lbl3, min_value=0, step=1_000_000)

    # ── 4. 지배·관계기업 여부 ─────────────────────────────────────────────────
    pf_ctrl = pf.get("has_controlling_entity", False)
    ctrl_default = 1 if pf_ctrl else 0    # 0=없음, 1=있음
    lbl4 = "4. 지배·관계기업 여부"
    ctrl_options = ["없음", "있음 — 관계기업 합산 매출액으로 판정"]

    if has_prefill:
        st.markdown(f"{lbl4} {_dart_badge()}", unsafe_allow_html=True)
        has_related_entity = st.radio(
            lbl4, options=ctrl_options, index=ctrl_default,
            label_visibility="collapsed",
        )
    else:
        has_related_entity = st.radio(lbl4, options=ctrl_options)

    # ── 5. 독립성 기준 ────────────────────────────────────────────────────────
    pf_indep = pf.get("is_independent", True)   # True=충족 추정
    indep_default = 0 if pf_indep else 1
    lbl5 = "5. 독립성 기준 충족"
    indep_options = [
        "충족 (대기업 계열사 아님)",
        "미충족 (대기업 계열사 — 중소기업 제외)",
    ]
    if has_prefill:
        st.markdown(f"{lbl5} {_dart_badge()}", unsafe_allow_html=True)
        is_independent = st.radio(
            lbl5, options=indep_options, index=indep_default,
            label_visibility="collapsed",
        )
    else:
        is_independent = st.radio(lbl5, options=indep_options)

    # ── 6. 유예기간 ───────────────────────────────────────────────────────────
    grace_period = st.checkbox("6. 중소기업 유예기간 해당 (졸업 후 3년 이내)")
    grace_year = None
    if grace_period:
        grace_year = st.number_input(
            "유예 진입 연도", min_value=2010, max_value=2030, value=2023, step=1,
        )

    # ── 주주 현황 표시 ────────────────────────────────────────────────────────
    shareholders = pf.get("shareholders", [])
    if shareholders:
        with st.expander(f"주주 현황 (DART, {len(shareholders)}명)", expanded=False):
            import pandas as pd
            rows = [
                {
                    "성명/법인명": s["nm"],
                    "관계":       s["relate"],
                    "지분율(%)":  s["ownership_pct"],
                }
                for s in shareholders
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption(
            "※ DART 주주현황 기준. 특수관계인 주석과 다를 수 있으므로 최종 확인 필요."
        )

    # ── 판정 ─────────────────────────────────────────────────────────────────
    revenue_limit     = SME_REVENUE_LIMIT.get(industry, SME_REVENUE_LIMIT["기타"])
    failed_indep      = "미충족" in is_independent
    exceeds_revenue   = revenue > revenue_limit
    exceeds_asset     = total_asset > MAX_ASSET

    if failed_indep:
        is_sme, reason = False, "독립성 기준 미충족"
    elif exceeds_asset:
        is_sme, reason = False, f"자산총액 {total_asset:,}원 > 5,000억원"
    elif exceeds_revenue:
        is_sme, reason = False, f"매출액 {revenue:,}원 > {revenue_limit:,}원 ({industry})"
    elif grace_period:
        is_sme, reason = True, f"유예기간 적용 ({grace_year}년 진입, 3년 이내)"
    else:
        is_sme, reason = True, "중소기업 요건 충족"

    color = "green" if is_sme else "red"
    st.markdown(
        f"**판정 결과**: :{color}[{'중소기업' if is_sme else '일반법인'}]  \n{reason}"
    )
    st.warning("⚠️ 이 판정은 참고용입니다. 회계사가 최종 확인 후 저장하세요.")

    return {
        "is_sme": is_sme,
        "notes": reason,
        "inputs": {
            "industry": industry,
            "revenue": revenue,
            "total_asset": total_asset,
            "has_related_entity": has_related_entity,
            "is_independent": is_independent,
            "grace_period": grace_period,
            "grace_year": grace_year,
        },
    }
