"""Apple.com/kr 스타일 CSS 테마."""

APPLE_CSS = """
<style>
/* ── 기본 폰트 & 렌더링 ──────────────────────────────────── */
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text",
                 "Helvetica Neue", Arial, sans-serif !important;
    -webkit-font-smoothing: antialiased !important;
    -moz-osx-font-smoothing: grayscale !important;
}

/* ── 배경 ─────────────────────────────────────────────────── */
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
.main {
    background-color: #fbfbfd !important;
}

/* ── 상단 헤더 (Apple 글래스모피즘) ─────────────────────────── */
header[data-testid="stHeader"] {
    background-color: rgba(251, 251, 253, 0.85) !important;
    backdrop-filter: saturate(180%) blur(20px) !important;
    -webkit-backdrop-filter: saturate(180%) blur(20px) !important;
    border-bottom: 1px solid rgba(0, 0, 0, 0.08) !important;
}

/* ── 사이드바 ─────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background-color: #f5f5f7 !important;
    border-right: 1px solid #d2d2d7 !important;
}

[data-testid="stSidebar"] > div:first-child {
    background-color: #f5f5f7 !important;
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
    padding: 0.55rem 0.75rem !important;
    border-radius: 10px !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    color: #3a3a3c !important;
    cursor: pointer !important;
    transition: background-color 0.12s ease !important;
    width: 100% !important;
}

[data-testid="stSidebar"] .stRadio [role="radiogroup"] label:hover {
    background-color: rgba(0, 0, 0, 0.05) !important;
}

/* ── 메인 컨텐츠 ──────────────────────────────────────────── */
.main .block-container {
    padding: 2rem 2.5rem 3rem 2.5rem !important;
    max-width: 1100px !important;
}

/* ── 제목/헤딩 타이포그래피 ───────────────────────────────── */
h1 {
    font-size: 2rem !important;
    font-weight: 700 !important;
    color: #1d1d1f !important;
    letter-spacing: -0.6px !important;
    line-height: 1.15 !important;
    margin-bottom: 0.4rem !important;
}

h2 {
    font-size: 1.4rem !important;
    font-weight: 700 !important;
    color: #1d1d1f !important;
    letter-spacing: -0.3px !important;
    margin-top: 1.5rem !important;
}

h3 {
    font-size: 1.1rem !important;
    font-weight: 600 !important;
    color: #1d1d1f !important;
}

p {
    color: #1d1d1f !important;
    font-size: 15px !important;
    line-height: 1.6 !important;
}

/* ── 기본 버튼 (Apple 파란 필 버튼) ──────────────────────── */
.stButton > button {
    background-color: #0071e3 !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 980px !important;
    padding: 0.5rem 1.3rem !important;
    font-size: 15px !important;
    font-weight: 500 !important;
    letter-spacing: 0.1px !important;
    transition: background-color 0.15s ease !important;
    box-shadow: none !important;
    height: auto !important;
    min-height: 0 !important;
    line-height: 1.5 !important;
}

.stButton > button:hover {
    background-color: #0077ed !important;
    color: #ffffff !important;
    box-shadow: none !important;
    border: none !important;
}

.stButton > button:active,
.stButton > button:focus {
    background-color: #006edb !important;
    box-shadow: none !important;
    border: none !important;
    outline: none !important;
}

/* ── 다운로드 버튼 ────────────────────────────────────────── */
.stDownloadButton > button {
    background-color: rgba(0, 113, 227, 0.1) !important;
    color: #0071e3 !important;
    border: none !important;
    border-radius: 980px !important;
    padding: 0.5rem 1.3rem !important;
    font-size: 15px !important;
    font-weight: 500 !important;
    transition: background-color 0.15s ease !important;
}

.stDownloadButton > button:hover {
    background-color: rgba(0, 113, 227, 0.18) !important;
}

/* ── 텍스트 입력 ──────────────────────────────────────────── */
.stTextInput > div > div > input {
    background-color: #ffffff !important;
    border: 1px solid #d2d2d7 !important;
    border-radius: 10px !important;
    color: #1d1d1f !important;
    font-size: 15px !important;
    padding: 0.45rem 0.85rem !important;
    height: 40px !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
}

.stTextInput > div > div > input:focus {
    border-color: #0071e3 !important;
    box-shadow: 0 0 0 3px rgba(0, 113, 227, 0.15) !important;
    outline: none !important;
}

/* ── 숫자 입력 ────────────────────────────────────────────── */
.stNumberInput > div > div > input {
    background-color: #ffffff !important;
    border: 1px solid #d2d2d7 !important;
    border-radius: 10px !important;
    color: #1d1d1f !important;
    font-size: 15px !important;
    height: 40px !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
}

.stNumberInput > div > div > input:focus {
    border-color: #0071e3 !important;
    box-shadow: 0 0 0 3px rgba(0, 113, 227, 0.15) !important;
    outline: none !important;
}

.stNumberInput button {
    background-color: #f5f5f7 !important;
    border: 1px solid #d2d2d7 !important;
    color: #3a3a3c !important;
    border-radius: 6px !important;
}

/* ── 텍스트에어리어 ────────────────────────────────────────── */
.stTextArea > div > div > textarea {
    background-color: #ffffff !important;
    border: 1px solid #d2d2d7 !important;
    border-radius: 12px !important;
    color: #1d1d1f !important;
    font-size: 15px !important;
    padding: 0.6rem 0.85rem !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
}

.stTextArea > div > div > textarea:focus {
    border-color: #0071e3 !important;
    box-shadow: 0 0 0 3px rgba(0, 113, 227, 0.15) !important;
    outline: none !important;
}

/* ── 셀렉트박스 ───────────────────────────────────────────── */
[data-testid="stSelectbox"] > div > div {
    background-color: #ffffff !important;
    border: 1px solid #d2d2d7 !important;
    border-radius: 10px !important;
    color: #1d1d1f !important;
}

/* ── 날짜 입력 ────────────────────────────────────────────── */
[data-testid="stDateInput"] input {
    background-color: #ffffff !important;
    border: 1px solid #d2d2d7 !important;
    border-radius: 10px !important;
    color: #1d1d1f !important;
    font-size: 15px !important;
}

/* ── 입력 라벨 ────────────────────────────────────────────── */
.stTextInput label, .stNumberInput label, .stTextArea label,
.stSelectbox label, .stDateInput label, .stFileUploader label {
    font-size: 13px !important;
    font-weight: 600 !important;
    color: #1d1d1f !important;
    letter-spacing: 0.1px !important;
    margin-bottom: 3px !important;
}

/* ── 메트릭 카드 (핵심 — Apple 스타일 카드) ──────────────── */
[data-testid="stMetric"] {
    background-color: #ffffff !important;
    border-radius: 16px !important;
    padding: 1.2rem 1.4rem !important;
    border: 1px solid #e8e8ed !important;
    box-shadow: 0 1px 8px rgba(0, 0, 0, 0.05), 0 0 1px rgba(0,0,0,0.04) !important;
}

[data-testid="stMetricLabel"] > div,
[data-testid="stMetricLabel"] p {
    font-size: 12px !important;
    font-weight: 600 !important;
    color: #86868b !important;
    text-transform: uppercase !important;
    letter-spacing: 0.5px !important;
    margin: 0 !important;
}

[data-testid="stMetricValue"] {
    font-size: 1.6rem !important;
    font-weight: 700 !important;
    color: #1d1d1f !important;
    letter-spacing: -0.5px !important;
}

[data-testid="stMetricDelta"] {
    font-size: 13px !important;
    font-weight: 500 !important;
}

/* ── 구분선 ───────────────────────────────────────────────── */
hr {
    border: none !important;
    border-top: 1px solid #e8e8ed !important;
    margin: 1.25rem 0 !important;
}

/* ── 알림/배너 ────────────────────────────────────────────── */
[data-testid="stAlert"] {
    border-radius: 12px !important;
    border: none !important;
    padding: 0.75rem 1rem !important;
}

/* success */
[data-testid="stAlert"][data-baseweb="notification"][kind="positive"],
.element-container .stSuccess {
    background-color: rgba(52, 199, 89, 0.1) !important;
}

/* warning */
[data-testid="stAlert"][data-baseweb="notification"][kind="warning"],
.element-container .stWarning {
    background-color: rgba(255, 149, 0, 0.1) !important;
}

/* error */
[data-testid="stAlert"][data-baseweb="notification"][kind="negative"],
.element-container .stError {
    background-color: rgba(255, 59, 48, 0.1) !important;
}

/* ── 데이터프레임 & 테이블 ────────────────────────────────── */
[data-testid="stDataFrame"],
[data-testid="stTable"] {
    border-radius: 14px !important;
    overflow: hidden !important;
    border: 1px solid #e8e8ed !important;
    box-shadow: 0 1px 6px rgba(0, 0, 0, 0.04) !important;
}

/* ── 파일 업로더 ──────────────────────────────────────────── */
[data-testid="stFileUploader"] section {
    border: 1.5px dashed #d2d2d7 !important;
    border-radius: 14px !important;
    background-color: #ffffff !important;
    transition: border-color 0.15s ease, background-color 0.15s ease !important;
}

[data-testid="stFileUploader"] section:hover {
    border-color: #0071e3 !important;
    background-color: rgba(0, 113, 227, 0.02) !important;
}

[data-testid="stFileUploaderDropzoneInstructions"] {
    color: #86868b !important;
    font-size: 14px !important;
}

/* ── 라디오 버튼 ──────────────────────────────────────────── */
.stRadio [role="radiogroup"] {
    gap: 4px !important;
}

.stRadio [data-baseweb="radio"] > div:first-child {
    border-color: #0071e3 !important;
}

/* ── 체크박스 ────────────────────────────────────────────── */
.stCheckbox [data-baseweb="checkbox"] [data-checked="true"] {
    background-color: #0071e3 !important;
    border-color: #0071e3 !important;
}

/* ── 스피너 ───────────────────────────────────────────────── */
[data-testid="stSpinner"] > div {
    border-top-color: #0071e3 !important;
}

.stSpinner svg {
    color: #0071e3 !important;
}

/* ── 코드 블록 ────────────────────────────────────────────── */
code {
    background-color: #f5f5f7 !important;
    border-radius: 5px !important;
    padding: 0.1rem 0.35rem !important;
    font-size: 13px !important;
    color: #1d1d1f !important;
    border: none !important;
}

/* ── 익스팬더 ────────────────────────────────────────────── */
[data-testid="stExpander"] > div:first-child {
    border-radius: 12px !important;
    border: 1px solid #e8e8ed !important;
    background-color: #f5f5f7 !important;
}

[data-testid="stExpander"] > div:first-child:hover {
    background-color: #ebebef !important;
}

/* ── 컬럼 갭 ──────────────────────────────────────────────── */
[data-testid="column"] {
    gap: 0 !important;
}

/* ── 스크롤바 ─────────────────────────────────────────────── */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}

::-webkit-scrollbar-track {
    background: transparent;
}

::-webkit-scrollbar-thumb {
    background-color: #c7c7cc;
    border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
    background-color: #aeaeb2;
}

/* ── caption (작은 설명 텍스트) ───────────────────────────── */
small, .caption, [data-testid="stCaptionContainer"] p {
    color: #86868b !important;
    font-size: 12px !important;
}
</style>
"""


def page_header(title: str, subtitle: str = "") -> str:
    """Apple 스타일 페이지 헤더 HTML."""
    sub_html = (
        f'<p style="font-size:15px;color:#86868b;margin:0.3rem 0 0 0;'
        f'font-weight:400;">{subtitle}</p>'
        if subtitle else ""
    )
    return (
        f'<div style="margin-bottom:1.75rem;padding-bottom:1.25rem;'
        f'border-bottom:1px solid #e8e8ed;">'
        f'<h1 style="font-size:2rem;font-weight:700;color:#1d1d1f;'
        f'letter-spacing:-0.6px;margin:0;line-height:1.1;">{title}</h1>'
        f'{sub_html}</div>'
    )


def section_title(title: str, subtitle: str = "") -> str:
    """섹션 제목 HTML (카드 내부용)."""
    sub_html = (
        f'<p style="font-size:13px;color:#86868b;margin:2px 0 0 0;">{subtitle}</p>'
        if subtitle else ""
    )
    return (
        f'<div style="margin-bottom:0.75rem;">'
        f'<h3 style="font-size:1.05rem;font-weight:600;color:#1d1d1f;margin:0;">'
        f'{title}</h3>{sub_html}</div>'
    )


def status_badge(label: str, ok: bool) -> str:
    """상태 배지 HTML."""
    color = "#34c759" if ok else "#ff3b30"
    bg = "rgba(52,199,89,0.1)" if ok else "rgba(255,59,48,0.1)"
    return (
        f'<span style="display:inline-flex;align-items:center;gap:5px;'
        f'background:{bg};color:{color};font-size:12px;font-weight:600;'
        f'padding:3px 10px;border-radius:980px;">'
        f'<span style="width:6px;height:6px;border-radius:50%;'
        f'background:{color};display:inline-block;"></span>{label}</span>'
    )


def info_card(content: str) -> str:
    """밝은 파란 정보 카드."""
    return (
        f'<div style="background:rgba(0,113,227,0.06);border-radius:12px;'
        f'padding:1rem 1.2rem;margin-bottom:1rem;'
        f'border:1px solid rgba(0,113,227,0.15);">'
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
        bg = "background-color: #ececf1" if shade.loc[row.name] else ""
        return [bg] * len(row)

    return df.style.apply(_row_style, axis=1)
