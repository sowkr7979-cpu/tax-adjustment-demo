"""6단계 — 출력 (감사추적 Excel·.taxproj·추천 서식)."""
from __future__ import annotations
import os
import tempfile
from datetime import date

import streamlit as st

from src.forms.registry import recommend_forms
from src.forms.audit_trail import generate_audit_trail
from src.llm.ollama_client import OllamaClient
from src.ui.styles import page_header, section_title, info_card
from src.utils.safe_export import safe_filename
from src.views.common import _parse_stored_date


def render(proj) -> None:
    st.markdown(page_header(
        "출력 파일 생성",
        "감사추적 Excel과 프로젝트 파일을 생성·다운로드합니다.",
    ), unsafe_allow_html=True)

    if st.session_state.tax_result is None:
        st.markdown(info_card(
            "<b style='color:#ff9500;'>안내</b> &nbsp; "
            "먼저 5단계 <b>계산·검토</b>를 실행하세요."
        ), unsafe_allow_html=True)
        st.stop()

    r = st.session_state.tax_result

    # ── 세무조정 검토패키지 PDF — 인쇄 검토용 종합 보고서 ─────────────────────
    st.markdown(section_title(
        "세무조정 검토패키지 PDF (인쇄용)",
        "핵심 세액 지표 · 소득금액조정합계표(조정구분·소득처분·검토메모) · 항목별 계산 근거 · "
        "전수 검토 체크리스트(위험도) · 자료요청 리스트 · 전년 대비 증감분석 · 고객 설명 메모를 "
        "한 부의 PDF로 출력합니다 — 종이로 검토할 수 있는 완결 패키지입니다.",
    ), unsafe_allow_html=True)

    col_pdf, _ = st.columns([1, 4])
    with col_pdf:
        if st.button("검토패키지 PDF 생성", use_container_width=True):
            with st.spinner("PDF 생성 중..."):
                from src.rules.aggregator import aggregate_journals
                from src.rules.data_requests import build_data_requests, assess_risk
                from src.rules.yoy_analysis import yoy_table, yoy_flags
                from src.forms.review_pdf import build_review_pdf, build_client_memo
                import src.rules.legal_basis as legal_basis

                loader = st.session_state.loader
                fy_start = _parse_stored_date(proj.company.fiscal_year_start, date.today())
                fy_end_val = _parse_stored_date(proj.company.fiscal_year_end, date.today())
                _agg = st.session_state.get("journal_aggregates")
                if _agg is None and loader.journals:
                    _agg = aggregate_journals(loader.journals)
                _prev_loader = st.session_state.get("prev_loader")
                _yoy = yoy_table(
                    loader.income_statement,
                    prev_income_df=getattr(_prev_loader, "income_statement", None),
                )
                _rev_cur = loader.get_amount_by_name(("매출액",))
                _rev_prev = 0
                if _yoy is not None:
                    _rev_row = _yoy[_yoy["계정명"].str.replace(" ", "")
                                    .str.contains("매출액", regex=False)]
                    if not _rev_row.empty:
                        _rev_prev = int(_rev_row["전기"].iloc[0])
                _calc_details = st.session_state.get("calc_details") or {}
                # 고객 메모: 5단계에서 수정한 텍스트가 있으면 그것을, 없으면 템플릿 생성
                _memo = (st.session_state.get("client_memo_text")
                         or build_client_memo(_calc_details, proj.company.name, fy_end_val.year))
                try:
                    _pdf_bytes = build_review_pdf(
                        company_name=proj.company.name,
                        business_no=proj.company.business_no,
                        fy_start=fy_start, fy_end=fy_end_val,
                        result=r,
                        calc_details=_calc_details,
                        coverage=st.session_state.get("coverage_results") or [],
                        requests=build_data_requests(
                            loader, proj.manual_input, proj.company, _agg,
                            has_prev_proj=bool(st.session_state.get("prev_proj_loaded")),
                            net_income_confirmed=(
                                loader.get_net_income() != 0
                                or bool(st.session_state.get("manual_net_income"))
                                or bool(st.session_state.get("ni_zero_confirm"))
                            ),
                        ),
                        yoy_df=_yoy,
                        yoy_warn=(yoy_flags(_yoy, _rev_cur, _rev_prev) if _yoy is not None else []),
                        review_memos=(proj.tax_adjustments or {}).get("review_memos", {}),
                        client_memo=_memo,
                        risk_fn=assess_risk,
                        law_check_label=legal_basis.LAST_LAW_FETCH_OK,
                        prior_reserves=proj.manual_input.prior_reserves,
                        depr_denial_end=int((proj.tax_adjustments or {}).get("depreciation_denial_end", 0)),
                        bad_debt_method=proj.manual_input.bad_debt_method,
                        reserve_decrease_overrides=(proj.tax_adjustments or {}).get("reserve_decrease_overrides", {}),
                        reserve_manual_rows=(proj.tax_adjustments or {}).get("reserve_manual_rows", []),
                        disposition_choices=(proj.tax_adjustments or {}).get("disposition_choices", {}),
                    )
                except FileNotFoundError as e:
                    st.error(f"PDF 생성 실패 — 한글 폰트를 찾지 못했습니다: {e}")
                    _pdf_bytes = None
                except Exception as e:
                    # 긴 문구·특수문자·예상 못 한 값으로도 실패할 수 있다 —
                    # 앱 전체가 에러 화면으로 무너지지 않게 안내로 처리
                    st.error(
                        "PDF 생성 실패 — 자료 형식 확인이 필요합니다. "
                        "5단계 계산을 다시 실행한 뒤 재시도하고, 계속 실패하면 "
                        "아래 오류 내용을 확인하세요."
                    )
                    with st.expander("오류 상세 (개발 확인용)"):
                        st.code(f"{type(e).__name__}: {e}")
                    _pdf_bytes = None
            if _pdf_bytes:
                st.success(f"PDF 생성 완료 ({len(_pdf_bytes) / 1024:.0f} KB) — 메모리에서 생성되어 임시파일이 남지 않습니다")
                st.download_button(
                    "다운로드 — 검토패키지 PDF",
                    data=_pdf_bytes,
                    file_name=f"세무조정검토패키지_{safe_filename(proj.company.name)}_{proj.company.fiscal_year_end}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
    st.caption(
        "※ 5단계에서 계산·검토메모를 마친 뒤 생성하세요 — 검토메모와 수정한 고객 설명 문구가 PDF에 반영됩니다."
    )

    st.divider()

    st.markdown(section_title(
        "감사추적 Excel",
        "LLM 판단 근거, 세무조정 계산 근거, 세액 계산 근거 3개 시트 포함",
    ), unsafe_allow_html=True)

    col_gen, _ = st.columns([1, 4])
    with col_gen:
        if st.button("감사추적 Excel 생성", use_container_width=True):
            # 임시파일은 메모리로 읽은 직후 삭제 — 고객명·세무조정 결과가 임시폴더에 남지 않도록
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                out_path = tmp.name
            try:
                generate_audit_trail(
                    llm_results=st.session_state.llm_results,
                    tax_result=r,
                    output_path=out_path,
                    company_name=proj.company.name,
                    model_name=OllamaClient().model,
                    rule_engine_version="0.1.0",
                    law_ref_date=_parse_stored_date(proj.company.fiscal_year_end, date.today()),
                    prior_reserves=proj.manual_input.prior_reserves,
                    depr_denial_end=int((proj.tax_adjustments or {}).get("depreciation_denial_end", 0)),
                    bad_debt_method=proj.manual_input.bad_debt_method,
                    reserve_decrease_overrides=(proj.tax_adjustments or {}).get("reserve_decrease_overrides", {}),
                    reserve_manual_rows=(proj.tax_adjustments or {}).get("reserve_manual_rows", []),
                    disposition_choices=(proj.tax_adjustments or {}).get("disposition_choices", {}),
                )
                with open(out_path, "rb") as f:
                    _audit_bytes = f.read()
            finally:
                try:
                    os.unlink(out_path)
                except OSError:
                    pass
            st.download_button(
                "다운로드 — 감사추적 Excel",
                data=_audit_bytes,
                file_name=(
                    f"감사추적_{safe_filename(proj.company.name)}"
                    f"_{proj.company.fiscal_year_end}.xlsx"
                ),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

    st.divider()

    st.markdown(section_title(
        "프로젝트 저장 (.taxproj)",
        "입력 데이터와 계산 결과를 JSON 형식으로 저장합니다.",
    ), unsafe_allow_html=True)

    col_proj, _ = st.columns([1, 4])
    with col_proj:
        if st.button("프로젝트 파일 생성", use_container_width=True):
            # 임시파일은 메모리로 읽은 직후 삭제 (고객자료 잔존 방지)
            with tempfile.NamedTemporaryFile(suffix=".taxproj", delete=False) as tmp:
                _proj_path = tmp.name
            try:
                proj.save(_proj_path)
                with open(_proj_path, "rb") as f:
                    _proj_bytes = f.read()
            finally:
                try:
                    os.unlink(_proj_path)
                except OSError:
                    pass
            st.download_button(
                "다운로드 — .taxproj",
                data=_proj_bytes,
                file_name=(
                    f"{safe_filename(proj.company.name)}"
                    f"_{proj.company.fiscal_year_end}.taxproj"
                ),
                mime="application/json",
                use_container_width=True,
            )

    st.divider()

    st.markdown(section_title(
        "추천 별지 서식",
        "계산된 항목 기준으로 신고 시 첨부할 서식 목록을 안내합니다.",
    ), unsafe_allow_html=True)

    forms = recommend_forms(
        has_depreciation=r.depreciation_excess > 0,
        has_entertainment=r.entertainment_excess > 0,
        has_donation=False,
        has_pension=r.pension_excess > 0,
        has_bad_debt=r.bad_debt_excess > 0,
        has_interest=False,
        has_forex=False,
        has_dividend=False,
        has_vehicle=False,
        has_tax_credit=False,
        is_sme=proj.company.is_sme,
    )
    if forms:
        import pandas as pd
        rows = [
            {
                "서식":  f.key,
                "명칭":  f.name,
                "검증":  "✓ API 확인" if f.verified else "⚠ 잠정",
            }
            for f in forms
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.caption("해당 서식 없음")

