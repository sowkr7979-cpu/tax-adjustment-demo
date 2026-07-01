# -*- coding: utf-8 -*-
"""리뷰 흐름 기능 테스트 — 전년도 승계, 자료요청 리스트, 증감분석, 위험도."""
import pandas as pd

from src.project.taxproj import TaxProject
from src.rules.data_requests import build_data_requests, assess_risk, DataRequest
from src.rules.yoy_analysis import yoy_table, yoy_flags


# ── 전년도 .taxproj 승계 ──────────────────────────────────────────────────────

def _prev_project() -> TaxProject:
    p = TaxProject()
    p.company.name = "(주)테스트"
    p.company.fiscal_year_start = "2024-01-01"
    p.company.fiscal_year_end = "2024-12-31"
    p.company.is_sme = True
    p.manual_input.carryforward_losses = [{"year": 2022, "amount": 50_000_000}]
    p.manual_input.related_parties = ["홍길동 (대표이사)"]
    p.manual_input.officer_names = ["홍길동"]
    p.manual_input.forex_method_reported = True
    p.tax_adjustments = {
        "depreciation_denial_end": 12_345_678,
        "reserves": [
            {"code": "감가상각 부인누계", "amount": 12_345_678, "disposition": "유보"},
            {"code": "외화환산이익 익금불산입", "amount": 3_000_000, "disposition": "△유보"},
        ],
    }
    return p


def test_carry_forward_reserves_and_losses():
    cur = TaxProject()
    notes = cur.carry_forward_from(_prev_project())
    assert cur.manual_input.carryforward_losses == [{"year": 2022, "amount": 50_000_000}]
    # 전년 계산 결과의 유보 발생분이 당기 '전기 유보'로
    assert len(cur.manual_input.prior_reserves) == 2
    assert cur.manual_input.prior_reserves[1]["disposition"] == "△유보"
    assert cur.manual_input.depreciation_denial_cumulative == 12_345_678
    assert cur.manual_input.related_parties == ["홍길동 (대표이사)"]
    assert cur.manual_input.forex_method_reported is True
    assert notes  # 승계 내역 설명 존재


def test_carry_forward_advances_fiscal_year():
    cur = TaxProject()
    cur.carry_forward_from(_prev_project())
    assert cur.company.fiscal_year_start == "2025-01-01"
    assert cur.company.fiscal_year_end == "2025-12-31"
    assert cur.company.name == "(주)테스트"
    assert cur.company.sme_verified is False   # 매년 재판정


# ── 자료요청 리스트 ───────────────────────────────────────────────────────────

class _FakeLoader:
    income_statement = None
    account_statement = None
    journals: list = []
    fixed_assets: list = []

    def get_net_income(self):
        return 0


def test_data_requests_missing_everything():
    p = TaxProject()
    reqs = build_data_requests(_FakeLoader(), p.manual_input, p.company,
                               agg=None, has_prev_proj=False)
    items = " ".join(q.item for q in reqs)
    assert "전년도 세무조정계산서" in items
    assert "손익계산서" in items
    assert all(isinstance(q, DataRequest) for q in reqs)


def test_data_requests_net_income_confirmed_suppresses():
    """'당기순이익 0원 확인' 또는 수기 입력 시 손익계산서 재요청 안 함 (모순 방지)."""
    p = TaxProject()
    reqs = build_data_requests(_FakeLoader(), p.manual_input, p.company,
                               agg=None, has_prev_proj=False,
                               net_income_confirmed=True)
    assert not any("손익계산서" in q.item for q in reqs)


def test_data_requests_prev_loaded_suppresses():
    p = TaxProject()
    p.manual_input.prior_reserves = [{"code": "x", "amount": 1, "disposition": "유보"}]
    reqs = build_data_requests(_FakeLoader(), p.manual_input, p.company,
                               agg=None, has_prev_proj=True)
    assert not any("전년도" in q.item for q in reqs)


# ── 위험도 ────────────────────────────────────────────────────────────────────

def test_assess_risk():
    assert assess_risk("가지급금 인정이자", 1_000_000) == "High"      # 특수관계 성격
    assert assess_risk("기업업무추진비 증빙불비", 500_000) == "High"   # 증빙
    assert assess_risk("소모품비", 2_000_000) == "Low"
    assert assess_risk("지급수수료", 60_000_000) == "High"            # 금액
    assert assess_risk("수선비", 20_000_000) == "Medium"
    assert assess_risk("기타", 5_000_000, status="검토필요") == "Medium"


# ── 전년 대비 증감분석 ────────────────────────────────────────────────────────

def test_yoy_table_and_flags():
    df = pd.DataFrame({
        "계정명": ["매출액", "기업업무추진비", "복리후생비", "소모품비"],
        "당기금액": [1_000_000_000, 80_000_000, 50_000_000, 3_000_000],
        "전기금액": [900_000_000, 40_000_000, 48_000_000, 2_900_000],
    })
    t = yoy_table(df)
    assert t is not None
    ent = t[t["계정명"] == "기업업무추진비"].iloc[0]
    assert ent["증감"] == 40_000_000
    flags = yoy_flags(t, revenue_cur=1_000_000_000, revenue_prev=900_000_000)
    # 접대비 +100% 급증 플래그
    assert any("기업업무추진비" in f and "급증" in f for f in flags)
    # 복리후생비 +4%는 플래그 없음
    assert not any("복리후생비" in f for f in flags)


def test_yoy_preserves_income_statement_order():
    """증감 금액 크기순이 아니라 손익계산서(입력) 순서를 그대로 유지한다."""
    df = pd.DataFrame({
        "계정명": ["매출액", "소모품비", "기업업무추진비"],
        "당기금액": [1_000_000_000, 3_000_000, 80_000_000],
        "전기금액": [900_000_000, 2_900_000, 40_000_000],
    })
    t = yoy_table(df)
    # 증감액으로 정렬했다면 [매출액, 기업업무추진비, 소모품비]가 됐을 것 — 입력 순서 유지 확인
    assert list(t["계정명"]) == ["매출액", "소모품비", "기업업무추진비"]


def test_yoy_table_none_when_no_prev():
    df = pd.DataFrame({"계정명": ["매출액"], "당기금액": [100], "전기금액": [0]})
    assert yoy_table(df) is None


def test_yoy_from_uploaded_prev_statement():
    """단일연도 당기 P&L + 별도 업로드한 전기 P&L → 증감분석 가능."""
    cur = pd.DataFrame({"계정명": ["매출액", "기업업무추진비"],
                        "당기금액": [1_000, 80]})
    prev = pd.DataFrame({"계정명": ["매출액", "기업업무추진비", "잡손실"],
                         "당기금액": [900, 40, 7]})   # 전기 P&L의 '당기' = 전기 값
    t = yoy_table(cur, prev_income_df=prev)
    assert t is not None
    assert t.attrs["prev_source"] == "전기 손익계산서 업로드"
    ent = t[t["계정명"] == "기업업무추진비"].iloc[0]
    assert ent["전기"] == 40 and ent["증감"] == 40
    # 전기에만 있던 계정(잡손실)도 소멸 항목으로 포함
    assert (t["계정명"] == "잡손실").any()


def test_bs_opening_check():
    from src.rules.yoy_analysis import bs_opening_check
    cur = pd.DataFrame({
        "계정명": ["단기차입금", "임대보증금", "현금"],
        "기초잔액": [500_000_000, 100_000_000, 3_000_000],
        "기말잔액": [700_000_000, 100_000_000, 5_000_000],
    })
    prev = pd.DataFrame({
        "계정명": ["단기차입금", "임대보증금", "현금"],
        "기말잔액": [500_000_000, 90_000_000, 3_000_000],   # 임대보증금 1천만 불일치
        "기초잔액": [0, 0, 0],
    })
    chk = bs_opening_check(cur, prev)
    assert chk is not None
    assert len(chk) == 1
    assert chk.iloc[0]["계정명"] == "임대보증금"
    assert chk.iloc[0]["차이"] == 10_000_000
