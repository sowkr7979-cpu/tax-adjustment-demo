"""기부금 한도 단위 테스트 — 법§24②2호·③2호 (law.go.kr 원문 기준)."""
from src.rules.donation import calc_donation


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
    """이월기부금 우선공제 — prior 이월분이 당기 한도를 먼저 소진."""
    r = calc_donation(
        special_donation=0,
        general_donation=0,
        nondesignated_donation=0,
        adjusted_income=100_000_000,
        prior_special_carryforward=60_000_000,
    )
    # 특례 한도 50M, 이월 특례 60M → 10M 초과
    assert r.special_limit == 50_000_000
    assert r.special_excess == 10_000_000
