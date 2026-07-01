"""기부금 한도 계산 — 법인세법 제24조 (이월분 우선공제 포함, 법§24⑤⑥)."""
from dataclasses import dataclass


@dataclass
class DonationResult:
    special_donation: int
    general_donation: int
    nondesignated_donation: int
    adjusted_income: int
    special_limit: int
    general_limit: int
    # 이월분 당기 공제(손금산입, 차감조정) — 법§24⑥ 우선공제
    special_carryover_used: int
    general_carryover_used: int
    # 당기분 한도초과 (손금불산입·가산, 차기 이월 대상)
    special_excess: int
    general_excess: int
    # 미공제 이월분 (한도 부족으로 당기 공제 못 한 이월액 — 차기 계속 이월)
    special_carryover_remaining: int
    general_carryover_remaining: int
    nondesignated_disallowed: int
    # 합계 — calc 연결용
    carryforward_deduction: int   # 이월분 당기 손금산입 합계 (→ total_deduct, 처분 "기타")
    total_disallowed: int         # 당기 한도초과 + 비지정 (→ donation_excess, 가산)


def calc_donation(
    *,
    special_donation: int,
    general_donation: int,
    nondesignated_donation: int,
    adjusted_income: int,
    carryforward_loss_deduction: int = 0,
    prior_special_carryforward: int = 0,
    prior_general_carryforward: int = 0,
    is_social_enterprise: bool = False,
) -> DonationResult:
    """기부금 한도 — 법§24②2호·③2호·⑤·⑥ (law.go.kr 원문 확인, efYd=2024-12-31).

    adjusted_income: 기준소득금액 = 차가감소득금액 + 특례기부금 + 일반기부금
        (= 특례·일반기부금 손금산입 전 해당 사업연도 소득금액, 법§24②2호)
    carryforward_loss_deduction: 법§13①1호 이월결손금 공제액 — 한도 base에서 차감
    prior_special_carryforward / prior_general_carryforward:
        전기 이월 기부금 잔액(법§24⑤, 10년 — 공제기한 내 합계). 공제기한 소멸 필터링은 호출부.
    is_social_enterprise: 사회적기업이면 일반기부금 한도율 20% (그 외 10%, 법§24③2호)

    법§24⑥ 우선공제: 이월된 금액을 당기 지출분보다 **먼저** 손금산입한다.
      따라서 ①이월분을 한도까지 우선 공제(손금산입·차감) → ②남은 한도로 당기분 공제
      → ③당기분 중 한도초과만 손금불산입(가산·차기 이월).
    """
    # 한도 기준 = 기준소득금액 − 이월결손금 (법§24②2호·③2호)
    limit_base = max(0, adjusted_income - carryforward_loss_deduction)

    # ── 특례기부금: limit_base × 50% ──
    special_limit = int(limit_base * 0.5)
    # ① 이월분 우선공제 (법§24⑥)
    special_carryover_used = min(prior_special_carryforward, special_limit)
    special_carryover_remaining = prior_special_carryforward - special_carryover_used
    # ② 남은 한도로 당기분 공제
    special_room = special_limit - special_carryover_used
    special_current_allowed = min(special_donation, special_room)
    # ③ 당기 한도초과 (손금불산입·차기 이월)
    special_excess = special_donation - special_current_allowed
    special_total_allowed = special_carryover_used + special_current_allowed

    # ── 일반기부금: (limit_base − 특례 손금산입액) × 10% (사회적기업 20%) ──
    general_base = max(0, limit_base - special_total_allowed)
    general_rate = 0.20 if is_social_enterprise else 0.10
    general_limit = int(general_base * general_rate)
    general_carryover_used = min(prior_general_carryforward, general_limit)
    general_carryover_remaining = prior_general_carryforward - general_carryover_used
    general_room = general_limit - general_carryover_used
    general_current_allowed = min(general_donation, general_room)
    general_excess = general_donation - general_current_allowed

    return DonationResult(
        special_donation=special_donation,
        general_donation=general_donation,
        nondesignated_donation=nondesignated_donation,
        adjusted_income=adjusted_income,
        special_limit=special_limit,
        general_limit=general_limit,
        special_carryover_used=special_carryover_used,
        general_carryover_used=general_carryover_used,
        special_excess=special_excess,
        general_excess=general_excess,
        special_carryover_remaining=special_carryover_remaining,
        general_carryover_remaining=general_carryover_remaining,
        nondesignated_disallowed=nondesignated_donation,
        carryforward_deduction=special_carryover_used + general_carryover_used,
        total_disallowed=special_excess + general_excess + nondesignated_donation,
    )


# 기부금 이월 공제기한 (법§24⑤): 발생 사업연도 다음 사업연도부터 10년 이내.
DONATION_CARRYFORWARD_YEARS = 10


def eligible_donation_carryforward(
    items: list[dict],
    fiscal_year_end_year: int,
    kind: str,
) -> list[dict]:
    """공제기한(10년) 내 이월 기부금을 발생연도 오름차순(선발생 우선)으로 반환.

    items: [{year, type('특례'|'일반'), amount}]
    kind: '특례' 또는 '일반'
    법§24⑤ — 발생연도 Y의 한도초과액은 Y+1 ~ Y+10 사업연도에 공제. (fy_end.year − Y) > 10 이면 소멸.
    """
    out = [
        {"year": int(it["year"]), "amount": int(it["amount"])}
        for it in (items or [])
        if str(it.get("type")) == kind
        and it.get("year") and it.get("amount")
        and (fiscal_year_end_year - int(it["year"])) <= DONATION_CARRYFORWARD_YEARS
    ]
    return sorted(out, key=lambda x: x["year"])


def donation_carryforward_schedule(
    carryforwards: list[dict],
    fiscal_year_end_year: int,
    special_used: int,
    general_used: int,
) -> list[dict]:
    """발생연도별 이월 기부금 명세 — 기부금조정명세서(별지 제21호) 이월명세 섹션용.

    반환: [{year, type, opening, used, expired, carryover}] (발생연도 오름차순, 종류별).
      opening   전기말 이월잔액 (당기초)
      used      당기 손금산입 (이월 우선공제, 선발생분부터 — 법§24⑥)
      expired   당기 소멸 (공제기한 10년 초과 — 법§24⑤). 조용히 사라지지 않게 명시.
      carryover 차기 이월 (= opening − used − expired)
    각 행 항등식: opening = used + expired + carryover. 종류별 Σused = *_used 입력값.
    """
    rows: list[dict] = []
    for kind, used_total in (("특례", special_used), ("일반", general_used)):
        items = sorted(
            [{"year": int(it["year"]), "amount": int(it["amount"])}
             for it in (carryforwards or [])
             if str(it.get("type")) == kind and it.get("year") and it.get("amount")],
            key=lambda x: x["year"],
        )
        remaining_used = used_total
        for it in items:
            yr, amt = it["year"], it["amount"]
            if (fiscal_year_end_year - yr) > DONATION_CARRYFORWARD_YEARS:
                # 공제기한 초과 → 당기 소멸 (공제·이월 불가)
                rows.append({"year": yr, "type": kind, "opening": amt,
                             "used": 0, "expired": amt, "carryover": 0})
                continue
            use = min(amt, remaining_used)
            remaining_used -= use
            rows.append({"year": yr, "type": kind, "opening": amt,
                         "used": use, "expired": 0, "carryover": amt - use})
    return rows


def roll_forward(
    eligible_sorted: list[dict],
    used: int,
    current_excess: int,
    current_year: int,
    kind: str,
) -> list[dict]:
    """차기로 이월할 기부금 잔액 = (미공제 이월분, 선발생분부터 소진) + 당기 한도초과분.

    반환: [{year, type, amount}] — 차기 .taxproj 승계용.
    """
    remaining = used
    nxt: list[dict] = []
    for it in eligible_sorted:
        amt = it["amount"]
        if remaining >= amt:
            remaining -= amt          # 이 연도분 전액 공제됨 → 이월 없음
            continue
        nxt.append({"year": it["year"], "type": kind, "amount": amt - remaining})
        remaining = 0
    if current_excess > 0:
        nxt.append({"year": current_year, "type": kind, "amount": current_excess})
    return nxt
