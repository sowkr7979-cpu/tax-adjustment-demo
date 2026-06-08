"""CSV/Excel 수식 인젝션 방어 테스트."""
import pandas as pd

from src.utils.safe_export import sanitize_cell, safe_df, safe_filename


def test_safe_filename():
    assert safe_filename("(주)에이/에스:센터") == "(주)에이_에스_센터"
    assert safe_filename('a*b?c"d<e>f|g') == "a_b_c_d_e_f_g"
    assert safe_filename("정상회사") == "정상회사"
    assert safe_filename("") == "output"
    assert safe_filename("...") == "output"   # 점만 → fallback


def test_sanitize_triggers():
    assert sanitize_cell("=HYPERLINK(\"x\")") == "'=HYPERLINK(\"x\")"
    assert sanitize_cell("+1+1") == "'+1+1"
    assert sanitize_cell("-2") == "'-2"
    assert sanitize_cell("@SUM") == "'@SUM"
    assert sanitize_cell("\t=cmd") == "'\t=cmd"


def test_sanitize_safe_values():
    assert sanitize_cell("정상 적요") == "정상 적요"
    assert sanitize_cell("") == ""
    assert sanitize_cell(1234) == 1234        # 숫자는 그대로
    assert sanitize_cell(None) is None


def test_safe_df_escapes_strings_only():
    df = pd.DataFrame({
        "적요": ["=WEBSERVICE(\"http://evil\")", "정상"],
        "금액": [1000, -2000],   # 숫자 컬럼 — 음수도 그대로
    })
    out = safe_df(df)
    assert out["적요"].tolist() == ["'=WEBSERVICE(\"http://evil\")", "정상"]
    assert out["금액"].tolist() == [1000, -2000]
    # 원본 비변경
    assert df["적요"].iloc[0] == "=WEBSERVICE(\"http://evil\")"
