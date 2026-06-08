"""기부금조정명세서 (별지 제21호서식) — 화면·PDF·Excel 공용 단일 소스.

법§24②③(한도)·⑤(10년 이월)·⑥(이월 우선공제). 3개 섹션:
  ① 한도계산 — 특례 50% / 일반 10%(사회적기업 20%), 이월결손금 차감
  ② 발생연도별 이월명세 — 전기이월·당기공제·당기소멸·차기이월 (감사추적: 소멸 명시 + 검산)
  ③ 당기 지출명세 — 특례/일반/비지정 (합계 분류 기준)

calc.py가 계산 시점에 `proj.tax_adjustments["donation_status"]`로 영속 저장한 dict를 입력으로 받는다.
(빌더가 calc의 순서의존 계산 _base_income을 재현하지 않도록 — calc.py 단일 산출.)
"""
from __future__ import annotations

from src.rules.donation import donation_carryforward_schedule


def build_donation_status(status: dict | None) -> dict | None:
    """기부금조정명세서 섹션 구성. status 없으면 None (기부금 없음).

    status (calc.py 저장): base_income, loss_deduction, special_donation, general_donation,
      nondesignated, special_limit, general_limit, general_rate,
      special_carryover_used, general_carryover_used, special_excess, general_excess,
      carryforward_deduction, total_disallowed, prior_carryforwards[], fy_end_year.
    """
    if not status:
        return None
    s = status
    limit_base = max(0, int(s.get("base_income", 0)) - int(s.get("loss_deduction", 0)))
    _rate_pct = int(round(float(s.get("general_rate", 0.10)) * 100))

    # ① 한도계산
    limit_calc = [
        {"구분": "특례기부금", "지출액": int(s.get("special_donation", 0)),
         "이월 우선공제": int(s.get("special_carryover_used", 0)),
         "손금산입한도": int(s.get("special_limit", 0)), "한도율": "50%",
         "당기 한도초과": int(s.get("special_excess", 0))},
        {"구분": "일반기부금", "지출액": int(s.get("general_donation", 0)),
         "이월 우선공제": int(s.get("general_carryover_used", 0)),
         "손금산입한도": int(s.get("general_limit", 0)), "한도율": f"{_rate_pct}%",
         "당기 한도초과": int(s.get("general_excess", 0))},
    ]

    # ② 발생연도별 이월명세 (전기이월 + 소멸) + 당기 발생분
    schedule = donation_carryforward_schedule(
        s.get("prior_carryforwards", []), int(s.get("fy_end_year", 0)),
        int(s.get("special_carryover_used", 0)), int(s.get("general_carryover_used", 0)),
    )
    for r in schedule:
        r["발생구분"] = "전기이월"
    for kind, excess in (("특례", int(s.get("special_excess", 0))),
                         ("일반", int(s.get("general_excess", 0)))):
        if excess > 0:
            schedule.append({
                "year": int(s.get("fy_end_year", 0)), "type": kind, "opening": 0,
                "used": 0, "expired": 0, "carryover": excess, "발생구분": "당기발생",
            })

    # 검산: 전기이월 각 행 opening == used+expired+carryover, Σused == carryforward_deduction
    prior_rows = [r for r in schedule if r["발생구분"] == "전기이월"]
    row_ok = all(r["opening"] == r["used"] + r["expired"] + r["carryover"] for r in prior_rows)
    used_sum = sum(r["used"] for r in prior_rows)
    used_ok = used_sum == int(s.get("carryforward_deduction", 0))
    expired_total = sum(r["expired"] for r in prior_rows)
    next_total = sum(r["carryover"] for r in schedule)

    # ③ 당기 지출명세 (합계 분류 — 건별 명세는 회계사 별도 첨부)
    current_donations = [
        {"구분": "특례기부금", "금액": int(s.get("special_donation", 0)), "비고": "한도 내 손금산입"},
        {"구분": "일반기부금", "금액": int(s.get("general_donation", 0)), "비고": "한도 내 손금산입"},
        {"구분": "비지정기부금", "금액": int(s.get("nondesignated", 0)), "비고": "전액 손금불산입 (이월 대상 아님)"},
    ]

    return {
        "base_income": int(s.get("base_income", 0)),
        "loss_deduction": int(s.get("loss_deduction", 0)),
        "limit_base": limit_base,
        "limit_calc": limit_calc,
        "carryforward_schedule": schedule,
        "current_donations": current_donations,
        "carryforward_deduction": int(s.get("carryforward_deduction", 0)),
        "total_disallowed": int(s.get("total_disallowed", 0)),
        "expired_total": expired_total,
        "next_carryforward_total": next_total,
        "balance_ok": bool(row_ok and used_ok),
        "balance_note": (
            "검산 일치 (Σ전기말 = Σ당기공제 + Σ당기소멸 + Σ차기이월)"
            if (row_ok and used_ok) else
            f"⚠ 검산 불일치 — 행 항등식 {row_ok}, 당기공제 합계 {used_sum:,} ≠ "
            f"{int(s.get('carryforward_deduction', 0)):,}"
        ),
    }
