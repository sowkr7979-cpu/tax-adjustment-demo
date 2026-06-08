"""기부금 한도 단위 테스트 — 법§24②2호·③2호·⑤·⑥ (law.go.kr 원문 기준)."""
from src.rules.donation import (
    calc_donation, eligible_donation_carryforward, roll_forward,
)


def test_donation_basic_limits():
    """이월결손금 없는 기본 한도: 특례 50%, 일반 (기준소득−특례손금)×10%."""
    r = calc_donation(
        special_donation=100_000_000,
        general_donation=50_000_000,
        nondesignated_donation=10_000_000,
        adjusted_income=200_000_000,   # 기준소득금액
    )
    # 특례 한도 = 200M×50% = 100M → 초과 0, 손금산입 100M
    assert r.special_limit == 100_000_000
    assert r.special_excess == 0
    # 일반 base = 200M − 100M(특례손금) = 100M → 한도 10M → 50M 중 40M 초과
    assert r.general_limit == 10_000_000
    assert r.general_excess == 40_000_000
    # 비지정 전액 + 일반 초과
    assert r.total_disallowed == 40_000_000 + 10_000_000


def test_donation_deducts_carryforward_loss():
    """기준소득금액에서 이월결손금(법§13①1호)을 차감한 base로 한도 산정."""
    r = calc_donation(
        special_donation=100_000_000,
        general_donation=50_000_000,
        nondesignated_donation=10_000_000,
        adjusted_income=200_000_000,
        carryforward_loss_deduction=50_000_000,
    )
    # limit_base = 200M − 50M = 150M
    # 특례 한도 = 75M → 100M 중 25M 초과, 손금산입 75M
    assert r.special_limit == 75_000_000
    assert r.special_excess == 25_000_000
    # 일반 base = 150M − 75M = 75M → 한도 7.5M → 50M 중 42.5M 초과
    assert r.general_limit == 7_500_000
    assert r.general_excess == 42_500_000
    assert r.total_disallowed == 25_000_000 + 42_500_000 + 10_000_000


def test_donation_social_enterprise_general_rate():
    """사회적기업은 일반기부금 한도율 20%."""
    r = calc_donation(
        special_donation=0,
        general_donation=50_000_000,
        nondesignated_donation=0,
        adjusted_income=100_000_000,
        is_social_enterprise=True,
    )
    # 일반 base = 100M → 한도 20M → 50M 중 30M 초과
    assert r.general_limit == 20_000_000
    assert r.general_excess == 30_000_000


def test_donation_carryforward_priority():
    """이월기부금 우선공제 (법§24⑥) — 이월분이 당기 한도를 먼저 소진, 미공제분은 차기 이월."""
    r = calc_donation(
        special_donation=0,
        general_donation=0,
        nondesignated_donation=0,
        adjusted_income=100_000_000,
        prior_special_carryforward=60_000_000,
    )
    # 특례 한도 50M, 이월 특례 60M → 50M 우선공제(손금산입), 10M 미공제(차기 이월)
    assert r.special_limit == 50_000_000
    assert r.special_carryover_used == 50_000_000
    assert r.special_carryover_remaining == 10_000_000
    assert r.special_excess == 0   # 당기 지출분이 없으므로 당기 한도초과는 0
    assert r.carryforward_deduction == 50_000_000   # 손금산입(차감조정)
    assert r.total_disallowed == 0


def test_donation_carryover_then_current():
    """이월분 우선공제 후 남은 한도로 당기분 공제, 당기 초과만 손금불산입."""
    r = calc_donation(
        special_donation=30_000_000,
        general_donation=0,
        nondesignated_donation=0,
        adjusted_income=100_000_000,       # 특례 한도 50M
        prior_special_carryforward=40_000_000,
    )
    # 이월 40M 우선공제 → 남은 한도 10M → 당기 30M 중 10M 공제, 20M 초과
    assert r.special_carryover_used == 40_000_000
    assert r.special_carryover_remaining == 0
    assert r.special_excess == 20_000_000        # 당기 한도초과 → 차기 이월·손금불산입
    assert r.carryforward_deduction == 40_000_000
    assert r.total_disallowed == 20_000_000


def test_eligible_donation_carryforward_expiry_and_sort():
    """공제기한 10년 초과분 소멸 + 종류 필터 + 발생연도 오름차순(선발생 우선)."""
    items = [
        {"year": 2015, "type": "특례", "amount": 5_000_000},   # 2025 기준 10년 → 유효
        {"year": 2014, "type": "특례", "amount": 3_000_000},   # 11년 경과 → 소멸
        {"year": 2020, "type": "특례", "amount": 7_000_000},
        {"year": 2021, "type": "일반", "amount": 9_000_000},   # 종류 다름
    ]
    out = eligible_donation_carryforward(items, 2025, "특례")
    assert [x["year"] for x in out] == [2015, 2020]            # 2014 소멸, 정렬됨
    assert sum(x["amount"] for x in out) == 12_000_000


def test_roll_forward_oldest_first_and_current_excess():
    """차기 이월 = 미공제 이월분(선발생분부터 소진) + 당기 한도초과분."""
    eligible = [
        {"year": 2018, "amount": 10_000_000},
        {"year": 2019, "amount": 10_000_000},
    ]
    # 이월 20M 중 12M 공제 → 2018 전액 소진, 2019 중 2M 소진 → 2019 잔액 8M 이월
    nxt = roll_forward(eligible, used=12_000_000, current_excess=5_000_000,
                       current_year=2025, kind="특례")
    assert nxt == [
        {"year": 2019, "type": "특례", "amount": 8_000_000},
        {"year": 2025, "type": "특례", "amount": 5_000_000},
    ]
