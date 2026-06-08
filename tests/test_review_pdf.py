# -*- coding: utf-8 -*-
"""검토패키지 PDF 생성 테스트 — 한글 포함 전체 섹션이 유효한 PDF로 나오는지."""
from datetime import date

import pandas as pd
import pytest

from src.forms.review_pdf import build_review_pdf, build_client_memo, _FONT_REG
from src.rules.data_requests import DataRequest, assess_risk
from src.utils.models import TaxAdjustmentResult


class _Cov:
    def __init__(self, item, status, amount_hint=0, legal_basis="법§25", detail="내역"):
        self.item, self.status = item, status
        self.amount_hint, self.legal_basis, self.detail = amount_hint, legal_basis, detail


@pytest.mark.skipif(not _FONT_REG.exists(), reason="맑은고딕 폰트 없음")
def test_build_review_pdf_full():
    r = TaxAdjustmentResult(
        fiscal_year_start=date(2025, 1, 1), fiscal_year_end=date(2025, 12, 31),
        is_sme=True,
        entertainment_excess=11_000_000, penalty=772_000,
        deemed_interest=4_600_000, depreciation_excess=2_327_919,
        net_income=58_053_101,
    )
    calc_details = {
        "기업업무추진비 한도초과": {
            "금액": 11_000_000, "법령": "법§25④·⑤",
            "산식": ["기본한도 = 3,600만원 × 12/12", "초과액 11,000,000원"],
            "사유": "분개장 자동 집계 결과 한도 초과", "lines": [1, 2, 3],
        },
        "(참고) 특수관계인 매출 집계": {"금액": 5, "법령": "", "산식": [], "사유": ""},
    }
    coverage = [
        _Cov("기업업무추진비 한도·증빙", "자동계산", 114_747_183),
        _Cov("가지급금 인정이자", "검토필요", 50_000_000, "법§52"),
        _Cov("의제배당", "해당없음"),
    ]
    requests = [DataRequest("법인카드 사용내역", "증빙 판정 불가", "법§25②", "High")]
    yoy = pd.DataFrame({
        "계정명": ["기업업무추진비"], "당기": [80_000_000], "전기": [40_000_000],
        "증감": [40_000_000], "증감률(%)": [100.0],
    })

    pdf_bytes = build_review_pdf(
        company_name="(주)티엘", business_no="123-45-67890",
        fy_start=date(2025, 1, 1), fy_end=date(2025, 12, 31),
        result=r, calc_details=calc_details, coverage=coverage,
        requests=requests, yoy_df=yoy,
        yoy_warn=["⚠ 기업업무추진비 급증 — 전기 40,000,000 → 당기 80,000,000 (+100%)"],
        review_memos={"기업업무추진비 한도초과": "카드내역 대사 완료"},
        client_memo=build_client_memo(calc_details, "(주)티엘", 2025),
        risk_fn=assess_risk,
        law_check_label="2026-06-06 05:00",
    )
    assert pdf_bytes[:5] == b"%PDF-"
    assert len(pdf_bytes) > 20_000          # 폰트 임베드 포함 실질 콘텐츠
    assert pdf_bytes.rstrip().endswith(b"%%EOF")


def test_build_client_memo_skips_reference_items():
    memo = build_client_memo(
        {"(참고) 특수관계인 매출 집계": {"금액": 5, "법령": ""},
         "벌과금·과태료·가산세": {"금액": 772_000, "법령": "법§21 3호"}},
        "(주)테스트", 2025,
    )
    assert "(참고)" not in memo
    assert "벌과금" in memo and "772,000" in memo
    assert "검토 초안" in memo
