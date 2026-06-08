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
from src.forms.reserve_status import build_reserve_status, reserve_totals
from src.forms.donation_status import build_donation_status

_FONT_REG = Path(r"C:\Windows\Fonts\malgun.ttf")
_FONT_BOLD = Path(r"C:\Windows\Fonts\malgunbd.ttf")

_GRAY = (236, 236, 241)
_HEAD = (29, 29, 31)

# 세목별 근거분개 표에 인쇄할 최대 분개 수 (초과분은 앱 CSV 안내) — PDF 분량 관리
# 500건 이내면 종이 검토용으로 전부 인쇄, 초과 시 금액 상위 500건만 표시
JOURNAL_LINE_CAP = 500

# ④ 전수 검토 체크리스트의 '검토필요' 항목에 붙이는 근거분개 최대 수 (금액 큰 순)
CHECKLIST_JOURNAL_CAP = 100


def book_tax_lines(detail: dict) -> list[str]:
    """calc_details 한 항목 → Book/Tax/계산근거/T·A(소득처분) 표시 줄 (화면·PDF 공용).

    detail: {금액, book, tax, tax_basis, 처분, ...}.
    book/tax가 None이면 분개 직접집계가 아닌 산식·수기 항목으로 '—' 표시.
    """
    book = detail.get("book")
    tax = detail.get("tax")
    disp = detail.get("처분") or "검토필요 (귀속자 미정)"
    out = [
        f"Book (장부상 금액): {book:,}원" if book is not None else "Book (장부상 금액): —",
        f"Tax (세무상 금액): {tax:,}원" if tax is not None else "Tax (세무상 금액): —",
    ]
    if detail.get("tax_basis"):
        out.append(f"세무상 금액 계산근거: {detail['tax_basis']}")
    out.append(f"T/A (세무조정): {detail.get('금액', 0):,}원 · 소득처분 {disp}")
    return out


def _journal_amount(ln) -> int:
    """분개 라인의 표시 금액 — 차변·대변 중 큰 절대값 (정렬 기준)."""
    return max(abs(getattr(ln, "debit", 0) or 0), abs(getattr(ln, "credit", 0) or 0))


def _journal_rows_for_pdf(lines: list, cap: int = JOURNAL_LINE_CAP) -> list[list[str]]:
    """근거분개 JournalLine 리스트 → PDF 표 행 (날짜·계정·적요·거래처·차변·대변).

    분개는 금액(차변·대변 중 큰 값) 내림차순으로 정렬한 뒤 cap건까지 인쇄한다 —
    검토자가 종이로 볼 때 금액이 큰 분개부터 확인할 수 있도록 한다.
    """
    rows = []
    sorted_lines = sorted(lines, key=_journal_amount, reverse=True)
    for ln in sorted_lines[:cap]:
        rows.append([
            str(getattr(ln, "date", "")),
            (getattr(ln, "account_name", "") or "")[:16],
            (getattr(ln, "description", "") or "")[:26],
            (getattr(ln, "counterparty_name", "") or "")[:16],
            f"{ln.debit:,}" if getattr(ln, "debit", 0) else "",
            f"{ln.credit:,}" if getattr(ln, "credit", 0) else "",
        ])
    return rows

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
    prior_reserves: list[dict] | None = None,
    depr_denial_end: int = 0,
    bad_debt_method: str = "총액법",
    reserve_decrease_overrides: dict[str, int] | None = None,
    reserve_manual_rows: list[dict] | None = None,
    disposition_choices: dict | None = None,
    consulting_topics: list | None = None,
    donation_status: dict | None = None,
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
    add_items, deduct_items = adjustment_rows(result, disposition_choices)
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

    # ── ②-2 자본금과적립금조정명세서(을) — 유보 잔액 명세 ──────────────────────
    _reserve_rows = build_reserve_status(
        prior_reserves or [], result, depr_denial_end, bad_debt_method,
        decrease_overrides=reserve_decrease_overrides, manual_rows=reserve_manual_rows)
    if _reserve_rows:
        _rt = reserve_totals(_reserve_rows)
        _h2(pdf, f"2-2. 자본금과적립금조정명세서(을) — 순유보 기말 {_rt['순유보_기말']:,}원")
        _res_rows = [
            [x["과목"], f"{x['기초']:,}", f"{x['증가']:,}", f"{x['감소']:,}",
             f"{x['기말']:,}", x["처분"], "추인확인" if x["검토"] else ""]
            for x in _reserve_rows
        ]
        _simple_table(
            pdf, ["과목", "기초", "당기증가", "당기감소", "기말", "처분", "검토"],
            _res_rows, widths=[28, 15, 15, 15, 15, 9, 13],
        )
        if any(x["검토"] for x in _reserve_rows):
            _body_font(pdf, 7.5)
            pdf.set_text_color(134, 134, 139)
            pdf.multi_cell(0, 4,
                           "※ '추인확인' 항목은 전기 유보가 있으나 당기 추인(감소)이 자동 반영되지 않았습니다 — "
                           "환입·추인 여부를 확인해 당기 감소를 보정하세요.",
                           new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*_HEAD)

    # ── ②-3 기부금조정명세서 (별지 제21호서식) ─────────────────────────────────
    _dstat = build_donation_status(donation_status)
    if _dstat:
        _h2(pdf, "2-3. 기부금조정명세서 (별지 제21호서식)")
        _body_font(pdf, 8)
        pdf.multi_cell(
            0, 4.6,
            f"기준소득금액 {_dstat['base_income']:,}원 - 이월결손금 공제 "
            f"{_dstat['loss_deduction']:,}원 = 한도기준 {_dstat['limit_base']:,}원",
            new_x="LMARGIN", new_y="NEXT")
        # ① 한도계산
        _body_font(pdf, 8, bold=True)
        pdf.multi_cell(0, 4.8, "  ① 한도 계산", new_x="LMARGIN", new_y="NEXT")
        _simple_table(
            pdf, ["구분", "지출액", "이월 우선공제", "손금산입한도", "한도율", "당기 한도초과"],
            [[c["구분"], f"{c['지출액']:,}", f"{c['이월 우선공제']:,}",
              f"{c['손금산입한도']:,}", c["한도율"], f"{c['당기 한도초과']:,}"]
             for c in _dstat["limit_calc"]],
            widths=[24, 22, 24, 24, 12, 24], size=7.5,
        )
        # ② 발생연도별 이월명세 (소멸 명시)
        if _dstat["carryforward_schedule"]:
            _body_font(pdf, 8, bold=True)
            pdf.multi_cell(0, 4.8, "  ② 발생연도별 이월명세 (법§24⑤⑥)", new_x="LMARGIN", new_y="NEXT")
            _simple_table(
                pdf, ["발생연도", "구분", "전기말 이월", "당기 공제", "당기 소멸", "차기 이월", "발생구분"],
                [[str(r["year"]), r["type"], f"{r['opening']:,}", f"{r['used']:,}",
                  f"{r['expired']:,}", f"{r['carryover']:,}", r["발생구분"]]
                 for r in _dstat["carryforward_schedule"]],
                widths=[16, 12, 22, 20, 18, 20, 16], size=7.0,
            )
            _body_font(pdf, 7.5)
            pdf.set_text_color(134, 134, 139)
            pdf.multi_cell(
                0, 4.0,
                f"  이월 당기 손금산입 {_dstat['carryforward_deduction']:,}원 · "
                f"당기 소멸 {_dstat['expired_total']:,}원 · 차기 이월 {_dstat['next_carryforward_total']:,}원 — "
                + _dstat["balance_note"],
                new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*_HEAD)

    # ── ③ 세목별 세무조정 (Book / Tax / 세무조정·소득처분 + 근거분개) ────────────
    pdf.add_page()
    _h2(pdf, "3. 세목별 세무조정 — Book / Tax / 세무상 금액 계산근거 / T·A·소득처분 + 근거분개")
    _items = [(n, d) for n, d in (calc_details or {}).items() if not n.startswith("(참고)")]
    for _idx, (name, d) in enumerate(_items):
        _body_font(pdf, 9.5, bold=True)
        pdf.multi_cell(0, 5.5, f"■ {name}  [{d.get('법령', '')}]",
                       new_x="LMARGIN", new_y="NEXT")
        # 판정 사유 (왜 자동조정 되었나)
        if d.get("사유"):
            _body_font(pdf, 8)
            pdf.set_text_color(0, 90, 180)
            pdf.multi_cell(0, 4.5, f"  사유: {d['사유']}", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*_HEAD)
        # Book / Tax / 세무상 금액 계산근거 / T·A · 소득처분
        _body_font(pdf, 8.5)
        for _l in book_tax_lines(d):
            pdf.multi_cell(0, 4.8, f"  {_l}", new_x="LMARGIN", new_y="NEXT")
        # 세무상 금액 산정 상세 (산식)
        _detail_formula = [f for f in (d.get("산식") or []) if f]
        if _detail_formula:
            _body_font(pdf, 7.5)
            pdf.set_text_color(110, 110, 115)
            for f_line in _detail_formula:
                pdf.multi_cell(0, 4.2, f"     - {f_line}", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*_HEAD)
        # 근거분개 — 실제 분개 내역
        _lines = d.get("lines") or []
        if _lines:
            _body_font(pdf, 8, bold=True)
            pdf.multi_cell(0, 4.8, f"  근거분개 ({len(_lines):,}건):",
                           new_x="LMARGIN", new_y="NEXT")
            _simple_table(
                pdf, ["날짜", "계정과목", "적요", "거래처", "차변", "대변"],
                _journal_rows_for_pdf(_lines), widths=[14, 22, 30, 20, 17, 17], size=7.0,
            )
            if len(_lines) > JOURNAL_LINE_CAP:
                _body_font(pdf, 7.0)
                pdf.set_text_color(134, 134, 139)
                pdf.multi_cell(
                    0, 4.0,
                    f"  ※ 전체 {len(_lines):,}건 중 금액 상위 {JOURNAL_LINE_CAP}건만 표시 — "
                    "전체 분개는 앱 5단계 'CSV 다운로드' 참조",
                    new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(*_HEAD)
        else:
            _body_font(pdf, 7.5)
            pdf.set_text_color(134, 134, 139)
            pdf.multi_cell(
                0, 4.2,
                "  근거분개: 분개장 직접 집계가 아닌 수기 입력·산식 기반 항목 "
                "(근거는 앱 3단계 입력 화면 참조)",
                new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*_HEAD)
        # 세목 구분선 (다음 세목)
        if _idx < len(_items) - 1:
            pdf.ln(1.5)
            pdf.set_draw_color(205, 205, 212)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(2.5)
        else:
            pdf.ln(2)

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

    # 4-2. '검토필요' 항목별 근거법령·검토포인트 (law.go.kr 원문 검증 — 4-1 분개보다 앞: 법령 이해→분개 확인)
    _law_items = [
        c for c in sorted(coverage, key=lambda x: -x.amount_hint)
        if c.status == "검토필요" and getattr(c, "interpretation", "")
    ]
    if _law_items:
        pdf.ln(2)
        _body_font(pdf, 8.5, bold=True)
        pdf.set_text_color(*_HEAD)
        pdf.multi_cell(0, 5, "4-2. 검토필요 항목 근거법령·검토포인트", new_x="LMARGIN", new_y="NEXT")
        _body_font(pdf, 7.5)
        pdf.set_text_color(134, 134, 139)
        pdf.multi_cell(
            0, 4,
            "※ 각 검토필요 항목의 근거 조문과 검토 포인트입니다(국가법령정보 원문 기준). "
            "적용·확정은 회계사 판단이며, 조문 원문은 앱 5단계에서 조회할 수 있습니다.",
            new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*_HEAD)
        for c in _law_items:
            _body_font(pdf, 8, bold=True)
            pdf.multi_cell(0, 4.8, f"■ {c.item}  [{c.legal_basis}]", new_x="LMARGIN", new_y="NEXT")
            _body_font(pdf, 7.5)
            pdf.set_text_color(70, 70, 75)
            pdf.multi_cell(0, 4.3, f"  검토포인트: {c.interpretation}", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*_HEAD)
            pdf.ln(0.8)

    # 4-1. '검토필요' 항목별 근거분개 — 회계사가 직접 들여다볼 분개를 첨부 (금액 큰 순 100건)
    _review_items = [
        c for c in sorted(coverage, key=lambda x: -x.amount_hint)
        if c.status == "검토필요" and getattr(c, "lines", None)
    ]
    if _review_items:
        pdf.ln(2)
        _body_font(pdf, 8.5, bold=True)
        pdf.set_text_color(*_HEAD)
        pdf.multi_cell(0, 5, "4-1. 검토필요 항목 근거분개 (금액 큰 순)", new_x="LMARGIN", new_y="NEXT")
        _body_font(pdf, 7.5)
        pdf.set_text_color(134, 134, 139)
        pdf.multi_cell(
            0, 4,
            f"※ 상태 '검토필요' 항목에 매칭된 분개를 항목당 금액 상위 {CHECKLIST_JOURNAL_CAP}건까지 첨부합니다 "
            "(자동계산·해당없음 항목 제외). 전체 분개는 앱 5단계 CSV 참조.",
            new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*_HEAD)
        for c in _review_items:
            _lines = c.lines
            _body_font(pdf, 8, bold=True)
            pdf.multi_cell(0, 4.8, f"■ {c.item}  [{c.legal_basis}]  ({len(_lines):,}건)",
                           new_x="LMARGIN", new_y="NEXT")
            _simple_table(
                pdf, ["날짜", "계정과목", "적요", "거래처", "차변", "대변"],
                _journal_rows_for_pdf(_lines, cap=CHECKLIST_JOURNAL_CAP),
                widths=[14, 22, 30, 20, 17, 17], size=7.0,
            )
            if len(_lines) > CHECKLIST_JOURNAL_CAP:
                _body_font(pdf, 7.0)
                pdf.set_text_color(134, 134, 139)
                pdf.multi_cell(
                    0, 4.0,
                    f"  ※ 전체 {len(_lines):,}건 중 금액 상위 {CHECKLIST_JOURNAL_CAP}건만 표시",
                    new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(*_HEAD)
            pdf.ln(1.5)

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

    # ── ⑦ 세무 컨설팅 코멘트 (규칙엔진 발굴 — 회계사 채택 후 확정) ──────────────
    if consulting_topics:
        pdf.add_page()
        _h2(pdf, f"7. 세무 컨설팅 코멘트 (검토 후보 {len(consulting_topics)}건 — 미확정)")
        _body_font(pdf, 7.5)
        pdf.set_text_color(134, 134, 139)
        pdf.multi_cell(0, 4,
                       "※ 재무자료·세무조정 결과에서 규칙엔진이 발굴한 자문 후보입니다. 모두 미확정이며 "
                       "회계사가 요건 검토 후 채택·확정합니다 (AI가 적용을 확정하지 않습니다).",
                       new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*_HEAD)
        from src.rules.consulting import SCENARIO_DISCLAIMER
        from src.rag.reference_retriever import format_reference
        for _t in consulting_topics:
            _body_font(pdf, 9, bold=True)
            pdf.multi_cell(0, 5.5, f"[{_t.category}·{_t.severity}] {_t.title}",
                           new_x="LMARGIN", new_y="NEXT")
            _body_font(pdf, 8)
            pdf.multi_cell(0, 4.5, f"  현재상황: {_t.situation}", new_x="LMARGIN", new_y="NEXT")
            pdf.multi_cell(0, 4.5, f"  근거: {_t.basis}", new_x="LMARGIN", new_y="NEXT")
            _body_font(pdf, 8, bold=True)
            pdf.multi_cell(0, 4.6, f"  결론 — 시나리오 ({SCENARIO_DISCLAIMER})",
                           new_x="LMARGIN", new_y="NEXT")
            _body_font(pdf, 8)
            for _sc in (getattr(_t, "scenarios", None) or []):
                _chk = " [회계사 확인 필요]" if _sc.needs_law_check else ""
                pdf.multi_cell(0, 4.4, f"  · {_sc.name}{_chk}", new_x="LMARGIN", new_y="NEXT")
                pdf.multi_cell(0, 4.2, f"      행동: {_sc.action}", new_x="LMARGIN", new_y="NEXT")
                pdf.multi_cell(0, 4.2, f"      효과: {_sc.effect}", new_x="LMARGIN", new_y="NEXT")
                if _sc.requirement:
                    pdf.multi_cell(0, 4.2, f"      요건: {_sc.requirement}", new_x="LMARGIN", new_y="NEXT")
                if _sc.risk:
                    pdf.multi_cell(0, 4.2, f"      리스크: {_sc.risk}", new_x="LMARGIN", new_y="NEXT")
            _body_font(pdf, 7.5)
            pdf.set_text_color(134, 134, 139)
            pdf.multi_cell(0, 4, f"  법령 근거: {_t.legal_basis} · {_t.status}",
                           new_x="LMARGIN", new_y="NEXT")
            # 참고자료 발췌 (국세청 참고파일 RAG — 검토 근거 자료, 미확정)
            for _ref in (getattr(_t, "references", None) or []):
                pdf.multi_cell(0, 4, f"  └ 참고자료: {format_reference(_ref)}",
                               new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*_HEAD)
            pdf.ln(1)

    # ── ⑧ 고객 설명 메모 ─────────────────────────────────────────────────────
    if client_memo:
        pdf.add_page()
        _h2(pdf, "8. 고객 설명용 메모 (초안)")
        _body_font(pdf, 8.5)
        pdf.multi_cell(0, 5, client_memo, new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
