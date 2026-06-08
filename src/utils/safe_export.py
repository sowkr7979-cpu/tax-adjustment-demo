"""CSV/Excel 수식 인젝션(Formula Injection) 방어 — 화면·Excel·CSV 공용.

신뢰불가 입력(고객 분개 적요·거래처명·계정명, LLM 출력)이 스프레드시트 셀에서
수식(=HYPERLINK, =WEBSERVICE, =cmd 등)으로 실행되지 않도록 위험 선두문자를 무력화한다.
"""
from __future__ import annotations

import re

import pandas as pd

# 파일명에 쓸 수 없는 문자(경로 구분자·예약문자·제어문자) — 다운로드 파일명 정제용
_FILENAME_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def safe_filename(name: str, fallback: str = "output") -> str:
    """다운로드 파일명용 — 경로/예약 문자를 '_'로 치환. 회사명 등 사용자 입력 정제."""
    cleaned = _FILENAME_BAD.sub("_", str(name)).strip().strip(".")
    return cleaned or fallback

# Excel/Sheets가 수식으로 해석하기 시작하는 선두문자 (+ 제어문자)
FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r", "\n")


def sanitize_cell(v):
    """문자열이 수식 트리거로 시작하면 앞에 작은따옴표를 붙여 텍스트로 고정."""
    if isinstance(v, str) and v and v[0] in FORMULA_TRIGGERS:
        return "'" + v
    return v


def safe_df(df: "pd.DataFrame") -> "pd.DataFrame":
    """모든 셀에 sanitize_cell 적용한 사본 반환 (to_csv 직전 사용).

    sanitize_cell은 비문자열(숫자·None)을 그대로 두므로 컬럼 dtype과 무관하게 안전하다.
    (pandas 2.x는 문자열 컬럼 dtype을 object가 아닌 str로 추론할 수 있어 dtype 분기는 쓰지 않는다.)
    """
    out = df.copy()
    for col in out.columns:
        out[col] = out[col].map(sanitize_cell)
    return out
