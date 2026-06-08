"""세무조정 검토패키지 PDF 생성 — 인쇄 검토용 종합 보고서.

구성 (리뷰 흐름 순서):
  ① 표지·핵심 세액 지표  ② 소득금액조정합계표 (조정구분·소득처분·검토메모)
  ③ 조정 항목별 계산 근거 (산식·판정 사유)  ④ 전수 검토 체크리스트 (위험도)
  ⑤ 자료요청 리스트  ⑥ 전년 대비 증감분석  ⑦ 고객 설명 메모

한글: Windows 맑은고딕(malgun.ttf) 임베드. 메모리에서 생성 — 임시파일 없음.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fpdf import FPDF

from src.forms.summary_rows import adjustment_rows, adj_type

_FONT_REG = Path(r"C:\Windows\Fonts\malgun.ttf")
_FONT_BOLD = Path(r"C:\Windows\Fonts\malgunbd.ttf")

_GRAY = (236, 236, 241)
_HEAD = (29, 29, 31)

# 항목별 고객 행동 안내 (결정론적 템플릿 — LLM 불필요, 환각 위험 없음)
ACTION_HINTS = {
    "업무용승용차": "운행기록부 작성 및 업무전용 자동차보험 가입을 유지하시면 손금 인정 범위가 늘어납니다.",
    "기업업무추진비 증빙불비": "건당 3만원 초과 지출은 법인카드·세금계산서 등 적격증빙 수취가 필요합니다.",
    "기업업무추진비 한도초과": "한도는 법인 규모·수입금액으로 정해지므로 지출 계획 수립 시 참고하시기 바랍니다.",
    "가지급금": "대표자·특수관계인 대여금은 인정이자 익금산입과 지급이자 손금불산입이 함께 발생하므로 조기 회수를 권장합니다.",
    "벌과금": "벌과금·과태료·가산세는 세법상 손금으로 인정되지 않습니다.",
    "감가상각": "세법상 상각한도를 초과한 부분은 당기에 부인되고 향후 한도 미달 연도에 추인됩니다.",
    "퇴직급여충당금": "장부상 퇴직급여충당금은 세법상 한도(0%)로 전액 부인되며, 퇴직연금 납입분은 별도로 손금산입이 가능합니다.",
    "대손충당금": "세법상 한도(채권의 1% 또는 대손실적률)를 초과한 설정액은 부인됩니다.",
    "간주임대료": "임대보증금에 대한 간주익금은 보증금을 금융자산으로 운용해 이자수익이 발생하면 그만큼 차감됩니다.",
    "채권자불분명": "채권자를 확인할 수 없는 차입금 이자는 전액 손금불산입되므로 차입처 증빙을 보완해 주세요.",
}


def build_client_memo(calc_details: dict, company_name: str, fy_year: int) -> str:
    """조정 결과 → 고객 설명 문구 초안 (화면·PDF 공용)."""
    lines = [
        f"[{company_name or '회사'}] {fy_year}년 귀속 법인세 세무조정 주요 내용 안내",
        "",
    ]
    for name, d in (calc_details or {}).items():
        if name.startswith("(참고)") or not d.get("금액"):
            continue
        hint = next((h for k, h in ACTION_HINTS.items() if k in name), "")
        lines.append(
            f"· {name}: {d['금액']:,}원 ({d.get('법령', '')})"
            + (f"\n  → {hint}" if hint else "")
        )
    lines.append("")
    lines.append("※ 본 안내는 검토 초안이며, 최종 신고 내용은 담당 회계사 확인 후 확정됩니다.")
    return "\n".join(lines)


class _ReviewPDF(FPDF):
    """페이지 머리글·바닥글 (회사명 · '검토 초안' 워터마크 문구 · 쪽번호)."""

    def __init__(self, company: str, fy_label: str):
        super().__init__(orientation="P", format="A4")
        self._company = company
        self._fy = fy_label
        self.set_auto_page_break(auto=True, margin=18)

    def header(self):
        self.set_font("Malgun", "", 7.5)
        self.set_text_color(134, 134, 139)
        self.cell(0, 5, f"{self._company} · {self._fy} 세무조정 검토패키지", align="L")
        self.cell(0, 5, "검토 초안 — 회계사 확인 전", align="R",
                  new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(210, 210, 215)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(3)
        self.set_text_color(*_HEAD)

    def footer(self):
        self.set_y(-14)
        self.set_font("Malgun", "", 7.5)
        self.set_text_color(134, 134, 139)
        self.cell(0, 6, f"- {self.page_no()} / {{nb}} -", align="C")


def _h2(pdf: FPDF, title: str) -> None:
    pdf.ln(2)
    pdf.set_font("Malgun", "B", 11)
    pdf.set_text_color(*_HEAD)
    pdf.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)


def _body_font(pdf: FPDF, size: float = 8.5, bold: bool = False) -> None:
    pdf.set_font("Malgun", "B" if bold else "", size)
    pdf.set_text_color(*_HEAD)


def _simple_table(pdf: FPDF, headers: list[str], rows: list[list[str]],
                  widths: list[int], size: float = 8.0) -> None:
    """줄바꿈 지원 표 — 헤더 회색, 본문 교대 음영."""
    from fpdf.fonts import FontFace

    _body_font(pdf, size)
    with pdf.table(
        col_widths=widths,
        text_align="LEFT",
        borders_layout="HORIZONTAL_LINES",
        line_height=size * 0.62,
        padding=1.2,
        headings_style=FontFace(family="Malgun", emphasis="BOLD", fill_color=_GRAY),
    ) as table:
        head = table.row()
        for h in headers:
            head.cell(h)
        for r in rows:
            row = table.row()
            for c in r:
                row.cell(str(c))


def build_review_pdf(
    *,
    company_name: str,
    business_no: str,
    fy_start, fy_end,
    result,                       # TaxAdjustmentResult
    calc_details: dict,           # {항목: {금액, 법령, 산식[], 사유}}
    coverage: list,               # CoverageResult 리스트
    requests: list,               # DataRequest 리스트
    yoy_df,                       # pd.DataFrame | None
    yoy_warn: list[str],
    review_memos: dict[str, str],
    client_memo: str,
    risk_fn,                      # assess_risk
    law_check_label: str = "",
) -> bytes:
    fy_label = f"{fy_start} ~ {fy_end}"
    pdf = _ReviewPDF(company_name or "(회사명 미입력)", fy_label)
    pdf.add_font("Malgun", "", str(_FONT_REG))
    pdf.add_font("Malgun", "B", str(_FONT_BOLD))
    pdf.alias_nb_pages()
    pdf.add_page()

    # ── ① 표지 + 핵심 세액 지표 ──────────────────────────────────────────────
    pdf.set_font("Malgun", "B", 16)
    pdf.cell(0, 10, "법인세 세무조정 검토패키지", new_x="LMARGIN", new_y="NEXT")
    _body_font(pdf, 9)
    pdf.cell(0, 6, f"회사명: {company_name}    사업자등록번호: {business_no}",
             new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"적용 사업연도: {fy_label}    법령 기준일: {fy_end} (사업연도 종료일 시행, law.go.kr)",
             new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6,
             f"생성: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
             + (f"    마지막 법령 확인: {law_check_label}" if law_check_label else ""),
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    _h2(pdf, "1. 핵심 세액 지표")
    _simple_table(
        pdf,
        ["당기순이익", "가산조정", "차감조정", "각사업연도소득", "과세표준", "산출세액", "차감납부세액"],
        [[f"{result.net_income:,}", f"{result.total_add_back:,}", f"{result.total_deduct:,}",
          f"{result.business_income:,}", f"{result.tax_base:,}", f"{result.gross_tax:,}",
          f"{result.final_tax_due:,}"]],
        widths=[15, 14, 14, 16, 15, 13, 13],
    )

    # ── ② 소득금액조정합계표 ─────────────────────────────────────────────────
    add_items, deduct_items = adjustment_rows(result)
    _h2(pdf, f"2. 소득금액조정합계표 — 가산 {result.total_add_back:,}원 / 차감 {result.total_deduct:,}원")
    rows = []
    for t, k, v, b, d in add_items + deduct_items:
        if not v:
            continue
        rows.append([t, k, f"{v:,}", b, d, adj_type(k), review_memos.get(k, "")])
    if rows:
        _simple_table(
            pdf, ["구분", "항목", "금액(원)", "근거", "소득처분(후보)", "조정구분", "검토메모"],
            rows, widths=[11, 24, 14, 13, 14, 10, 24],
        )
        _body_font(pdf, 7.5)
        pdf.set_text_color(134, 134, 139)
        pdf.multi_cell(0, 4,
                       "※ 소득처분은 후보입니다 — 귀속자(대표자·주주·임원)에 따라 상여·배당·기타사외유출이 달라질 수 "
                       "있습니다. 결산조정 항목은 장부 계상 여부가 손금 인정의 전제입니다.",
                       new_x="LMARGIN", new_y="NEXT")
    else:
        _body_font(pdf)
        pdf.cell(0, 6, "발생한 조정 항목이 없습니다.", new_x="LMARGIN", new_y="NEXT")

    # ── ③ 조정 항목별 계산 근거 ──────────────────────────────────────────────
    pdf.add_page()
    _h2(pdf, "3. 조정 항목별 계산 근거 (산식·판정 사유)")
    for name, d in (calc_details or {}).items():
        if name.startswith("(참고)"):
            continue
        _body_font(pdf, 9, bold=True)
        pdf.multi_cell(0, 5.5, f"■ {name} — {d.get('금액', 0):,}원  [{d.get('법령', '')}]",
                       new_x="LMARGIN", new_y="NEXT")
        if d.get("사유"):
            _body_font(pdf, 8)
            pdf.set_text_color(0, 90, 180)
            pdf.multi_cell(0, 4.5, f"  사유: {d['사유']}", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*_HEAD)
        _body_font(pdf, 8)
        for f_line in d.get("산식", []):
            if f_line:
                pdf.multi_cell(0, 4.5, f"  · {f_line}", new_x="LMARGIN", new_y="NEXT")
        n_lines = len(d.get("lines") or [])
        if n_lines:
            pdf.set_text_color(134, 134, 139)
            pdf.multi_cell(0, 4.5, f"  근거 분개 {n_lines:,}건 — 앱 5단계 드릴다운·CSV 참조",
                           new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*_HEAD)
        pdf.ln(1.5)

    # ── ④ 전수 검토 체크리스트 ───────────────────────────────────────────────
    pdf.add_page()
    n_rev = sum(1 for c in coverage if c.status == "검토필요")
    _h2(pdf, f"4. 세무조정 전수 검토 체크리스트 ({len(coverage)}항목 — 검토필요 {n_rev})")
    cov_rows = [
        [c.status,
         (risk_fn(c.item, c.amount_hint, c.status) if c.status != "해당없음" else ""),
         c.item, c.legal_basis,
         f"{c.amount_hint:,}" if c.amount_hint else "", c.detail]
        for c in sorted(coverage, key=lambda x: ({"검토필요": 0, "자동계산": 1, "해당없음": 2}[x.status],
                                                 -x.amount_hint))
    ]
    if cov_rows:
        _simple_table(pdf, ["상태", "위험도", "조정 항목", "법령", "관련 금액", "내역/필요 자료"],
                      cov_rows, widths=[9, 9, 20, 12, 13, 37], size=7.5)

    # ── ⑤ 자료요청 리스트 ────────────────────────────────────────────────────
    pdf.add_page()
    _h2(pdf, f"5. 고객 자료요청 리스트 ({len(requests)}건)")
    if requests:
        _simple_table(
            pdf, ["위험도", "요청 자료", "사유", "관련 세무조정"],
            [[q.risk, q.item, q.reason, q.related]
             for q in sorted(requests, key=lambda x: {"High": 0, "Medium": 1, "Low": 2}[x.risk])],
            widths=[9, 26, 40, 25], size=7.5,
        )
    else:
        _body_font(pdf)
        pdf.cell(0, 6, "현재 상태에서 추가로 요청할 자료가 없습니다.", new_x="LMARGIN", new_y="NEXT")

    # ── ⑥ 전년 대비 증감분석 ─────────────────────────────────────────────────
    _h2(pdf, "6. 전년 대비 증감분석")
    if yoy_df is None or len(yoy_df) == 0:
        _body_font(pdf)
        pdf.cell(0, 6, "전기 비교 데이터 없음 (손익계산서가 당기 단일 열 양식).",
                 new_x="LMARGIN", new_y="NEXT")
    else:
        for w in yoy_warn:
            _body_font(pdf, 8, bold=True)
            pdf.set_text_color(200, 80, 0)
            pdf.multi_cell(0, 4.8, w, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*_HEAD)
        top = yoy_df.head(25)
        _simple_table(
            pdf, ["계정명", "당기", "전기", "증감", "증감률(%)"],
            [[r["계정명"], f"{r['당기']:,}", f"{r['전기']:,}", f"{r['증감']:,}",
              ("" if r["증감률(%)"] is None else f"{r['증감률(%)']}")]
             for _, r in top.iterrows()],
            widths=[30, 18, 18, 18, 12], size=7.5,
        )
        if len(yoy_df) > 25:
            _body_font(pdf, 7.5)
            pdf.set_text_color(134, 134, 139)
            pdf.cell(0, 5, f"※ 증감액 상위 25개만 표시 (전체 {len(yoy_df)}개는 앱 CSV 참조)",
                     new_x="LMARGIN", new_y="NEXT")

    # ── ⑦ 고객 설명 메모 ─────────────────────────────────────────────────────
    if client_memo:
        pdf.add_page()
        _h2(pdf, "7. 고객 설명용 메모 (초안)")
        _body_font(pdf, 8.5)
        pdf.multi_cell(0, 5, client_memo, new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
