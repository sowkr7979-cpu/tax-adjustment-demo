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
from src.ui.styles import APPLE_CSS
from src.views import basic_info, upload, manual, llm, calc, output


# ── 설정 ──────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="법인세 세무조정 자동화",
    page_icon="📊",
    layout="wide",
)

st.markdown(APPLE_CSS, unsafe_allow_html=True)

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
    "4. LLM 분석",
    "5. 계산·검토",
    "6. 출력",
]

with st.sidebar:
    st.markdown("""
    <div style="
        display:flex; align-items:center; gap:10px;
        padding:0.5rem 0 1.25rem 0;
        margin-bottom:0.25rem;
        border-bottom:1px solid #d2d2d7;
    ">
        <div style="
            width:34px; height:34px; flex-shrink:0;
            background:linear-gradient(145deg,#0071e3,#34aadc);
            border-radius:9px;
            display:flex; align-items:center; justify-content:center;
            color:white; font-size:16px; font-weight:800;
            box-shadow:0 2px 8px rgba(0,113,227,0.35);
        ">세</div>
        <div>
            <div style="font-size:14px;font-weight:700;color:#1d1d1f;letter-spacing:-0.3px;line-height:1.2;">세무조정 자동화</div>
            <div style="font-size:11px;color:#86868b;margin-top:1px;">법인세 신고서 작성 시스템</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    page = st.radio("메뉴", NAV_ITEMS, label_visibility="collapsed")

    st.markdown("<br>" * 2, unsafe_allow_html=True)

    proj = st.session_state.project
    ollama = OllamaClient()
    llm_ok = ollama.is_available()
    llm_color = "#34c759" if llm_ok else "#ff3b30"
    llm_bg = "rgba(52,199,89,0.08)" if llm_ok else "rgba(255,59,48,0.08)"

    st.markdown(f"""
    <div style="border-top:1px solid #d2d2d7; padding-top:1rem; margin-top:0.5rem;">
        <div style="
            display:flex; align-items:center; gap:7px;
            background:{llm_bg}; border-radius:10px;
            padding:0.55rem 0.8rem; margin-bottom:0.5rem;
        ">
            <div style="width:7px;height:7px;border-radius:50%;background:{llm_color};flex-shrink:0;"></div>
            <div>
                <div style="font-size:13px;font-weight:600;color:#1d1d1f;line-height:1.2;">
                    Ollama {"연결됨" if llm_ok else "오프라인"}
                </div>
                <div style="font-size:11px;color:#86868b;margin-top:1px;">{ollama.model}</div>
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
elif page == "4. LLM 분석":
    llm.render(proj, llm_ok)
elif page == "5. 계산·검토":
    calc.render(proj)
elif page == "6. 출력":
    output.render(proj)
