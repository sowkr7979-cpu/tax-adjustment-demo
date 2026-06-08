"""자본금적립금(을) 유보 잔액표 빌더 테스트."""
from datetime import date

from src.forms.reserve_status import build_reserve_status, reserve_totals
from src.utils.models import TaxAdjustmentResult


def _r(**kw) -> TaxAdjustmentResult:
    r = TaxAdjustmentResult(
        fiscal_year_start=date(2025, 1, 1),
        fiscal_year_end=date(2025, 12, 31),
        is_sme=True,
    )
    for k, v in kw.items():
        setattr(r, k, v)
    return r


def _row(rows, code):
    return next(x for x in rows if x["과목"] == code)


def test_depreciation_reconciles_to_denial_end():
    """감가상각 부인누계 기말 = 엔진 denial_end, 기초 역산."""
    rows = build_reserve_status(
        prior_reserves=[],
        tax_result=_r(depreciation_excess=3_000_000, depreciation_approved=1_000_000),
        depr_denial_end=7_000_000,
    )
    d = _row(rows, "감가상각 부인누계")
    assert d["기말"] == 7_000_000
    assert d["기초"] == 7_000_000 - 3_000_000 + 1_000_000  # 5,000,000
    assert d["검토"] is False


def test_bad_debt_full_reversal():
    """대손충당금 총액법 — 전기 유보 전액 환입, 기말 = 당기 설정."""
    rows = build_reserve_status(
        prior_reserves=[{"code": "대손충당금 한도초과", "amount": 10_000_000, "disposition": "유보"}],
        tax_result=_r(bad_debt_excess=12_000_000),
    )
    bd = _row(rows, "대손충당금 한도초과")
    assert bd["감소"] == 10_000_000
    assert bd["기말"] == 12_000_000
    assert bd["검토"] is False


def test_manual_reversal_flagged():
    """기초 유보가 있는데 당기 추인 자동 미반영 → 검토 플래그."""
    rows = build_reserve_status(
        prior_reserves=[{"code": "퇴직급여충당금 한도초과", "amount": 8_000_000, "disposition": "유보"}],
        tax_result=_r(pension_excess=5_000_000),
    )
    p = _row(rows, "퇴직급여충당금 한도초과")
    assert p["기말"] == 13_000_000
    assert p["검토"] is True


def test_minus_reserve_and_unknown_prior():
    """△유보(퇴직연금 손금산입) + 스펙 외 전기유보 이월."""
    rows = build_reserve_status(
        prior_reserves=[{"code": "기타 유보항목", "amount": 3_000_000, "disposition": "유보"}],
        tax_result=_r(pension_deduction=2_000_000),
    )
    m = _row(rows, "퇴직연금 부담금(손금산입)")
    assert m["기말"] == 2_000_000 and m["처분"] == "△유보"
    other = _row(rows, "기타 유보항목")
    assert other["기말"] == 3_000_000 and other["검토"] is True


def test_bad_debt_supplementary_method():
    """보충법 — 전기 유보 이월(전액 환입 안 함), 추인은 검토 플래그."""
    rows = build_reserve_status(
        prior_reserves=[{"code": "대손충당금 한도초과", "amount": 10_000_000, "disposition": "유보"}],
        tax_result=_r(bad_debt_excess=12_000_000),
        bad_debt_method="보충법",
    )
    bd = _row(rows, "대손충당금 한도초과")
    assert bd["감소"] == 0
    assert bd["기말"] == 22_000_000   # 기초 10M + 당기 12M
    assert bd["검토"] is True


def test_depreciation_base_mismatch_flagged():
    """전기 부인누계 기재(기초)와 엔진 역산 기초가 다르면 검토 플래그."""
    rows = build_reserve_status(
        prior_reserves=[{"code": "감가상각 부인누계", "amount": 9_000_000, "disposition": "유보"}],
        tax_result=_r(depreciation_excess=3_000_000, depreciation_approved=1_000_000),
        depr_denial_end=7_000_000,  # 역산 기초 = 7M−3M+1M = 5M ≠ 전기기재 9M
    )
    d = _row(rows, "감가상각 부인누계")
    assert d["기말"] == 7_000_000
    assert d["검토"] is True


def test_minus_reserve_prior_balance_flagged():
    """전기 △유보 잔액이 있으면 차기 추인 검토 플래그 ON."""
    rows = build_reserve_status(
        prior_reserves=[{"code": "퇴직연금 부담금(손금산입)", "amount": 5_000_000, "disposition": "△유보"}],
        tax_result=_r(pension_deduction=2_000_000),
    )
    m = _row(rows, "퇴직연금 부담금(손금산입)")
    assert m["기말"] == 7_000_000
    assert m["검토"] is True


def test_decrease_override_recomputes_and_clears_flag():
    """당기 감소(추인) 직접 입력 → 기말 재계산 + 검토 플래그 해제."""
    rows = build_reserve_status(
        prior_reserves=[{"code": "퇴직급여충당금 한도초과", "amount": 8_000_000, "disposition": "유보"}],
        tax_result=_r(pension_excess=5_000_000),
        decrease_overrides={"퇴직급여충당금 한도초과": 3_000_000},
    )
    p = _row(rows, "퇴직급여충당금 한도초과")
    assert p["감소"] == 3_000_000
    assert p["기말"] == 8_000_000 + 5_000_000 - 3_000_000  # 10,000,000
    assert p["검토"] is False


def test_manual_rows_appended():
    """수기 유보 항목(일시상각충당금 등) 추가."""
    rows = build_reserve_status(
        prior_reserves=[],
        tax_result=_r(),
        manual_rows=[
            {"과목": "일시상각충당금", "기초": 0, "증가": 20_000_000, "감소": 0, "처분": "유보"},
            {"과목": "", "기초": 0, "증가": 0, "감소": 0, "처분": "유보"},  # 빈 행 무시
        ],
    )
    m = _row(rows, "일시상각충당금")
    assert m["기말"] == 20_000_000 and m["검토"] is False
    assert all(x["과목"] for x in rows)  # 빈 과목 행 없음


def test_vehicle_depr_excess_in_reserve():
    """업무용승용차 감가상각 한도초과는 유보로 을표에 반영."""
    rows = build_reserve_status(
        prior_reserves=[],
        tax_result=_r(vehicle_depr_excess=3_000_000),
    )
    v = _row(rows, "업무용승용차 감가상각 한도초과")
    assert v["기말"] == 3_000_000 and v["처분"] == "유보"


def test_reserve_totals():
    rows = build_reserve_status(
        prior_reserves=[],
        tax_result=_r(bad_debt_excess=12_000_000, pension_deduction=2_000_000),
    )
    t = reserve_totals(rows)
    assert t["유보_기말"] == 12_000_000
    assert t["△유보_기말"] == 2_000_000
    assert t["순유보_기말"] == 10_000_000
