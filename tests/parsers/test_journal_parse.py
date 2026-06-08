"""분개장 파서(벡터화 _journal_lines_from_df) 단위 테스트."""
from datetime import date

import pandas as pd

from src.parsers.smart_a import _journal_lines_from_df


def _df():
    # read_any_table 출력 모사 — 전부 문자열. WEHAGO식 중복 Code(계정/거래처)·별칭 포함.
    return pd.DataFrame({
        "일자": ["2025-01-15", "", "2025/03/02"],   # 빈 날짜 행은 스킵
        "전표번호": ["1", "2", "3"],
        "Code": ["101", "102", "103"],              # 계정코드 별칭
        "계정명": ["보통예금", "현금", "가지급금"],
        "적요": ["a", "b", "c"],
        "Code.1": ["C1", "C2", "C3"],               # 거래처코드 별칭
        "거래처명": ["갑", "을", "병"],
        "차변": ["1,000", "0", "(500)"],            # 음수 괄호 표기
        "대변": ["0", "2,000", "0"],
        "증빙구분": ["카드", "", "세금계산서"],
        "카드번호": ["1234", "", ""],
        "__sheet__": ["s", "s", "s"],
        "__row__": ["2", "3", "4"],
    }).astype(str)


def test_alias_and_date_skip():
    lines = _journal_lines_from_df(_df(), "src.xlsx")
    # 둘째 행은 날짜 비어 스킵 → 2건
    assert len(lines) == 2
    assert [l.date for l in lines] == [date(2025, 1, 15), date(2025, 3, 2)]


def test_dup_code_resolution():
    """WEHAGO 중복 Code — 계정코드=Code, 거래처코드=Code.1로 정확히 분리."""
    lines = _journal_lines_from_df(_df(), "src.xlsx")
    assert lines[0].account_code == "101" and lines[0].counterparty_code == "C1"
    assert lines[1].account_code == "103" and lines[1].counterparty_code == "C3"


def test_amount_and_evidence():
    lines = _journal_lines_from_df(_df(), "src.xlsx")
    assert lines[0].debit == 1_000 and lines[0].credit == 0
    assert lines[1].debit == -500          # (500) → 음수
    assert lines[0].evidence_type == "카드" and lines[0].card_no == "1234"
    # 미존재 컬럼(차량번호·프로젝트·증빙번호)은 빈 문자열
    assert lines[0].vehicle_no == "" and lines[0].project == ""
    assert lines[0].source_file == "src.xlsx" and lines[0].source_row == 2


def test_empty_df():
    assert _journal_lines_from_df(pd.DataFrame(), "x") == []
