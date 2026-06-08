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

    # ── 비과세소득·소득공제 (법§13①2호·3호) — 과세표준에서 차감 ──
    st.markdown(section_title(
        "비과세소득·소득공제 (법§13①)",
        "과세표준 = 각사업연도소득 − 이월결손금 − 비과세소득 − 소득공제. "
        "분개로 자동 파악되지 않아 직접 입력합니다. 해당 없으면 0.",
    ), unsafe_allow_html=True)
    _ntc1, _ntc2 = st.columns(2, gap="medium")
    proj.manual_input.non_taxable_income = int(_ntc1.number_input(
        "비과세소득 (원)", min_value=0,
        value=int(proj.manual_input.non_taxable_income or 0), step=1_000_000,
        help="법§51(공익신탁 신탁재산 소득) 등 — 항목별 근거 법령을 검토조서에 기록. "
             "당기 미공제분은 차기 이월 불가(법§13②, 한도 초과 시 소멸).",
    ))
    proj.manual_input.income_deduction = int(_ntc2.number_input(
        "소득공제 (원)", min_value=0,
        value=int(proj.manual_input.income_deduction or 0), step=1_000_000,
        help="법§13①3호 — 이 법·다른 법률에 따른 소득공제(예: 유동화전문회사 배당 소득공제 "
             "조특§104의31 등). 당기 미공제분은 소멸(법§13②).",
    ))

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

    # ── 전기 유보 당기 추인 → 소득금액 반영 (회계사 명시 입력) ──
    st.markdown(section_title(
        "전기 유보 당기 추인 (소득금액 반영)",
        "전기 유보·△유보가 당기에 추인(환입)되어 소득금액에 영향을 주는 금액을 입력합니다. "
        "유보 추인 → 손금산입(△유보), △유보 추인 → 익금산입(유보).",
    ), unsafe_allow_html=True)
    st.caption(
        "⚠ **감가상각 부인누계 추인**(엔진 자동 반영)과 **기부금 이월**(별도 처리)은 "
        "여기에 넣지 마세요 — 이중계상됩니다. **대손충당금 총액법** 전기 한도초과 환입"
        "(법§34③, 손금산입)은 여기에 포함합니다. 위 자본금과적립금조정명세서(을)의 "
        "'당기감소(추인)' 합계와 대조하여 입력하세요."
    )
    _rrc1, _rrc2 = st.columns(2, gap="medium")
    proj.manual_input.prior_reserve_reversal_deduct = int(_rrc1.number_input(
        "전기 유보 추인 — 손금산입(△유보) (원)", min_value=0,
        value=int(proj.manual_input.prior_reserve_reversal_deduct or 0), step=1_000_000,
        help="전기에 손금불산입(유보)된 금액의 당기 추인 — 손금산입. 감가상각 제외.",
    ))
    proj.manual_input.prior_reserve_reversal_add = int(_rrc2.number_input(
        "전기 △유보 추인 — 익금산입(유보) (원)", min_value=0,
        value=int(proj.manual_input.prior_reserve_reversal_add or 0), step=1_000_000,
        help="전기에 익금불산입(△유보)된 금액의 당기 추인 — 익금산입.",
    ))

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

    st.markdown(section_title(
        "수입금액 보정 (기업업무추진비 한도)",
        "기업업무추진비 한도의 분모인 수입금액(영§42① 기업회계기준 매출액)을 보정합니다. "
        "0이면 매출계정 자동집계를 사용합니다.",
    ), unsafe_allow_html=True)
    proj.manual_input.revenue_manual = int(st.number_input(
        "수입금액 보정값 (원) — 0이면 자동집계 사용", min_value=0,
        value=int(proj.manual_input.revenue_manual or 0), step=10_000_000,
        help="파서가 매출 계정을 누락·오분류한 경우에만 보정하세요(영§42① 기업회계기준 매출액 기준). "
             "임의 가산 금지 — 보정 시 출처를 검토조서에 기록.",
    ))

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

        proj.manual_input.bad_debt_method = st.radio(
            "대손충당금 처리방식",
            ["총액법", "보충법"],
            index=(1 if proj.manual_input.bad_debt_method == "보충법" else 0),
            horizontal=True,
            help="유보 잔액표(을)의 증감 표기 기준 — 총액법(법§34③ 기본): 전기 충당금 전액 환입 후 "
                 "당기 재설정 / 보충법: 전기 유보 이월·증감분만 조정(추인은 검토). 기말 유보 잔액은 동일.",
        )

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

