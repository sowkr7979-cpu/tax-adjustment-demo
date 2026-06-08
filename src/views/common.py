"""views 공통 헬퍼 — 날짜·사업자번호·DART 미리보기."""
from __future__ import annotations
import calendar
from datetime import date

import streamlit as st

from src.apis.dart_api import DartApiClient


@st.cache_data(ttl=3600, show_spinner=False)
def _dart_preview(corp_code: str) -> dict:
    """검색 결과 식별용 상세 미리보기 (1시간 캐시).

    동일 상호·다른 업종 법인 구분을 위해 선택 항목의 업종·대표자·주소를
    자동 입력 확정 전에 보여준다. 실패 시 빈 dict.
    """
    try:
        info = DartApiClient().get_company_info(corp_code)
    except Exception:
        return {}
    if not info:
        return {}
    return {
        "ceo": info.ceo_nm,
        "industry_code": info.industry_code,
        "adres": info.adres,
        "est_dt": info.est_dt,
        "acc_mt": info.acc_mt,
    }


def _parse_stored_date(s: str, fallback: date) -> date:
    try:
        return date.fromisoformat(s) if s else fallback
    except ValueError:
        return fallback


def _fmt_bizr(raw: str) -> str:
    """'0001234567' → '000-12-34567'"""
    d = "".join(c for c in raw if c.isdigit())
    return f"{d[:3]}-{d[3:5]}-{d[5:]}" if len(d) == 10 else raw


def _set_fiscal_year_from_acc_mt(proj, acc_mt: str) -> None:
    """결산월(acc_mt)로 직전 사업연도 시작·종료일 자동 설정."""
    try:
        month = int(acc_mt)
        fy_end_year = date.today().year - 1
        last_day = calendar.monthrange(fy_end_year, month)[1]
        fy_end_date = date(fy_end_year, month, last_day)
        start_month = (month % 12) + 1
        start_year = fy_end_year if month == 12 else fy_end_year - 1
        fy_start_date = date(start_year, start_month, 1)
        proj.company.fiscal_year_start = str(fy_start_date)
        proj.company.fiscal_year_end   = str(fy_end_date)
    except (ValueError, TypeError):
        pass
