"""기부금조정명세서(별지 제21호) 빌더·발생연도별 명세 테스트."""
from src.rules.donation import donation_carryforward_schedule
from src.forms.donation_status import build_donation_status


def test_carryforward_schedule_expiry_and_identity():
    """발생연도별 명세 — 소멸 명시 + 항등식(opening = used + expired + carryover)."""
    prior = [
        {"year": 2019, "type": "특례", "amount": 40_000_000},
        {"year": 2013, "type": "특례", "amount": 5_000_000},   # 2024 기준 11년 → 소멸
        {"year": 2020, "type": "일반", "amount": 3_000_000},
    ]
    rows = donation_carryforward_schedule(prior, 2024, special_used=40_000_000, general_used=3_000_000)
    by = {(r["year"], r["type"]): r for r in rows}
    assert by[(2013, "특례")]["expired"] == 5_000_000      # 소멸 명시
    assert by[(2013, "특례")]["used"] == 0
    assert by[(2019, "특례")]["used"] == 40_000_000
    assert by[(2019, "특례")]["carryover"] == 0
    assert by[(2020, "일반")]["used"] == 3_000_000
    # 항등식
    for r in rows:
        assert r["opening"] == r["used"] + r["expired"] + r["carryover"]


def test_carryforward_schedule_partial_use_oldest_first():
    """이월 우선공제는 선발생분부터 — 한도 부족 시 신발생분이 차기 이월."""
    prior = [
        {"year": 2021, "type": "특례", "amount": 30_000_000},
        {"year": 2022, "type": "특례", "amount": 30_000_000},
    ]
    # used 40M → 2021 전액(30M) + 2022 중 10M, 2022 잔액 20M 차기 이월
    rows = donation_carryforward_schedule(prior, 2024, special_used=40_000_000, general_used=0)
    by = {r["year"]: r for r in rows}
    assert by[2021]["used"] == 30_000_000 and by[2021]["carryover"] == 0
    assert by[2022]["used"] == 10_000_000 and by[2022]["carryover"] == 20_000_000


def _status():
    return {
        "base_income": 100_000_000, "loss_deduction": 0,
        "special_donation": 10_000_000, "general_donation": 0, "nondesignated": 2_000_000,
        "special_limit": 50_000_000, "general_limit": 5_000_000, "general_rate": 0.10,
        "special_carryover_used": 40_000_000, "general_carryover_used": 3_000_000,
        "special_excess": 0, "general_excess": 0,
        "carryforward_deduction": 43_000_000, "total_disallowed": 2_000_000,
        "prior_carryforwards": [
            {"year": 2019, "type": "특례", "amount": 40_000_000},
            {"year": 2013, "type": "특례", "amount": 5_000_000},   # 소멸
            {"year": 2020, "type": "일반", "amount": 3_000_000},
        ],
        "fy_end_year": 2024,
    }


def test_build_donation_status_sections_and_balance():
    """빌더 — 한도계산·이월명세·당기지출 구성 + 검산 일치."""
    out = build_donation_status(_status())
    assert out["limit_base"] == 100_000_000
    # 한도계산
    sp = next(x for x in out["limit_calc"] if x["구분"] == "특례기부금")
    assert sp["손금산입한도"] == 50_000_000 and sp["이월 우선공제"] == 40_000_000
    # 이월명세 소멸 행 존재 + 검산
    assert out["expired_total"] == 5_000_000
    assert out["balance_ok"] is True
    assert out["next_carryforward_total"] == 0
    # 당기지출 — 비지정은 이월 대상 아님 표기
    nd = next(x for x in out["current_donations"] if x["구분"] == "비지정기부금")
    assert "이월 대상 아님" in nd["비고"]


def test_build_donation_status_current_excess_carryforward():
    """당기 한도초과는 '당기발생' 행으로 차기 이월에 포함."""
    s = _status()
    s.update(special_excess=7_000_000, total_disallowed=9_000_000)
    out = build_donation_status(s)
    cur = [r for r in out["carryforward_schedule"] if r["발생구분"] == "당기발생"]
    assert any(r["type"] == "특례" and r["carryover"] == 7_000_000 for r in cur)
    assert out["next_carryforward_total"] == 7_000_000


def test_build_donation_status_none():
    assert build_donation_status(None) is None
