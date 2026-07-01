"""결산부속명세서(계정별 세부명세) 파서 — 블록 반복형에서 세부 라인 추출 검증.

read_any_table 출력 형태(컬럼 코드/계정과목명/적요/코드.1/거래처명/금액/비고)를 합성해
파일·네트워크 없이 _account_details_from_df 순수 로직을 회귀 보호한다.
"""
import pandas as pd

from src.parsers.smart_a import _account_details_from_df


def _block_df() -> pd.DataFrame:
    """현금(2줄)·외상매출금(페이지 2개로 분할)·합계/제목/헤더/회사행 혼재한 합성 표."""
    cols = ["코드", "계정과목명", "적요", "코드.1", "거래처명", "금액", "비고"]
    rows = [
        # 현금 블록
        ["10100", "현금", "", "", "미등록거래처", "66,240", ""],
        ["10100", "현금", "", "098000", "기업은행", "-66,240", ""],
        ["합 계", "", "", "", "", "", ""],
        # 보통예금 제목/기간/회사/반복헤더(모두 세부 아님) + 세부 2줄
        ["", "", "보통예금명세서", "", "", "", ""],
        ["", "", "28기 2025년 12월 31일 현재", "", "", "", ""],
        ["(주)티엘", "", "", "", "", "(단위: 원)", ""],
        ["코드", "계정과목명", "적요", "코드", "거래처명", "금액", "비고"],
        ["10300", "보통예금", "", "098000", "기업은행", "472,703,017", ""],
        ["10300", "보통예금", "", "098019", "기업 044", "14,351,857", ""],
        ["합 계", "", "", "", "", "487,054,874", ""],
        # 외상매출금 — 페이지 1
        ["10800", "외상매출금", "", "000112", "롯데쇼핑", "427,316", ""],
        # 외상매출금 — 페이지 2 (제목·헤더 반복 후 이어짐)
        ["", "", "외상매출금명세서", "", "", "", ""],
        ["코드", "계정과목명", "적요", "코드", "거래처명", "금액", "비고"],
        ["10800", "외상매출금", "", "000113", "홈플러스", "76,091", ""],
    ]
    return pd.DataFrame(rows, columns=cols)


def test_extracts_only_detail_lines():
    out = _account_details_from_df(_block_df())
    # 세부 라인만: 현금2 + 보통예금2 + 외상매출금2 = 6 (제목·헤더·합계·회사행 제외)
    assert len(out) == 6
    assert set(out["계정명"]) == {"현금", "보통예금", "외상매출금"}
    assert list(out.columns) == ["계정코드", "계정명", "적요", "거래처코드", "거래처명", "금액", "비고"]


def test_amounts_parsed_with_sign_and_commas():
    out = _account_details_from_df(_block_df())
    cash = out[out["계정명"] == "현금"]["금액"].tolist()
    assert cash == [66240, -66240]
    assert out[out["계정명"] == "보통예금"]["금액"].sum() == 487_054_874


def test_paginated_account_merges_by_name():
    """제목·헤더가 중간에 반복돼도 같은 계정으로 병합된다 (외상매출금 2건)."""
    out = _account_details_from_df(_block_df())
    ar = out[out["계정명"] == "외상매출금"]
    assert len(ar) == 2
    assert ar["금액"].sum() == 427_316 + 76_091
    assert set(ar["거래처명"]) == {"롯데쇼핑", "홈플러스"}


def test_no_total_or_header_rows_leak():
    out = _account_details_from_df(_block_df())
    assert "합 계" not in set(out["계정코드"])
    assert "계정과목명" not in set(out["계정명"])
    # 계정코드는 모두 숫자로 시작
    assert out["계정코드"].str.match(r"^\d").all()
