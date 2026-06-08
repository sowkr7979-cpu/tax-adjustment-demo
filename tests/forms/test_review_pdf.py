"""검토패키지 PDF — Book/Tax/세무조정·소득처분 + 근거분개 표시 테스트."""
from datetime import date

from src.forms.review_pdf import (
    book_tax_lines, _journal_rows_for_pdf, JOURNAL_LINE_CAP, build_review_pdf,
)
from src.utils.models import JournalLine, TaxAdjustmentResult


def _line(amount_debit=0, amount_credit=0, name="기업업무추진비", desc="식대"):
    return JournalLine(
        journal_id="J1", line_no=1, date=date(2025, 3, 2),
        account_code="8132", account_name=name, description=desc,
        counterparty_code="", counterparty_name="(주)거래처",
        debit=amount_debit, credit=amount_credit,
        evidence_type="카드", evidence_no="", card_no="1234",
        vehicle_no="", project="", source_file="f.xls",
        source_sheet="분개장", source_row=10,
    )


def test_book_tax_lines_full():
    """book/tax/계산근거/처분이 모두 있으면 4줄 (Book·Tax·계산근거·T·A)."""
    d = {"금액": 6_576_771, "book": 114_747_183, "tax": 108_170_412,
         "tax_basis": "기본한도 + 수입금액한도", "처분": "기타사외유출"}
    lines = book_tax_lines(d)
    assert lines[0] == "Book (장부상 금액): 114,747,183원"
    assert lines[1] == "Tax (세무상 금액): 108,170,412원"
    assert lines[2] == "세무상 금액 계산근거: 기본한도 + 수입금액한도"
    assert lines[3] == "T/A (세무조정): 6,576,771원 · 소득처분 기타사외유출"


def test_book_tax_lines_missing_book_tax_shows_dash():
    """book/tax가 None이면 '—', tax_basis 없으면 계산근거 줄 생략."""
    d = {"금액": 5_000_000, "book": None, "tax": None, "처분": "유보"}
    lines = book_tax_lines(d)
    assert lines[0] == "Book (장부상 금액): —"
    assert lines[1] == "Tax (세무상 금액): —"
    # tax_basis 없음 → 계산근거 줄 없이 바로 T/A
    assert lines[2].startswith("T/A (세무조정): 5,000,000원 · 소득처분 유보")
    assert len(lines) == 3


def test_book_tax_lines_unset_disposition():
    """처분 미지정이면 검토필요 표기."""
    d = {"금액": 1_000_000, "book": 1_000_000, "tax": 0}
    assert "검토필요" in book_tax_lines(d)[-1]


def test_journal_rows_cap_and_columns():
    """근거분개 행은 6열(날짜·계정·적요·거래처·차변·대변), 상한 적용."""
    lines = [_line(amount_debit=1000 + i) for i in range(JOURNAL_LINE_CAP + 20)]
    rows = _journal_rows_for_pdf(lines)
    assert len(rows) == JOURNAL_LINE_CAP
    assert len(rows[0]) == 6
    assert rows[0][1] == "기업업무추진비"
    # 금액 내림차순 정렬 → 첫 행은 가장 큰 차변
    _max = 1000 + (JOURNAL_LINE_CAP + 20 - 1)
    assert rows[0][4] == f"{_max:,}"   # 차변 천단위
    assert rows[0][5] == ""            # 대변 0 → 빈칸


def test_journal_rows_sorted_by_amount_desc():
    """근거분개는 입력 순서가 아니라 금액(차변·대변 중 큰 값) 내림차순으로 표시."""
    lines = [
        _line(amount_debit=100, desc="작은차변"),
        _line(amount_credit=900, desc="큰대변"),
        _line(amount_debit=500, desc="중간차변"),
    ]
    rows = _journal_rows_for_pdf(lines)
    assert [r[2] for r in rows] == ["큰대변", "중간차변", "작은차변"]
    assert rows[0][5] == "900"   # 큰 대변이 맨 위


def test_build_review_pdf_with_book_tax_details():
    """calc_details에 book/tax/근거분개가 있으면 PDF가 생성된다 (스모크)."""
    r = TaxAdjustmentResult(
        fiscal_year_start=date(2025, 1, 1),
        fiscal_year_end=date(2025, 12, 31), is_sme=True,
    )
    r.entertainment_excess = 6_576_771
    calc_details = {
        "기업업무추진비 한도초과": {
            "금액": 6_576_771, "법령": "법§25④·⑤",
            "산식": ["기본한도 3,600만 × 12/12", "총한도 108,170,412원"],
            "lines": [_line(amount_debit=50_000) for _ in range(120)],
            "사유": "지출 합계가 한도 초과",
            "book": 114_747_183, "tax": 108_170_412,
            "tax_basis": "기본한도 + 수입금액한도 = 손금인정 한도",
            "처분": "기타사외유출",
        },
        "(참고) 특수관계인 매출 집계": {  # 참고 항목 → 본문 제외
            "금액": 999, "법령": "", "산식": [], "lines": [], "사유": "",
            "book": None, "tax": None, "tax_basis": "", "처분": "",
        },
    }
    out = build_review_pdf(
        company_name="(주)테스트", business_no="123-45-67890",
        fy_start=date(2025, 1, 1), fy_end=date(2025, 12, 31),
        result=r, calc_details=calc_details,
        coverage=[], requests=[], yoy_df=None, yoy_warn=[],
        review_memos={}, client_memo="", risk_fn=lambda *a: "Low",
    )
    assert isinstance(out, bytes) and len(out) > 1000
    assert out[:4] == b"%PDF"
