"""업무용승용차 한도 — 차량별 적용(영§50의2) 단위 테스트."""
from src.rules.vehicle import calc_vehicle


def _car(depr, **kw):
    return calc_vehicle(
        vehicle_id=kw.get("vid", "차량"),
        depreciation=depr,
        other_expense=kw.get("other", 0),
        business_use_ratio=kw.get("ratio", 1.0),
        has_insurance=kw.get("insurance", True),
        has_logbook=kw.get("logbook", True),
        is_specified_corp=kw.get("spec", False),
        months=kw.get("months", 12),
    )


def test_depreciation_limit_is_per_vehicle():
    """차량별 800만원 한도 — 2대를 각각 적용하면 합산 풀링보다 부인액이 작다."""
    # 각 차량 감가상각 1,000만 → 차량당 한도초과 200만, 2대 합계 400만
    per_car = _car(10_000_000).depreciation_limit_excess + _car(10_000_000).depreciation_limit_excess
    assert per_car == 4_000_000
    # 만약 합산(2,000만)으로 1대처럼 계산하면 한도초과 1,200만 — 차량별이 정확
    pooled = _car(20_000_000).depreciation_limit_excess
    assert pooled == 12_000_000
    assert per_car < pooled


def test_specified_corp_400_limit():
    """특정법인 감가상각 한도 400만원 (영§50의2⑮)."""
    r = _car(10_000_000, spec=True)
    assert r.depreciation_limit == 4_000_000
    assert r.depreciation_limit_excess == 6_000_000


def test_no_logbook_ratio_per_vehicle():
    """운행기록부 미작성 — 관련비용 ≤ 1,500만이면 100% 업무사용 인정."""
    r = _car(5_000_000, other=5_000_000, logbook=False)
    assert r.business_use_ratio == 1.0
    assert r.personal_use_disallowed == 0


def test_no_insurance_full_disallow():
    """업무전용보험 미가입 → 관련비용 전액 손금불산입 (영§50의2④1호)."""
    r = _car(10_000_000, other=3_000_000, insurance=False)
    assert r.total_disallowed == 13_000_000
