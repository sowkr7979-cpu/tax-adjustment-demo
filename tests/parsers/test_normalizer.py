# -*- coding: utf-8 -*-
"""회계자료 표준화 파이프라인 테스트 — HTML형 .xls, 음수 표기, 헤더 탐지, 합계행."""
import pytest

from src.parsers.normalizer import (
    sniff_format, parse_amount, is_total_row, detect_header_row,
    read_any_table, expand_keywords,
)


# ── 음수·금액 표기 ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ("1,234,567",     1_234_567),
    ("426584000.0",   426_584_000),
    ("(1,234)",       -1_234),          # 괄호 음수
    ("△1,234",        -1_234),          # 세모 음수
    ("▲ 5,000",       -5_000),          # 채운 세모 + 공백
    ("-1,234",        -1_234),
    ("1234-",         -1_234),          # 후행 마이너스
    ("12,345원",      12_345),          # 단위 표기
    ("１２３",         123),             # 전각 숫자
    ("-",             0),
    ("",              0),
    ("nan",           0),
    ("적요텍스트",     0),
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


# ── 합계행 판별 ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name, expected", [
    ("합계", True), ("소 계", True), ("자산총계", True),
    ("부채와자본총계", True), ("[합계]", True),
    ("당기순이익", False), ("기계장치", False), ("회계법인수수료", False),
    ("매출액", False), ("세금과공과", False),
])
def test_is_total_row(name, expected):
    assert is_total_row(name) is expected


def test_expand_keywords():
    kws = expand_keywords(("기업업무추진비",))
    assert "접대비" in kws
    assert "기업업무추진비" in kws


# ── HTML형 .xls (확장자 위장 — 구버전 더존 내보내기 재현) ────────────────────

_HTML_DOC = """<html><head><meta charset="{charset}"></head><body>
<table>
 <tr><td colspan="5">분 개 장</td></tr>
 <tr><td colspan="5">(주)테스트 2025-01-01 ~ 2025-12-31</td></tr>
 <tr><td></td><td></td><td></td><td></td><td></td></tr>
 <tr><td>날짜</td><td>전표번호</td><td>계정코드</td><td>계정명</td><td>차변</td></tr>
 <tr><td>2025-03-15</td><td>V001</td><td>81320</td><td>기업업무추진비</td><td>150,000</td></tr>
 <tr><td>2025-06-30</td><td>V002</td><td>83910</td><td>세금과공과</td><td>(50,000)</td></tr>
</table></body></html>"""


@pytest.fixture
def html_xls(tmp_path):
    """cp949 인코딩 HTML인데 확장자는 .xls인 파일."""
    p = tmp_path / "분개장.xls"
    p.write_bytes(_HTML_DOC.format(charset="euc-kr").encode("cp949"))
    return p


def test_sniff_html_disguised_as_xls(html_xls):
    assert sniff_format(html_xls) == "html"


def test_read_any_table_html(html_xls):
    df, meta = read_any_table(html_xls)
    assert meta["format"] == "html"
    assert meta["encoding"] in ("cp949", "euc-kr")
    # 제목 2행 + 빈 행 아래의 실제 헤더를 찾았는가
    assert "계정명" in df.columns or "계정코드" in df.columns
    assert meta["rows"] == 2
    # 데이터 검증
    names = df["계정명"].tolist()
    assert "기업업무추진비" in names
    assert parse_amount(df.iloc[1]["차변"]) == -50_000   # 괄호 음수


def test_parse_journal_from_html_xls(html_xls):
    """파서 전체 경로: HTML형 .xls → JournalLine."""
    from src.parsers.smart_a import parse_journal
    lines = parse_journal(html_xls)
    assert len(lines) == 2
    assert lines[0].account_code == "81320"
    assert lines[0].debit == 150_000


def test_real_xlsx_unaffected(tmp_path):
    """진짜 XLSX는 기존 동작 유지 (헤더 1행)."""
    import pandas as pd
    p = tmp_path / "journal.xlsx"
    pd.DataFrame({
        "날짜": ["2025-01-05"], "전표번호": ["1"], "계정코드": ["81320"],
        "계정명": ["기업업무추진비"], "차변": ["30000"], "대변": ["0"],
    }).to_excel(p, index=False)
    df, meta = read_any_table(p)
    assert meta["format"] == "xlsx"
    assert meta["rows"] == 1
    assert "계정명" in df.columns


def test_malformed_xlsx_bad_xf_count(tmp_path):
    """비표준 styles.xml(<xf>에 count 속성) — openpyxl 실패 시 정정 후 복구 읽기.

    일부 회계 프로그램 내보내기가 OOXML 스펙을 어겨 `<xf>` 요소에 `count` 속성을
    붙인다. openpyxl CellStyle 파서가 거부하므로 styles.xml을 정정해 복구해야 한다.
    """
    import io
    import re
    import zipfile

    import pandas as pd

    p = tmp_path / "journal.xlsx"
    pd.DataFrame({
        "날짜": ["2025-04-01"], "전표번호": ["00001"], "계정코드": ["255"],
        "계정명": ["부가세예수금"], "차변": ["3,904,780"], "대변": ["0"],
    }).to_excel(p, index=False)

    # styles.xml의 cellStyleXfs 내부 <xf>에 잘못된 count 속성을 주입해 파일을 깨뜨린다
    with zipfile.ZipFile(p) as src:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
            for item in src.infolist():
                data = src.read(item.filename)
                if item.filename == "xl/styles.xml":
                    text = data.decode("utf-8")
                    text = re.sub(r"<cellStyleXfs([^>]*)><xf",
                                  '<cellStyleXfs\\1><xf count="1"', text, count=1)
                    data = text.encode("utf-8")
                out.writestr(item, data)
        p.write_bytes(buf.getvalue())

    # 표준 openpyxl 읽기는 실패해야 한다 (재현 검증)
    with pytest.raises(Exception):
        pd.read_excel(p, engine="openpyxl")

    df, meta = read_any_table(p)
    assert meta["format"] == "xlsx"
    assert "sanitized" in str(meta["encoding"])
    assert meta["rows"] == 1
    assert "계정명" in df.columns
    assert df.iloc[0]["계정명"] == "부가세예수금"


def test_title_rows_above_header_xlsx(tmp_path):
    """진짜 Excel인데 제목·회사명 행이 헤더 위에 있는 경우 — 헤더 재탐지."""
    import pandas as pd
    p = tmp_path / "ledger.xlsx"
    rows = [
        ["계 정 별 원 장", "", "", ""],
        ["(주)테스트", "", "", ""],
        ["날짜", "계정코드", "계정명", "차변"],
        ["2025-02-01", "81320", "기업업무추진비", "100,000"],
    ]
    pd.DataFrame(rows).to_excel(p, index=False, header=False)
    df, meta = read_any_table(p)
    # 첫 행이 헤더로 잡히면 Unnamed 비율 60% 이상 → 본문에서 재탐지
    assert "계정명" in df.columns
    assert meta["rows"] == 1
