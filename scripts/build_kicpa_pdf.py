# -*- coding: utf-8 -*-
"""KICPA(Big 4) 면접용 프로젝트 소개 PDF 생성.

'법인세 세무조정 자동화(로컬 규칙엔진 + 검토보조)' 프로젝트를 도식 중심으로 설명한다.
matplotlib로 도식(파이프라인·아키텍처·규칙엔진·전수검토)을 렌더해 PNG로 저장하고,
fpdf2로 A4 다단 보고서에 임베드한다. 참고 산출물(세무AI_프로젝트소개_KICPA용.pdf)의
전문적 톤(네이비 헤더 + 틸 테이블 + 도식 임베드)을 따른다.

실행: python scripts/build_kicpa_pdf.py
출력: OUT_PATH (아래) — 데스크톱 참고자료 폴더에 저장.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.forms.fonts import korean_fonts  # noqa: E402
from fpdf import FPDF  # noqa: E402

# ── 팔레트 ────────────────────────────────────────────────────────────────
NAVY = "#1f2d3d"
TEAL = "#0f766e"
TEAL_D = (15, 118, 110)
INK = (34, 41, 51)
MUTE = (107, 118, 131)
LINE = (214, 220, 227)

BOX_BLUE = ("#eaf1f8", "#b9d1ea")
BOX_TEAL = ("#e6f2f0", "#9cc7c0")
BOX_YEL = ("#fdf5e6", "#e7cd8f")
BOX_RED = ("#fdecec", "#e6b0b0")
BOX_GRN = ("#eaf5ee", "#a9d3ba")
BOX_GRY = ("#f2f4f7", "#d6dce3")

_REG, _BOLD = korean_fonts()
_KFONT = fm.FontProperties(fname=_REG)
_KFONT_B = fm.FontProperties(fname=_BOLD)
plt.rcParams["axes.unicode_minus"] = False

SCRATCH = Path(os.environ.get("TEMP", "/tmp")) / "kicpa_figs"
SCRATCH.mkdir(parents=True, exist_ok=True)

# 출력 경로: 인자 > 환경변수(KICPA_PDF_OUT) > 데스크톱 기본값 (포터빌리티)
_DEFAULT_OUT = (
    r"C:\Users\hwshin\Desktop\법무법인 외, 타 회사 AI분석"
    r"\법인세세무조정자동화_프로젝트소개_KICPA용.pdf"
)
OUT_PATH = Path(
    (sys.argv[1] if len(sys.argv) > 1 else None)
    or os.environ.get("KICPA_PDF_OUT")
    or _DEFAULT_OUT
)


# ── 도식 헬퍼 ─────────────────────────────────────────────────────────────
def _box(ax, x, y, w, h, text, fc, ec, *, fs=10, bold=False, tc="#22303f"):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=1.2, edgecolor=ec, facecolor=fc, mutation_aspect=1))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontproperties=(_KFONT_B if bold else _KFONT), fontsize=fs, color=tc,
            wrap=True)


def _arrow(ax, x1, y1, x2, y2, color="#4a5a6a"):
    ax.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=14,
        linewidth=1.4, color=color, shrinkA=2, shrinkB=2))


def _fig(w=11, h=5.0):
    fig, ax = plt.subplots(figsize=(w, h), dpi=200)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    return fig, ax


def _save(fig, name):
    p = SCRATCH / name
    fig.savefig(p, bbox_inches="tight", pad_inches=0.05, facecolor="white")
    plt.close(fig)
    return str(p)


def fig_pipeline():
    fig, ax = _fig(11, 3.3)
    steps = [
        ("① 기본정보", "회사·중소기업·특정법인\nDART 연동·주주"),
        ("② 재무자료 업로드", "8종 파일 파싱\n표준화 파이프라인"),
        ("③ 수기 입력", "판단 자료만\n(금액은 자동집계)"),
        ("④ AI 검토 보조", "고위험 큐 요약\n검토메모 초안"),
        ("⑤ 계산·검토", "규칙엔진 산식·적수\n별지15호·드릴다운"),
        ("⑥ 출력", "검토패키지 PDF\n감사추적·.taxproj"),
    ]
    colors = [BOX_BLUE, BOX_BLUE, BOX_BLUE, BOX_YEL, BOX_TEAL, BOX_GRN]
    n = len(steps)
    w, gap = 13.5, 2.2
    total = n * w + (n - 1) * gap
    x0 = (100 - total) / 2
    y, h = 30, 40
    for i, ((t, d), c) in enumerate(zip(steps, colors)):
        x = x0 + i * (w + gap)
        _box(ax, x, y, w, h, t, c[0], c[1], fs=10.5, bold=True)
        ax.text(x + w / 2, y - 6, d, ha="center", va="top",
                fontproperties=_KFONT, fontsize=8, color="#55636f")
        if i < n - 1:
            _arrow(ax, x + w, y + h / 2, x + w + gap, y + h / 2)
    ax.text(50, 92, "6단계 자동화 흐름 — 회계사가 판단만 입력하면 규칙엔진이 세무조정을 확정",
            ha="center", fontproperties=_KFONT_B, fontsize=11.5, color=NAVY)
    ax.text(50, 12, "④ AI 검토보조는 '선택' — 세무조정 계산(⑤)은 LLM 없이 규칙엔진만으로 완결",
            ha="center", fontproperties=_KFONT, fontsize=8.5, color=TEAL)
    return _save(fig, "pipeline.png")


def fig_architecture():
    fig, ax = _fig(11, 5.2)
    # 입력
    _box(ax, 4, 74, 24, 16, "회계 프로그램 자료\n더존 Smart A · WEHAGO\n(재무제표·분개장·고정자산 등 8종)",
         *BOX_GRY, fs=9)
    # 표준화
    _box(ax, 38, 74, 24, 16, "표준화 파이프라인\nsrc/parsers/normalizer\n포맷스니핑·인코딩·헤더탐지·음수표기",
         *BOX_BLUE, fs=9, bold=True)
    # 규칙엔진 (핵심)
    _box(ax, 20, 44, 60, 20,
         "규칙 엔진  (핵심 · 결정론)\n분개장 1-pass 집계 · 적수 일별계산 · 손금불산입/익금산입 산식\n"
         "aggregator · jeoksu · tax_base — 4만 건도 1초 내 확정",
         *BOX_TEAL, fs=10.5, bold=True)
    # 법령 매핑 (좌)
    _box(ax, 4, 20, 26, 16,
         "법령 매핑  legal_basis\n모든 조정 = law.go.kr 조문\n(법령ID·조문번호 필수 등록)",
         *BOX_GRN, fs=9, bold=True)
    # 전수검토 (중)
    _box(ax, 37, 20, 26, 16,
         "전수 검토 coverage\n법§13~55의2 · 33항목\n검토필요는 정직하게 표시",
         *BOX_GRN, fs=9, bold=True)
    # 산출 (우)
    _box(ax, 70, 20, 26, 16,
         "산출 forms\n검토패키지 PDF·감사추적\n별지15호 매핑",
         *BOX_TEAL, fs=9, bold=True)
    # LLM 보조 (분리)
    _box(ax, 70, 44, 26, 20,
         "AI 검토 보조 (선택·분리)\n로컬 Ollama / 배포는 Claude API\n요약·메모만 — 금액 확정 안 함",
         *BOX_YEL, fs=8.6)
    # 화살표
    _arrow(ax, 28, 82, 38, 82)
    _arrow(ax, 50, 74, 50, 64)
    _arrow(ax, 40, 44, 30, 36)
    _arrow(ax, 50, 44, 50, 36)
    _arrow(ax, 60, 44, 78, 36)
    _arrow(ax, 80, 54, 80, 54)  # noop visual
    ax.add_patch(FancyArrowPatch((80, 54), (80, 64), arrowstyle="<->",
                 mutation_scale=12, linewidth=1.2, color="#b08a2a"))
    ax.text(83.5, 59, "선택 큐만", fontproperties=_KFONT, fontsize=7.5, color="#8a6d1f",
            rotation=90, va="center")
    ax.text(50, 96, "아키텍처 — 규칙엔진이 세무판단을 확정하고, AI는 보조만 (ADR-002 가드레일)",
            ha="center", fontproperties=_KFONT_B, fontsize=11.5, color=NAVY)
    return _save(fig, "architecture.png")


def fig_engine():
    fig, ax = _fig(11, 4.4)
    ax.text(50, 94, "규칙 엔진 — 분개장 1회 순회로 집계, 적수는 일별 재구성",
            ha="center", fontproperties=_KFONT_B, fontsize=11.5, color=NAVY)
    _box(ax, 3, 40, 20, 30, "분개장\n(전표·날짜·계정\n차·대변·증빙)", *BOX_GRY, fs=9)
    _box(ax, 30, 62, 30, 12, "1-pass 집계\n접대비·벌과금·법인세·평가손익·이자",
         *BOX_TEAL, fs=9, bold=True)
    _box(ax, 30, 44, 30, 12, "적수(積數) 일별 계산\nB/S 기초 + 분개 증감", *BOX_TEAL, fs=9, bold=True)
    _box(ax, 30, 26, 30, 12, "법령 산식 적용\n한도·시부인·소득처분", *BOX_TEAL, fs=9, bold=True)
    _box(ax, 67, 40, 30, 30,
         "확정 결과\n· 소득금액조정합계표\n· 별지15호 가산/차감\n· 과세표준→세액→최저한세\n· 분개 행 단위 근거",
         *BOX_GRN, fs=9, bold=True)
    for yy in (68, 50, 32):
        _arrow(ax, 23, 55, 30, yy)
        _arrow(ax, 60, yy, 67, 55)
    ax.text(50, 16,
            "핵심 원칙: 인정이자는 거래상대방별 계산(상대방 간 통산 금지, 영§88③) · "
            "적수는 잔액×365 근사가 아닌 실제 일별 계산",
            ha="center", fontproperties=_KFONT, fontsize=8.5, color=TEAL)
    return _save(fig, "engine.png")


def fig_coverage():
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.6), dpi=200,
                           gridspec_kw={"width_ratios": [1, 1.25]})
    # 도넛 — 자동계산 vs 검토필요
    a0 = ax[0]
    vals = [8, 25]
    labels = ["자동계산 8", "검토필요 25"]
    cols = ["#0f766e", "#e0b34a"]
    w, _, _ = a0.pie(vals, colors=cols, startangle=90,
                     wedgeprops=dict(width=0.42, edgecolor="white", linewidth=2),
                     autopct=lambda p: f"{int(round(p*33/100))}", pctdistance=0.79,
                     textprops=dict(fontproperties=_KFONT_B, fontsize=11, color="white"))
    a0.text(0, 0, "전수 검토\n33항목", ha="center", va="center",
            fontproperties=_KFONT_B, fontsize=11, color=NAVY)
    a0.legend(labels, loc="lower center", bbox_to_anchor=(0.5, -0.16), ncol=2,
              frameon=False, prop=_KFONT, fontsize=9)
    a0.set_title("법§13~55의2 전수 대조", fontproperties=_KFONT_B, fontsize=11, color=NAVY, pad=8)

    # 신뢰성 막대
    a1 = ax[1]
    a1.axis("off")
    items = [
        ("모든 조정 = 법령 매핑", "legal_basis 필수 등록"),
        ("금액·세액 확정 = 규칙엔진", "LLM은 확정 안 함 (ADR-002)"),
        ("감사추적 = 분개 행 단위", "'왜 자동조정 되었나' 판정사유"),
        ("실데이터 회귀", "티엘 WEHAGO 49,060 분개 일치"),
        ("품질", "pytest 회귀 299건 통과"),
    ]
    y = 0.9
    for t, d in items:
        a1.add_patch(plt.Rectangle((0.02, y - 0.055), 0.03, 0.03,
                     transform=a1.transAxes, color=TEAL))
        a1.text(0.09, y, t, transform=a1.transAxes, fontproperties=_KFONT_B,
                fontsize=10.5, color="#22303f", va="center")
        a1.text(0.09, y - 0.075, d, transform=a1.transAxes, fontproperties=_KFONT,
                fontsize=9, color="#67727e", va="center")
        y -= 0.20
    a1.set_title("신뢰성 설계 — 검증 가능성·재현성", fontproperties=_KFONT_B,
                 fontsize=11, color=NAVY, loc="left", pad=8)
    fig.subplots_adjust(wspace=0.05)
    return _save(fig, "coverage.png")


# ── PDF ───────────────────────────────────────────────────────────────────
class Doc(FPDF):
    def __init__(self):
        super().__init__(orientation="P", format="A4")
        self.set_auto_page_break(auto=True, margin=16)
        self.add_font("K", "", _REG)
        self.add_font("K", "B", _BOLD)

    def footer(self):
        self.set_y(-12)
        self.set_font("K", "", 7.5)
        self.set_text_color(*MUTE)
        self.cell(0, 6, "법인세 세무조정 자동화 · 프로젝트 소개(KICPA용)", align="L")
        self.cell(0, 6, f"{self.page_no()} / {{nb}}", align="R")


def h_section(pdf, title):
    pdf.ln(1)
    pdf.set_font("K", "B", 15)
    pdf.set_text_color(*TEAL_D)
    pdf.cell(0, 9, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*LINE)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(2.5)
    pdf.set_text_color(*INK)


def body(pdf, text, size=9.3, gap=4.9):
    pdf.set_font("K", "", size)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, gap, text, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)


def callout(pdf, title, text, border=TEAL_D):
    x0, y0 = pdf.get_x(), pdf.get_y()
    pdf.set_draw_color(*border)
    pdf.set_fill_color(246, 250, 249)
    pdf.set_font("K", "B", 9.6)
    pdf.set_text_color(*border)
    pdf.multi_cell(0, 5.4, f"◆ {title}", new_x="LMARGIN", new_y="NEXT",
                   fill=True, border="L")
    pdf.set_font("K", "", 8.8)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 4.7, text, new_x="LMARGIN", new_y="NEXT", fill=True, border="L")
    pdf.ln(2)


def table(pdf, headers, rows, widths, size=8.6):
    from fpdf.fonts import FontFace
    pdf.set_font("K", "", size)
    pdf.set_text_color(*INK)
    with pdf.table(
        col_widths=widths, text_align="LEFT",
        borders_layout="HORIZONTAL_LINES", line_height=size * 0.62, padding=1.6,
        headings_style=FontFace(family="K", emphasis="BOLD", color=255,
                                fill_color=TEAL_D),
    ) as t:
        hr = t.row()
        for h in headers:
            hr.cell(h)
        for r in rows:
            rr = t.row()
            for c in r:
                rr.cell(str(c))
    pdf.ln(2)


def img(pdf, path, w=None):
    w = w or (pdf.w - pdf.l_margin - pdf.r_margin)
    pdf.image(path, w=w)
    pdf.ln(2)


def build():
    p_pipeline = fig_pipeline()
    p_arch = fig_architecture()
    p_engine = fig_engine()
    p_cov = fig_coverage()

    pdf = Doc()
    pdf.alias_nb_pages()

    # ── 1. 표지 ──────────────────────────────────────────────
    pdf.add_page()
    pdf.set_fill_color(*[int(NAVY[i:i+2], 16) for i in (1, 3, 5)])
    pdf.rect(0, 0, pdf.w, 52, style="F")
    pdf.set_xy(pdf.l_margin, 15)
    pdf.set_font("K", "B", 22)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 12, "법인세 세무조정 자동화 시스템", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(pdf.l_margin)
    pdf.set_font("K", "", 11)
    pdf.set_text_color(200, 214, 224)
    pdf.cell(0, 8, "회계자료를 규칙엔진으로 자동 세무조정 — 모든 조정은 국가법령정보 기반, 감사추적은 분개 행 단위",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(14)
    pdf.set_text_color(*INK)

    callout(
        pdf, "한 문장 요약",
        "더존 Smart A·WEHAGO 재무자료를 파싱해 분개장 1-pass 집계 + 법령 산식 규칙엔진으로 "
        "세무조정 금액·과세표준·세액을 확정하고, 로컬 LLM(배포 데모는 Claude API)이 애매한 분개의 "
        "검토를 보조하는 로컬 AI 시스템입니다. AI는 세무판단을 확정하지 않으며 — 초안·근거·검토포인트 "
        "생성이 목적입니다. 최종 판단·서명은 회계사가 합니다.")

    table(
        pdf, ["구분", "내용"],
        [
            ["무엇을", "회계자료 → 세무조정 자동계산 + 검토패키지(PDF·감사추적·별지) 산출"],
            ["누구를 위해", "법인세 세무조정 용역 회계사·세무사 (검토 보조 도구)"],
            ["핵심 엔진", "분개장 1-pass 집계 · 적수 일별계산 · 손금불산입/익금산입 법령 산식 (결정론)"],
            ["왜 신뢰 가능", "모든 조정 = law.go.kr 조문 매핑 · 분개 행 단위 감사추적 · 실데이터 회귀 검증"],
            ["기술 스택", "Python·Streamlit(로컬) · pandas/openpyxl/lxml · 규칙엔진 · Ollama/Claude(보조)"],
        ],
        widths=[26, 114])

    callout(
        pdf, "회계사가 5분 안에 확인할 것",
        "① 세무조정 금액·세액을 AI가 아니라 규칙엔진이 확정하는가  "
        "② 모든 조정에 법령(조문) 근거가 붙는가  ③ 계산 결과가 분개 행까지 역추적되는가  "
        "④ 커버하지 못한 항목을 '검토필요'로 정직하게 표시하는가",
        border=(180, 120, 20))

    pdf.ln(1)
    pdf.set_font("K", "", 7.6)
    pdf.set_text_color(*MUTE)
    pdf.multi_cell(0, 4,
                   "※ 본 문서의 도식은 시스템 설계 구조를 그대로 반영했습니다. 수치 예시(한빛정밀㈜)는 "
                   "검토용 가상 데이터이며 실제 회사와 무관합니다.",
                   new_x="LMARGIN", new_y="NEXT")

    # ── 2. 자동화 흐름 ───────────────────────────────────────
    pdf.add_page()
    h_section(pdf, "1. 전체 자동화 흐름 — 6단계")
    body(pdf,
         "회계사는 '금액'이 아니라 '판단'만 입력합니다. 금액은 분개장에서 자동 집계되고, "
         "규칙엔진이 법령 산식으로 세무조정을 확정합니다. AI 검토보조(④)는 선택 단계로, "
         "이를 건너뛰어도 세무조정 계산(⑤)은 규칙엔진만으로 완결됩니다.")
    img(pdf, p_pipeline)
    body(pdf,
         "입력 자료(8종)는 항상 깨끗하지 않습니다 — 확장자를 위장한 HTML형 .xls, 인코딩, 제목행, "
         "음수 표기(△·괄호·전각), 합계행, 회사별 계정명 차이를 표준화 파이프라인이 단일 관문에서 흡수합니다. "
         "원본 행번호는 감사추적용으로 보존됩니다.")

    # ── 3. 아키텍처 ──────────────────────────────────────────
    pdf.add_page()
    h_section(pdf, "2. 아키텍처 — 규칙엔진이 확정, AI는 보조")
    img(pdf, p_arch)
    callout(
        pdf, "왜 이 구조가 회계법인에 적합한가",
        "세무조정 금액·한도·세액 계산은 규칙엔진만 담당하고, LLM은 대량 분개 판단·금액 확정에 "
        "일절 관여하지 않습니다(ADR-002). AI는 회계사가 선택한 소수 고위험 거래의 요약·검토메모 초안만 "
        "생성하며, 결과는 계산에 반영되지 않고 감사추적에 보존됩니다. 즉 '환각이 금액을 바꾸는' 경로가 "
        "구조적으로 차단됩니다.")

    # ── 4. 규칙엔진 ──────────────────────────────────────────
    pdf.add_page()
    h_section(pdf, "3. 규칙 엔진 — 결정론적 세무조정 계산")
    img(pdf, p_engine)
    table(
        pdf, ["항목", "계산 기준", "법령"],
        [
            ["감가상각 시부인", "정액·정률 산식 독립계산(월할·비망가액 특례), 대장은 대사용만", "법§23, 영§26~28"],
            ["기업업무추진비", "기본한도+수입금액 적용률, 특수관계인 매출 10%, 특정법인 ×50%, 증빙불비", "법§25"],
            ["지급이자 4호", "(이자−1·3호) × [업무무관+가지급금 적수 ÷ 차입금 적수]", "법§28, 영§53"],
            ["인정이자", "거래상대방별 적수×이자율 − 약정이자 (상대방 간 통산 금지)", "법§52, 영§88③"],
            ["간주임대료", "주업·차입금 요건 충족 시 (보증금−건설비)적수×이자율−금융수익", "조특법§138"],
            ["과세표준·세액", "각사업연도소득−이월결손금 → 세율(개시일) → 최저한세 → 차감납부", "법§13~55"],
        ],
        widths=[30, 82, 28], size=8.2)

    # ── 5. 신뢰성·전수검토 ───────────────────────────────────
    pdf.add_page()
    h_section(pdf, "4. 신뢰성 — 법령 근거·전수 검토·감사추적")
    img(pdf, p_cov)
    body(pdf,
         "법인세법 §13~55의2 전 조문 기준 33개 조정항목을 분개장과 대조해 자동계산/검토필요/해당없음으로 "
         "표시합니다. 자동으로 계산하지 못한 25개 항목(의제배당·자본거래·합병분할·토지등 양도 등)은 "
         "숨기지 않고 '검토필요'로 정직하게 드러내며, 각 항목에 근거법령과 검토포인트 해석을 함께 붙입니다.")
    callout(
        pdf, "검증 가능성 · 재현성",
        "회사 재무수치는 업로드 원본, 세무조정은 법령 조문으로 추적 가능합니다. 계산 항목을 선택하면 "
        "'왜 자동조정 되었나'(판정사유) + 적용 산식 + 근거 분개 + CSV까지 드릴다운됩니다. 실데이터 회귀"
        "(티엘 WEHAGO 분개 49,060건 핵심수치 일치)와 pytest 회귀 299건으로 품질을 보증합니다.")

    # ── 6. 데모 산출 (한빛정밀) ──────────────────────────────
    pdf.add_page()
    h_section(pdf, "5. 데모 산출 예시 — 한빛정밀㈜ (가상)")
    body(pdf,
         "라이브 배포 데모에서 면접관이 파일 업로드 없이 '데모 데이터 불러오기'만 누르면, 아래 가상 회사의 "
         "분개장이 규칙엔진을 통과해 세무조정 후보와 근거가 즉시 생성됩니다. (전부 가상 데이터)")
    table(
        pdf, ["항목", "자동 집계·판정", "세무조정 성격"],
        [
            ["수입금액(매출)", "3,000,000,000원", "접대비 한도 산정 기준"],
            ["기업업무추진비", "54,000,000원 집계 · 증빙불비 4,500,000원", "손금불산입(한도초과·증빙불비)"],
            ["벌과금·과태료", "3,000,000원", "손금불산입 전액 (법§21)"],
            ["법인세비용", "42,000,000원", "손금불산입 전액"],
            ["감가상각비", "정률법 2개 자산 회사계상 90,000,000원", "세무한도 초과분 시부인(법§23)"],
            ["수입배당금", "30,000,000원", "익금불산입 검토(법§18의2)"],
            ["당기순이익", "250,000,000원", "→ 각사업연도소득·과세표준·세액 자동 산출"],
        ],
        widths=[34, 66, 40], size=8.2)
    callout(
        pdf, "정직한 한계",
        "본 시스템은 '검토 보조'이지 '판단 대체'가 아닙니다. 세무조정 금액은 법령 산식으로 확정하되, "
        "소득처분(귀속자)·개별 사실관계·최신 예규는 회계사 확인이 필요합니다. 라이브 데모는 반드시 "
        "가상 데이터만 사용하며, 실제 고객 세무자료는 로컬 실행(외부 미전송)을 전제로 합니다.",
        border=(180, 60, 60))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT_PATH))
    print("saved:", OUT_PATH)


if __name__ == "__main__":
    build()
