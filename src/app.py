"""법인세 세무조정 자동화 — Streamlit 메인 앱 (페이지 라우팅).

화면 본문은 src/views/ 페이지별 모듈에 있다:
  basic_info(1단계) · upload(2단계) · manual(3단계) · llm(4단계) · calc(5단계) · output(6단계)
"""
from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from src.parsers.smart_a import SmartALoader
from src.project.taxproj import TaxProject
from src.llm.ollama_client import OllamaClient
from src.ui.styles import GOOGLE_CSS
from src.views import basic_info, upload, manual, llm, calc, output


# ── 설정 ──────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="법인세 세무조정 자동화",
    page_icon="📊",
    layout="wide",
)

st.markdown(GOOGLE_CSS, unsafe_allow_html=True)

# 세션 상태 초기화
if "project" not in st.session_state:
    st.session_state.project = TaxProject()
if "loader" not in st.session_state:
    st.session_state.loader = SmartALoader()
if "prev_loader" not in st.session_state:
    st.session_state.prev_loader = SmartALoader()   # 전기(전년도) 재무제표
if "llm_results" not in st.session_state:
    st.session_state.llm_results = []
if "tax_result" not in st.session_state:
    st.session_state.tax_result = None


# ── 사이드바 ─────────────────────────────────────────────────────────────────

NAV_ITEMS = [
    "1. 기본정보",
    "2. 파일 업로드",
    "3. 수기 입력",
    "4. AI 검토 보조",
    "5. 계산·검토",
    "6. 출력",
]

with st.sidebar:
    st.markdown("""
    <div style="
        display:flex; align-items:center; gap:10px;
        padding:0.5rem 0 1.25rem 0;
        margin-bottom:0.25rem;
        border-bottom:1px solid #ececf1;
    ">
        <div style="
            width:34px; height:34px; flex-shrink:0;
            background:#0d0d0d;
            border-radius:8px;
            display:flex; align-items:center; justify-content:center;
            color:white; font-size:16px; font-weight:600;
        ">세</div>
        <div>
            <div style="font-size:14px;font-weight:600;color:#0d0d0d;letter-spacing:-0.01em;line-height:1.2;">세무조정 자동화</div>
            <div style="font-size:11px;color:#6e6e80;margin-top:1px;">법인세 신고서 작성 시스템</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    page = st.radio("메뉴", NAV_ITEMS, label_visibility="collapsed")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── 데모 데이터 (면접관용 — 업로드 없이 결과 확인) ──────────────────────
    if st.button("🧪 데모 데이터 불러오기", width="stretch"):
        from src.demo.sample_case import build_demo_loader, build_demo_project

        st.session_state.loader = build_demo_loader()
        st.session_state.project = build_demo_project()
        st.session_state.prev_loader = SmartALoader()
        # 파생 상태 초기화 — 새 데모로 다시 계산되게
        for _k in ("tax_result", "calc_details", "coverage_results",
                   "journal_aggregates", "depr_results", "rule_results",
                   "llm_results", "llm_job", "manual_net_income", "ni_zero_confirm"):
            st.session_state.pop(_k, None)
        st.session_state.demo_loaded = True
        st.rerun()

    if st.session_state.get("demo_loaded"):
        st.caption("가상 회사 **한빛정밀(주)** 로드됨 · 2단계부터 확인하세요 (더미 데이터)")

    st.markdown("<br>", unsafe_allow_html=True)

    proj = st.session_state.project
    llm_client = OllamaClient()
    llm_ok = llm_client.is_available()
    # Ollama 미기동이면 '오류'가 아니라 '선택 기능 비활성'으로 중립 표시
    llm_color = "#10a37f" if llm_ok else "#8e8ea0"
    llm_bg = "#ecfdf5" if llm_ok else "#f7f7f8"
    _title = "로컬 LLM(Ollama) 연결됨" if llm_ok else "AI 검토보조 · 선택 기능"
    _sub = llm_client.model if llm_ok else "미연결 — 규칙엔진 계산은 정상 동작"

    st.markdown(f"""
    <div style="border-top:1px solid #ececf1; padding-top:1rem; margin-top:0.5rem;">
        <div style="
            display:flex; align-items:center; gap:7px;
            background:{llm_bg}; border-radius:10px;
            padding:0.55rem 0.8rem; margin-bottom:0.5rem;
        ">
            <div style="width:7px;height:7px;border-radius:50%;background:{llm_color};flex-shrink:0;"></div>
            <div>
                <div style="font-size:13px;font-weight:600;color:#0d0d0d;line-height:1.2;">{_title}</div>
                <div style="font-size:11px;color:#6e6e80;margin-top:1px;">{_sub}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── 페이지 라우팅 ─────────────────────────────────────────────────────────────

if page == "1. 기본정보":
    basic_info.render(proj)
elif page == "2. 파일 업로드":
    upload.render(st.session_state.loader)
elif page == "3. 수기 입력":
    manual.render(proj)
elif page == "4. AI 검토 보조":
    llm.render(proj, llm_ok)
elif page == "5. 계산·검토":
    calc.render(proj)
elif page == "6. 출력":
    output.render(proj)
