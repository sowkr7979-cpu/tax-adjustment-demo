"""3단계 — 수기 입력 (이월결손금·유보·세무조정 필요자료)."""
from __future__ import annotations
from datetime import date

import streamlit as st

from src.ui.manual_input import (
    render_carryforward_loss, render_prior_reserves, render_adjustment_data,
    validate_manual_input,
)
from src.ui.styles import page_header, section_title
from src.views.common import _parse_stored_date


def render(proj) -> None:
    st.markdown(page_header(
        "수기 입력 항목",
        "API나 파일로 자동 파악되지 않는 항목을 직접 입력합니다.",
    ), unsafe_allow_html=True)

    fy_end_val = _parse_stored_date(
        proj.company.fiscal_year_end, date.today()
    )

    # ── 전년도 세무조정 자료 불러오기 — 실무의 시작점 ──────────────────────────
    st.markdown(section_title(
        "전년도 세무조정 자료 불러오기 (.taxproj)",
        "전년도 프로젝트 파일이 있으면 전기 유보·이월결손금·감가상각 부인누계·"
        "판단자료(임원 명단, 평가방법 신고, 승용차 분류 등)를 당기로 승계합니다. "
        "파일이 없으면 아래 항목들을 전년 세무조정계산서를 보고 직접 입력하세요.",
    ), unsafe_allow_html=True)

    _prev_file = st.file_uploader(
        "전년도 .taxproj 파일", type=["taxproj", "json"], key="prev_taxproj",
    )
    if _prev_file is not None and st.button("전년도 자료 승계 실행"):
        import json
        import tempfile
        import os
        from src.project.taxproj import TaxProject
        with tempfile.NamedTemporaryFile(suffix=".taxproj", delete=False) as tmp:
            tmp.write(_prev_file.read())
            _tmp_path = tmp.name
        try:
            prev_proj = TaxProject.load(_tmp_path)
            notes = proj.carry_forward_from(prev_proj)
            st.session_state["prev_proj_loaded"] = True
            st.success(f"전년도 자료 승계 완료 — {prev_proj.company.name or '(회사명 없음)'}")
            for n in notes:
                st.markdown(f"- {n}")
            st.warning(
                "승계된 값은 **초안**입니다 — 이월결손금 당기 공제분 차감, 유보 추인 여부, "
                "중소기업·특정법인 재판정을 반드시 확인하세요."
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            st.error(f"전년도 파일을 읽지 못했습니다: {e} — 아래에서 직접 입력하세요.")
        finally:
            try:
                os.unlink(_tmp_path)
            except OSError:
                pass
    elif not st.session_state.get("prev_proj_loaded"):
        st.caption(
            "전년도 파일이 없어도 됩니다 — 전년 세무조정계산서(자본금과적립금조정명세서 갑·을)를 "
            "보고 아래 이월결손금·전기 유보·부인누계를 직접 입력하면 동일하게 계산됩니다."
        )

    st.divider()

    st.markdown(section_title(
        "이월결손금 명세",
        "발생 연도별 금액을 입력합니다. 2009년 전 발생분은 5년, 이후는 15년 공제기한.",
    ), unsafe_allow_html=True)
    proj.manual_input.carryforward_losses = render_carryforward_loss(
        existing=proj.manual_input.carryforward_losses,
    )

    st.divider()

    st.markdown(section_title(
        "전기 세무조정 유보 내역",
        "전기에서 이월된 유보·△유보 항목을 입력합니다.",
    ), unsafe_allow_html=True)
    proj.manual_input.prior_reserves = render_prior_reserves(
        existing=proj.manual_input.prior_reserves,
    )

    # 감가상각 부인누계 — 전기 유보의 일부 (자본금과적립금조정명세서(을) 항목)
    # 자산별 부인누계는 고정자산대장에서 자동 사용되므로, 이 입력은 합계 대사 검증용
    _fa_denial_sum = sum(
        a.denied_depr_start for a in (st.session_state.loader.fixed_assets or [])
    )
    new_depr_denial = st.number_input(
        "감가상각 부인누계액 합계 (원) — 전기 자본금과적립금조정명세서(을) 기준",
        min_value=0,
        value=proj.manual_input.depreciation_denial_cumulative,
        step=1_000_000,
        help="계산에는 고정자산대장의 자산별 '전기말부인누계'가 사용됩니다. "
             "이 값은 전기 신고서 합계와 대장 합계를 대사(검증)하는 용도입니다.",
    )
    proj.manual_input.depreciation_denial_cumulative = new_depr_denial
    if _fa_denial_sum or new_depr_denial:
        if new_depr_denial and _fa_denial_sum != new_depr_denial:
            st.warning(
                f"⚠ 대사 불일치 — 고정자산대장 자산별 부인누계 합계 {_fa_denial_sum:,}원 ≠ "
                f"입력값 {new_depr_denial:,}원. 전기 신고서(을지)와 대장을 확인하세요."
            )
        elif new_depr_denial:
            st.caption(f"✓ 대사 일치 — 고정자산대장 부인누계 합계 {_fa_denial_sum:,}원")
        else:
            st.caption(f"고정자산대장 자산별 부인누계 합계: {_fa_denial_sum:,}원 (전기 신고서와 대사 권장)")

    st.divider()

    st.markdown(section_title(
        "세무조정 필요자료",
        "전수 검토 체크리스트의 '검토필요' 항목 — 자료가 구비된 항목을 입력하면 "
        "계산·검토 단계에서 법령 산식으로 자동 반영됩니다.",
    ), unsafe_allow_html=True)
    render_adjustment_data(
        proj.manual_input,
        st.session_state.loader.journals,
        loader=st.session_state.loader,
        related_parties=proj.manual_input.related_parties,
    )

    st.divider()

    st.markdown(section_title("충당금·채권 정보"), unsafe_allow_html=True)
    col1, col2 = st.columns(2, gap="medium")
    with col1:
        new_pension = st.number_input(
            "퇴직연금(DB형) 운용자산 (원)",
            min_value=0,
            value=proj.manual_input.pension_db_asset,
            step=1_000_000,
            help="기말 사외 예치금 잔액 — 영§44의2④ 손금산입 한도(예치금 기준)",
        )
        proj.manual_input.pension_db_asset = new_pension

        new_estimate = st.number_input(
            "퇴직급여추계액 (원)",
            min_value=0,
            value=proj.manual_input.retirement_estimate,
            step=1_000_000,
            help="일시퇴직기준·보험수리기준 중 큰 금액 — DB형 퇴직연금 손금산입 한도(추계액 기준, 영§44의2④1호·1호의2)",
        )
        proj.manual_input.retirement_estimate = new_estimate

        new_prior_pension = st.number_input(
            "직전까지 손금산입한 퇴직연금 부담금 누계 (원)",
            min_value=0,
            value=proj.manual_input.prior_pension_deducted,
            step=1_000_000,
            help="직전 사업연도종료일까지 손금에 산입한 부담금 누계 — 영§44의2④2호",
        )
        proj.manual_input.prior_pension_deducted = new_prior_pension

    with col2:
        new_recv = st.number_input(
            "채권잔액 합계 (원)",
            min_value=0,
            value=proj.manual_input.receivable_balance,
            step=1_000_000,
        )
        proj.manual_input.receivable_balance = new_recv

        new_bad = st.number_input(
            "직전 3년 대손실적률",
            min_value=0.0,
            max_value=1.0,
            value=proj.manual_input.actual_bad_debt_rate,
            step=0.001,
            format="%.4f",
        )
        proj.manual_input.actual_bad_debt_rate = new_bad

    st.divider()

    col_v, _ = st.columns([1, 3])
    with col_v:
        if st.button("입력 검증", use_container_width=True):
            errs = validate_manual_input(proj.manual_input, fy_end_val)
            if errs:
                for e in errs:
                    st.warning(e)
            else:
                st.success("모든 항목 검증 통과")

