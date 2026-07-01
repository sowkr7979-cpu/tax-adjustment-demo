"""OpenAI(openai.com) 스타일 CSS 테마.

디자인 토큰:
  Text     #0d0d0d (primary) / #6e6e80 (secondary) / #8e8ea0 (muted)
  Surface  #ffffff / subtle #f7f7f8
  Border   #e5e5e5 / #ececf1
  Primary  #0d0d0d (near-black pill 버튼) / hover #2d2d2d
  Accent   #10a37f (green — 링크·포커스·활성 내비)
  State     success #10a37f/bg#ecfdf5 · warning #b45309/bg#fffbeb
            error #ef4146/bg#fef2f2 · info #10a37f/bg#f7f7f8

폰트는 외부 fetch 없이 시스템 스택만 사용(네트워크 허용목록·프라이버시 준수).
OpenAI의 Söhne가 없으면 중립적 산세리프로 폴백한다.
"""

GOOGLE_CSS = """
<style>
/* ── 기본 폰트 & 렌더링 ──────────────────────────────────── */
html, body, [class*="css"] {
    font-family: "Söhne", "ui-sans-serif", -apple-system, BlinkMacSystemFont,
                 "Segoe UI", Helvetica, "Apple Color Emoji", Arial, sans-serif !important;
    -webkit-font-smoothing: antialiased !important;
    -moz-osx-font-smoothing: grayscale !important;
}

/* ── 배경 ─────────────────────────────────────────────────── */
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
.main {
    background-color: #ffffff !important;
}

/* ── 상단 헤더 ────────────────────────────────────────────── */
header[data-testid="stHeader"] {
    background-color: rgba(255, 255, 255, 0.9) !important;
    backdrop-filter: saturate(180%) blur(12px) !important;
    -webkit-backdrop-filter: saturate(180%) blur(12px) !important;
    border-bottom: 1px solid #ececf1 !important;
}

/* ── 사이드바 ─────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background-color: #f7f7f8 !important;
    border-right: 1px solid #ececf1 !important;
}

[data-testid="stSidebar"] > div:first-child {
    background-color: #f7f7f8 !important;
    padding: 1.25rem 1rem 1.5rem 1rem !important;
}

/* 사이드바 메뉴 라벨 숨김 */
[data-testid="stSidebar"] .stRadio > div:first-child > label {
    display: none !important;
}

/* 사이드바 nav 항목 */
[data-testid="stSidebar"] .stRadio [role="radiogroup"] {
    gap: 2px !important;
    display: flex !important;
    flex-direction: column !important;
}

[data-testid="stSidebar"] .stRadio [role="radiogroup"] label {
    display: flex !important;
    align-items: center !important;
    padding: 0.6rem 0.9rem !important;
    border-radius: 8px !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    color: #40414f !important;
    cursor: pointer !important;
    transition: background-color 0.12s ease, color 0.12s ease !important;
    width: 100% !important;
}

[data-testid="stSidebar"] .stRadio [role="radiogroup"] label:hover {
    background-color: #ececf1 !important;
    color: #0d0d0d !important;
}

/* ── 메인 컨텐츠 ──────────────────────────────────────────── */
.main .block-container {
    padding: 2.25rem 2.5rem 3rem 2.5rem !important;
    max-width: 1080px !important;
}

/* ── 제목/헤딩 타이포그래피 (OpenAI 톤 — 타이트·중간굵기) ──── */
h1 {
    font-size: 2.25rem !important;
    font-weight: 600 !important;
    color: #0d0d0d !important;
    letter-spacing: -0.022em !important;
    line-height: 1.15 !important;
    margin-bottom: 0.4rem !important;
}

h2 {
    font-size: 1.5rem !important;
    font-weight: 600 !important;
    color: #0d0d0d !important;
    letter-spacing: -0.015em !important;
    margin-top: 1.6rem !important;
}

h3 {
    font-size: 1.12rem !important;
    font-weight: 600 !important;
    color: #0d0d0d !important;
    letter-spacing: -0.01em !important;
}

p {
    color: #40414f !important;
    font-size: 15px !important;
    line-height: 1.65 !important;
}

a { color: #10a37f !important; }

/* ── 기본 버튼 (OpenAI near-black pill) ───────────────────── */
.stButton > button {
    background-color: #0d0d0d !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 999px !important;
    padding: 0.55rem 1.5rem !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    letter-spacing: 0 !important;
    transition: background-color 0.15s ease, transform 0.05s ease !important;
    box-shadow: none !important;
    height: auto !important;
    min-height: 0 !important;
    line-height: 1.5 !important;
}

.stButton > button:hover {
    background-color: #2d2d2d !important;
    color: #ffffff !important;
    box-shadow: none !important;
    border: none !important;
}

.stButton > button:active,
.stButton > button:focus {
    background-color: #000000 !important;
    box-shadow: none !important;
    border: none !important;
    outline: none !important;
}

.stButton > button:disabled {
    background-color: #d9d9e3 !important;
    color: #ffffff !important;
}

/* ── 다운로드 버튼 (아웃라인 pill) ────────────────────────── */
.stDownloadButton > button {
    background-color: #ffffff !important;
    color: #0d0d0d !important;
    border: 1px solid #d9d9e3 !important;
    border-radius: 999px !important;
    padding: 0.55rem 1.5rem !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    transition: background-color 0.15s ease, border-color 0.15s ease !important;
}

.stDownloadButton > button:hover {
    background-color: #f7f7f8 !important;
    border-color: #0d0d0d !important;
}

/* ── 텍스트 입력 ──────────────────────────────────────────── */
.stTextInput > div > div > input {
    background-color: #ffffff !important;
    border: 1px solid #d9d9e3 !important;
    border-radius: 10px !important;
    color: #0d0d0d !important;
    font-size: 15px !important;
    padding: 0.45rem 0.85rem !important;
    height: 42px !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
}

.stTextInput > div > div > input:focus {
    border-color: #10a37f !important;
    box-shadow: 0 0 0 3px rgba(16, 163, 127, 0.15) !important;
    outline: none !important;
}

/* ── 숫자 입력 ────────────────────────────────────────────── */
.stNumberInput > div > div > input {
    background-color: #ffffff !important;
    border: 1px solid #d9d9e3 !important;
    border-radius: 10px !important;
    color: #0d0d0d !important;
    font-size: 15px !important;
    height: 42px !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
}

.stNumberInput > div > div > input:focus {
    border-color: #10a37f !important;
    box-shadow: 0 0 0 3px rgba(16, 163, 127, 0.15) !important;
    outline: none !important;
}

.stNumberInput button {
    background-color: #f7f7f8 !important;
    border: 1px solid #d9d9e3 !important;
    color: #6e6e80 !important;
    border-radius: 8px !important;
}

/* ── 텍스트에어리어 ────────────────────────────────────────── */
.stTextArea > div > div > textarea {
    background-color: #ffffff !important;
    border: 1px solid #d9d9e3 !important;
    border-radius: 10px !important;
    color: #0d0d0d !important;
    font-size: 15px !important;
    padding: 0.6rem 0.85rem !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
}

.stTextArea > div > div > textarea:focus {
    border-color: #10a37f !important;
    box-shadow: 0 0 0 3px rgba(16, 163, 127, 0.15) !important;
    outline: none !important;
}

/* ── 셀렉트박스 ───────────────────────────────────────────── */
[data-testid="stSelectbox"] > div > div {
    background-color: #ffffff !important;
    border: 1px solid #d9d9e3 !important;
    border-radius: 10px !important;
    color: #0d0d0d !important;
}

/* ── 날짜 입력 ────────────────────────────────────────────── */
[data-testid="stDateInput"] input {
    background-color: #ffffff !important;
    border: 1px solid #d9d9e3 !important;
    border-radius: 10px !important;
    color: #0d0d0d !important;
    font-size: 15px !important;
}

/* ── 입력 라벨 ────────────────────────────────────────────── */
.stTextInput label, .stNumberInput label, .stTextArea label,
.stSelectbox label, .stDateInput label, .stFileUploader label {
    font-size: 13px !important;
    font-weight: 500 !important;
    color: #0d0d0d !important;
    letter-spacing: 0 !important;
    margin-bottom: 4px !important;
}

/* ── 메트릭 카드 ──────────────────────────────────────────── */
[data-testid="stMetric"] {
    background-color: #ffffff !important;
    border-radius: 14px !important;
    padding: 1.2rem 1.4rem !important;
    border: 1px solid #e5e5e5 !important;
    box-shadow: none !important;
}

[data-testid="stMetricLabel"] > div,
[data-testid="stMetricLabel"] p {
    font-size: 12px !important;
    font-weight: 500 !important;
    color: #6e6e80 !important;
    text-transform: none !important;
    letter-spacing: 0 !important;
    margin: 0 !important;
}

[data-testid="stMetricValue"] {
    font-size: 1.65rem !important;
    font-weight: 600 !important;
    color: #0d0d0d !important;
    letter-spacing: -0.02em !important;
}

[data-testid="stMetricDelta"] {
    font-size: 13px !important;
    font-weight: 500 !important;
}

/* ── 구분선 ───────────────────────────────────────────────── */
hr {
    border: none !important;
    border-top: 1px solid #ececf1 !important;
    margin: 1.25rem 0 !important;
}

/* ── 알림/배너 (은은한 상태 색) ──────────────────────────── */
[data-testid="stAlert"] {
    border-radius: 12px !important;
    border: 1px solid #ececf1 !important;
    padding: 0.75rem 1rem !important;
}

[data-testid="stAlert"][data-baseweb="notification"][kind="positive"],
.element-container .stSuccess {
    background-color: #ecfdf5 !important;
}

[data-testid="stAlert"][data-baseweb="notification"][kind="warning"],
.element-container .stWarning {
    background-color: #fffbeb !important;
}

[data-testid="stAlert"][data-baseweb="notification"][kind="negative"],
.element-container .stError {
    background-color: #fef2f2 !important;
}

[data-testid="stAlert"][data-baseweb="notification"][kind="info"],
.element-container .stInfo {
    background-color: #f7f7f8 !important;
}

/* ── 데이터프레임 & 테이블 ────────────────────────────────── */
[data-testid="stDataFrame"],
[data-testid="stTable"] {
    border-radius: 12px !important;
    overflow: hidden !important;
    border: 1px solid #e5e5e5 !important;
    box-shadow: none !important;
}

/* ── 파일 업로더 ──────────────────────────────────────────── */
[data-testid="stFileUploader"] section {
    border: 1.5px dashed #d9d9e3 !important;
    border-radius: 12px !important;
    background-color: #ffffff !important;
    transition: border-color 0.15s ease, background-color 0.15s ease !important;
}

[data-testid="stFileUploader"] section:hover {
    border-color: #10a37f !important;
    background-color: #f7fdfb !important;
}

[data-testid="stFileUploaderDropzoneInstructions"] {
    color: #6e6e80 !important;
    font-size: 14px !important;
}

/* ── 라디오 버튼 ──────────────────────────────────────────── */
.stRadio [role="radiogroup"] {
    gap: 4px !important;
}

.stRadio [data-baseweb="radio"] > div:first-child {
    border-color: #10a37f !important;
}

/* ── 체크박스 ────────────────────────────────────────────── */
.stCheckbox [data-baseweb="checkbox"] [data-checked="true"] {
    background-color: #10a37f !important;
    border-color: #10a37f !important;
}

/* ── 스피너 ───────────────────────────────────────────────── */
[data-testid="stSpinner"] > div {
    border-top-color: #10a37f !important;
}

.stSpinner svg {
    color: #10a37f !important;
}

/* ── 코드 블록 ────────────────────────────────────────────── */
code {
    background-color: #f7f7f8 !important;
    border-radius: 6px !important;
    padding: 0.1rem 0.35rem !important;
    font-size: 13px !important;
    color: #0d0d0d !important;
    border: 1px solid #ececf1 !important;
}

/* ── 익스팬더 ────────────────────────────────────────────── */
[data-testid="stExpander"] > div:first-child {
    border-radius: 12px !important;
    border: 1px solid #e5e5e5 !important;
    background-color: #f7f7f8 !important;
}

[data-testid="stExpander"] > div:first-child:hover {
    background-color: #ececf1 !important;
}

/* ── 컬럼 갭 ──────────────────────────────────────────────── */
[data-testid="column"] {
    gap: 0 !important;
}

/* ── 스크롤바 ─────────────────────────────────────────────── */
::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}

::-webkit-scrollbar-track {
    background: transparent;
}

::-webkit-scrollbar-thumb {
    background-color: #d9d9e3;
    border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
    background-color: #b4b4c4;
}

/* ── caption (작은 설명 텍스트) ───────────────────────────── */
small, .caption, [data-testid="stCaptionContainer"] p {
    color: #6e6e80 !important;
    font-size: 12px !important;
}
</style>
"""

# 하위 호환 별칭 (기존 import 경로 유지)
APPLE_CSS = GOOGLE_CSS


def page_header(title: str, subtitle: str = "") -> str:
    """OpenAI 스타일 페이지 헤더 HTML."""
    sub_html = (
        f'<p style="font-size:15px;color:#6e6e80;margin:0.35rem 0 0 0;'
        f'font-weight:400;">{subtitle}</p>'
        if subtitle else ""
    )
    return (
        f'<div style="margin-bottom:1.75rem;padding-bottom:1.25rem;'
        f'border-bottom:1px solid #ececf1;">'
        f'<h1 style="font-size:2.25rem;font-weight:600;color:#0d0d0d;'
        f'letter-spacing:-0.022em;margin:0;line-height:1.15;">{title}</h1>'
        f'{sub_html}</div>'
    )


def section_title(title: str, subtitle: str = "") -> str:
    """섹션 제목 HTML (카드 내부용)."""
    sub_html = (
        f'<p style="font-size:13px;color:#6e6e80;margin:2px 0 0 0;">{subtitle}</p>'
        if subtitle else ""
    )
    return (
        f'<div style="margin-bottom:0.75rem;">'
        f'<h3 style="font-size:1.08rem;font-weight:600;color:#0d0d0d;margin:0;'
        f'letter-spacing:-0.01em;">{title}</h3>{sub_html}</div>'
    )


def status_badge(label: str, ok: bool) -> str:
    """상태 배지 HTML (OpenAI green / red)."""
    color = "#10a37f" if ok else "#ef4146"
    bg = "#ecfdf5" if ok else "#fef2f2"
    return (
        f'<span style="display:inline-flex;align-items:center;gap:5px;'
        f'background:{bg};color:{color};font-size:12px;font-weight:600;'
        f'padding:3px 10px;border-radius:999px;">'
        f'<span style="width:6px;height:6px;border-radius:50%;'
        f'background:{color};display:inline-block;"></span>{label}</span>'
    )


def info_card(content: str) -> str:
    """은은한 정보 카드 (OpenAI subtle surface)."""
    return (
        f'<div style="background:#f7f7f8;border-radius:12px;'
        f'padding:1rem 1.2rem;margin-bottom:1rem;'
        f'border:1px solid #e5e5e5;">'
        f'{content}</div>'
    )


def striped_by_group(df, group_col: str = "전표번호"):
    """분개 표를 전표(그룹) 단위로 흰색↔회색 교대 표시하는 pandas Styler 반환.

    같은 전표번호의 차·대변 라인은 같은 색 — 전표가 바뀔 때마다 색이 교대되어
    전표 묶음을 눈으로 구분하기 쉽다. st.dataframe(striped_by_group(df), ...)로 사용.
    group_col이 없으면 행 단위 교대.
    """
    if df is None or len(df) == 0:
        return df
    if group_col in df.columns:
        col = df[group_col].astype(str)
        group_no = col.ne(col.shift()).cumsum()
    else:
        import pandas as pd
        group_no = pd.Series(range(len(df)), index=df.index)
    shade = (group_no % 2 == 0)

    def _row_style(row):
        bg = "background-color: #f7f7f8" if shade.loc[row.name] else ""
        return [bg] * len(row)

    return df.style.apply(_row_style, axis=1)
