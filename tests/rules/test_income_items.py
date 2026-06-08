"""익금산입·익금불산입 항목 단위 테스트 — 인정이자(상대방별)·간주임대료·법§18 6호 보전충당."""
import pytest
from src.rules.income_items import (
    calc_deemed_interest_by_party,
    calc_debt_relief_offset,
)


# ── 법§18 6호: 자산수증익·채무면제익 이월결손금 보전 충당액 익금불산입 ──────────

def test_debt_relief_full_offset_when_carryforward_exceeds_gross():
    """이월결손금 ≥ 자산수증익+채무면제익 → 전액 보전 충당(전액 익금불산입)."""
    r = calc_debt_relief_offset(
        asset_gift=30_000_000,
        debt_forgiveness=20_000_000,
        carryforward_available=100_000_000,
    )
    assert r.gross == 50_000_000
    assert r.offset == 50_000_000  # 전액 보전


def test_debt_relief_partial_offset_when_carryforward_smaller():
    """이월결손금 < 이익 → 이월결손금 한도까지만 보전(나머지는 과세)."""
    r = calc_debt_relief_offset(
        asset_gift=40_000_000,
        debt_forgiveness=30_000_000,
        carryforward_available=25_000_000,
    )
    assert r.gross == 70_000_000
    assert r.offset == 25_000_000  # 이월결손금 한도


def test_debt_relief_zero_when_no_carryforward():
    """보전 대상 이월결손금이 없으면 익금불산입액 0 (전액 과세)."""
    r = calc_debt_relief_offset(
        asset_gift=50_000_000,
        debt_forgiveness=0,
        carryforward_available=0,
    )
    assert r.offset == 0


def test_debt_relief_negative_inputs_clamped():
    """음수 입력은 0으로 보정 — 손금산입액이 음수가 되지 않는다."""
    r = calc_debt_relief_offset(
        asset_gift=-10_000_000,
        debt_forgiveness=10_000_000,
        carryforward_available=-5_000_000,
    )
    assert r.gross == 10_000_000
    assert r.offset == 0


# ── 법§18 4·5호: 국세환급금이자·부가세 매출세액 익금불산입 (total_deduct 반영) ──

def test_section18_4_5_in_total_deduct():
    """국세환급금이자(4호)·부가세 매출세액(5호) 익금불산입이 total_deduct에 합산된다."""
    from datetime import date
    from src.utils.models import TaxAdjustmentResult
    r = TaxAdjustmentResult(
        fiscal_year_start=date(2024, 1, 1),
        fiscal_year_end=date(2024, 12, 31),
        is_sme=True,
        refund_interest_excluded=1_500_000,
        vat_output_excluded=500_000,
    )
    assert r.total_deduct == 2_000_000


# ── 영§88③: 가지급금 인정이자 거래상대방별 (상대방 간 통산 금지) ────────────────

def test_deemed_interest_per_party_no_netting():
    """상대방별 양수 익금산입만 합산 — 한 상대방의 초과수취가 다른 상대방을 상쇄하지 않음."""
    res = calc_deemed_interest_by_party(
        [
            ("A", 36_500_000_000, 0),        # 적수 큼, 약정이자 0 → 인정이자 전액
            ("B", 3_650_000_000, 100_000_000),  # 약정이자 과다 → 차액 음수(상쇄 대상 아님)
        ],
        rate=0.046,
        days=365,
    )
    a = next(p for p in res.parties if p.name == "A")
    b = next(p for p in res.parties if p.name == "B")
    assert a.inclusion > 0
    assert b.inclusion == 0                  # 음수 차액은 0 처리
    assert res.inclusion_amount == a.inclusion  # B가 A를 통산하지 않음


def test_deemed_interest_threshold_not_applied_below_5pct():
    """영§88③: 차액이 3억 미만이고 시가의 5% 미만이면 부당행위 미적용(inclusion 0)."""
    # jeoksu 설정으로 deemed ≈ 10억, 약정이자로 차액을 4천만(시가의 5%=5천만 미만, 3억 미만)으로
    res = calc_deemed_interest_by_party(
        [("C", 7_934_782_608_696, 960_000_000)],
        rate=0.046,
        days=365,
    )
    c = res.parties[0]
    assert c.deemed == pytest.approx(1_000_000_000, abs=2_000)
    assert 0 < c.diff < c.deemed * 0.05   # 차액이 시가의 5% 미만
    assert c.diff < 300_000_000           # 3억 미만
    assert c.applied is False
    assert c.inclusion == 0               # 미적용 → 익금산입 0


def test_deemed_interest_threshold_applied_at_5pct_or_more():
    """차액이 시가의 5% 이상이면 적용 — 차액 전액 익금산입."""
    res = calc_deemed_interest_by_party(
        [("D", 7_934_782_608_696, 0)],   # 약정이자 0 → 차액=시가 전액(5% 이상)
        rate=0.046,
        days=365,
    )
    d = res.parties[0]
    assert d.applied is True
    assert d.inclusion == d.deemed
