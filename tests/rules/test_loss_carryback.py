"""결손금 소급공제 환급세액 계산 테스트 (법§72, 영§110)."""
from datetime import date
from types import SimpleNamespace

from src.rules.loss_carryback import (
    compute_loss_carryback, compute_loss_carryback_from_manual,
)


def _base(**kw):
    args = dict(
        is_sme=True,
        current_loss=100_000_000,
        prior_tax_base=300_000_000,
        prior_gross_tax=37_000_000,      # 300M: 200M*0.19 누진공제 20M → 37,000,000 (2023 테이블)
        prior_credit_exemption=0,
        prior_fiscal_start=date(2024, 1, 1),
    )
    args.update(kw)
    return compute_loss_carryback(**args)


def test_basic_refund():
    # 적용결손금 100M → 2호 = (300M-100M)=200M × 9% = 18,000,000
    # 환급 = 37,000,000 - 18,000,000 = 19,000,000, 한도 37,000,000 → 19,000,000
    r = _base()
    assert r.eligible
    assert r.applied_loss == 100_000_000
    assert r.step1 == 37_000_000
    assert r.step2 == 18_000_000
    assert r.refund == 19_000_000
    assert not r.limit_binds
    assert not r.needs_manual_step2


def test_limit_binds():
    # 직전 공제·감면세액이 커서 한도가 환급액을 제한
    r = _base(prior_credit_exemption=30_000_000)
    assert r.refund_limit == 7_000_000          # 37M - 30M
    assert r.refund == 7_000_000                # 19M(1호-2호) > 7M 한도
    assert r.limit_binds


def test_not_sme_ineligible():
    r = _base(is_sme=False)
    assert not r.eligible
    assert r.refund == 0
    assert any("중소기업" in x for x in r.reasons)


def test_not_filed_on_time_ineligible():
    r = _base(both_filed_on_time=False)
    assert not r.eligible
    assert any("기한내 신고" in x for x in r.reasons)


def test_no_current_loss_ineligible():
    r = _base(current_loss=0)
    assert not r.eligible


def test_prior_no_tax_ineligible():
    # 직전 산출세액 0 → 한도 0 → 환급 없음
    r = _base(prior_gross_tax=0)
    assert not r.eligible
    assert r.refund == 0


def test_carryback_loss_capped_by_prior_tax_base():
    # 당기 결손금 > 직전 과세표준 → 소급공제 결손금은 직전 과표로 상한 (영§110⑤)
    r = _base(current_loss=500_000_000, prior_tax_base=300_000_000)
    assert r.max_carryback_loss == 300_000_000
    # 적용결손금 300M → 2호 = (300M-300M)=0 × 세율 = 0 → 환급 = 37M, 한도 37M
    assert r.applied_loss == 300_000_000
    assert r.step2 == 0
    assert r.refund == 37_000_000


def test_requested_loss_partial():
    # 신청 결손금을 상한 미만으로 → 잔여는 이월 안내
    r = _base(requested_loss=50_000_000)
    assert r.applied_loss == 50_000_000
    # 2호 = (300M-50M)=250M → 200M*0.19-20M + ... 250M은 200M초과구간: 250M*0.19-20M=27.5M
    assert r.step2 == int(250_000_000 * 0.19) - 20_000_000
    assert any("이월공제" in x for x in r.reasons)


def test_prior_rate_table_missing_needs_manual():
    # 직전 사업연도 2022 → 세율테이블 미수록 → 보수적 0 환급 + 회계사 입력 요구
    r = _base(prior_fiscal_start=date(2022, 1, 1))
    assert r.eligible          # 요건은 충족하나
    assert r.needs_manual_step2
    assert r.refund == 0
    assert any("세율테이블" in x for x in r.reasons)


def test_prior_rate_table_missing_with_override():
    # 회계사가 2호를 직접 입력하면 그 값으로 환급 계산
    r = _base(prior_fiscal_start=date(2022, 1, 1), manual_step2_override=20_000_000)
    assert not r.needs_manual_step2
    assert r.step2 == 20_000_000
    assert r.refund == 17_000_000     # 37M - 20M


# ── 수기입력 인자 포장 헬퍼 (calc/output 3곳 중복 제거) ──────────────────────

def _mi(**kw):
    """ManualInput 덕타이핑 스텁."""
    base = dict(
        loss_carryback_prior_tax_base=300_000_000,
        loss_carryback_prior_gross_tax=37_000_000,
        loss_carryback_prior_credit=0,
        loss_carryback_requested_loss=0,        # 0 → 상한 전액
        loss_carryback_both_filed=True,
        loss_carryback_step2_override=0,        # 0 → 미입력
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_from_manual_matches_direct_call():
    """헬퍼가 직접 호출과 동일 결과 — 직전 개시일은 당기 −1년, requested/override 0은 None 변환."""
    r = compute_loss_carryback_from_manual(
        _mi(), is_sme=True, fy_start=date(2025, 1, 1), current_loss=100_000_000)
    direct = compute_loss_carryback(
        is_sme=True, current_loss=100_000_000,
        prior_tax_base=300_000_000, prior_gross_tax=37_000_000, prior_credit_exemption=0,
        prior_fiscal_start=date(2024, 1, 1),
        requested_loss=None, both_filed_on_time=True, manual_step2_override=None,
    )
    assert r == direct
    assert r.refund == 19_000_000


def test_from_manual_leap_day_prior_start():
    """2/29 개시 사업연도 → 직전 개시일을 평년으로 보정(ValueError 회피)."""
    r = compute_loss_carryback_from_manual(
        _mi(), is_sme=True, fy_start=date(2024, 2, 29), current_loss=100_000_000)
    assert r.eligible        # 직전 개시일 계산이 예외 없이 처리됨
