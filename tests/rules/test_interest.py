"""지급이자 손금불산입·업무용승용차 단위 테스트."""
import pytest
from src.rules.interest import calc_interest_disallowance
from src.rules.vehicle import calc_vehicle


# ── 지급이자 손금불산입 ───────────────────────────────────────────────────────

def test_unknown_creditor_full():
    """채권자불분명 이자 전액 손금불산입."""
    r = calc_interest_disallowance(
        total_interest=10_000_000,
        unknown_creditor_interest=2_000_000,
        construction_interest=0,
        non_business_asset=0,
        total_asset=100_000_000,
    )
    assert r.unknown_creditor_disallowed == 2_000_000
    assert r.non_business_disallowed == 0


def test_construction_interest_capitalized():
    """건설자금이자는 별도 자본화 (총 손금불산입에 포함)."""
    r = calc_interest_disallowance(
        total_interest=10_000_000,
        unknown_creditor_interest=0,
        construction_interest=3_000_000,
        non_business_asset=10_000_000,
        total_asset=100_000_000,
    )
    # 4호 기준이자 = 10M - 0 - 3M = 7M
    assert r.construction_capitalized == 3_000_000
    assert r.non_business_disallowed == int(7_000_000 * 0.1)
    assert r.total_disallowed == 3_000_000 + int(7_000_000 * 0.1)


def test_non_business_ratio():
    r = calc_interest_disallowance(
        total_interest=20_000_000,
        unknown_creditor_interest=0,
        construction_interest=0,
        non_business_asset=30_000_000,
        total_asset=100_000_000,
    )
    assert r.non_business_ratio == pytest.approx(0.3, rel=1e-5)
    assert r.non_business_disallowed == int(20_000_000 * 0.3)


# ── 업무용승용차 ─────────────────────────────────────────────────────────────

def test_no_insurance_full_disallowed():
    r = calc_vehicle(
        vehicle_id="V001",
        depreciation=5_000_000, other_expense=2_000_000,
        business_use_ratio=0.8, has_insurance=False, has_logbook=True,
    )
    assert r.total_disallowed == 7_000_000


def test_no_logbook_under_15m_full_ratio():
    """운행기록부 미작성 + 관련비용 1,500만원 이하 → 업무사용비율 100% (영§50의2⑦1호)."""
    r = calc_vehicle(
        vehicle_id="V002",
        depreciation=10_000_000, other_expense=2_000_000,
        business_use_ratio=0.9, has_insurance=True, has_logbook=False,
    )
    assert r.business_use_ratio == 1.0


def test_no_logbook_over_15m_ratio():
    """운행기록부 미작성 + 관련비용 3,000만원 → 비율 = 1,500만/3,000만 = 50% (영§50의2⑦2호)."""
    r = calc_vehicle(
        vehicle_id="V002b",
        depreciation=25_000_000, other_expense=5_000_000,
        business_use_ratio=0.9, has_insurance=True, has_logbook=False,
    )
    assert r.business_use_ratio == pytest.approx(0.5, rel=1e-9)


def test_specified_corp_limits():
    """특정법인: 감가상각 한도 400만·전액인정 한도 500만 (영§50의2⑮)."""
    r = calc_vehicle(
        vehicle_id="V002c",
        depreciation=10_000_000, other_expense=0,
        business_use_ratio=1.0, has_insurance=True, has_logbook=True,
        is_specified_corp=True,
    )
    assert r.depreciation_limit == 4_000_000
    assert r.depreciation_limit_excess == 6_000_000

    r2 = calc_vehicle(
        vehicle_id="V002d",
        depreciation=6_000_000, other_expense=0,
        business_use_ratio=1.0, has_insurance=True, has_logbook=False,
        is_specified_corp=True,
    )
    # 관련비용 600만 > 500만 → 비율 = 500/600
    assert r2.business_use_ratio == pytest.approx(5 / 6, rel=1e-9)


def test_depreciation_over_8m_deferred():
    """감가상각비 800만원 초과분 이월."""
    r = calc_vehicle(
        vehicle_id="V003",
        depreciation=20_000_000, other_expense=1_000_000,
        business_use_ratio=1.0, has_insurance=True, has_logbook=True,
    )
    # 업무사용 감가상각 = 20M, 한도 = 8M → 이월 12M
    assert r.depreciation_limit_excess == 12_000_000


def test_other_expense_no_limit():
    """기타비용은 업무사용비율만 적용, 별도 한도 없음."""
    r = calc_vehicle(
        vehicle_id="V004",
        depreciation=0, other_expense=5_000_000,
        business_use_ratio=0.6, has_insurance=True, has_logbook=True,
    )
    assert r.business_other_expense_allowed == int(5_000_000 * 0.6)
    # 개인사용분(40%)만 손금불산입
    assert r.personal_use_disallowed == int(5_000_000 * 0.4)
