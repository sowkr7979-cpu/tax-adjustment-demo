"""기타 세무조정 — 벌과금(법§21), 임원 상여·퇴직(법§26) 등."""


def calc_penalty(penalty_total: int) -> int:
    """벌과금·과태료: 전액 손금불산입 (법§21)."""
    return penalty_total


def calc_officer_bonus_excess(
    *,
    paid_bonus: int,
    approved_limit: int,
) -> int:
    """임원 상여금 정관·주총 한도 초과분 손금불산입 (법§26)."""
    return max(0, paid_bonus - approved_limit)


def calc_officer_retirement_excess(
    *,
    paid_amount: int,
    tenure_years: float,
    last_salary: int,
    allowance_rate: float = 0.1,
) -> int:
    """
    임원 퇴직금 한도초과 계산.
    한도 = 직전 1년간 총급여액 × 1/10 × 근속연수
    """
    limit = int(last_salary * allowance_rate * tenure_years)
    return max(0, paid_amount - limit)


def calc_unfair_transaction_general(*, market_value: int, transaction_value: int) -> int:
    """부당행위계산 부인액(001563/제52조, 003608/제88조·제89조).

    고가매입·저가양도 등 일반 부당행위는 시가와 거래가액의 차액을 이전된 이익으로 본다.
    영§88③의 3억원·5% 게이트는 건별 Q&A 스펙에서 먼저 적용한다.
    """
    return abs(int(market_value or 0) - int(transaction_value or 0))


def calc_stock_based_compensation_excess(*, booked_expense: int, deductible_amount: int) -> int:
    """주식매수선택권·주식기준보상 손금불산입(001584/제13조의2, 004920/제19조).

    조특법상 손금산입 요건·한도 충족액을 회계사가 확정 입력하면, 장부 비용 중
    그 금액을 초과한 부분을 손금불산입한다.
    """
    return max(0, int(booked_expense or 0) - int(deductible_amount or 0))


def calc_construction_progress_adjustment(*, tax_revenue: int, book_revenue: int) -> int:
    """작업진행률 수익인식 차이(003608/제69조).

    세무상 작업진행률 기준 수익과 장부 수익의 차액을 반환한다.
    양수는 익금산입, 음수는 익금불산입 대상이다.
    """
    return int(tax_revenue or 0) - int(book_revenue or 0)


def calc_treasury_stock_disposal(*, booked_gain: int, booked_loss: int) -> tuple[int, int]:
    """자기주식처분손익 조정(001563/제15조·제17조).

    반환: (익금불산입할 처분이익, 손금불산입할 처분손실). 자기주식 처분은 자본거래로
    보아 손익 계상분을 세무조정한다.
    """
    return max(0, int(booked_gain or 0)), max(0, int(booked_loss or 0))


def calc_proper_purpose_reserve(*, booked_reserve: int, deductible_limit: int) -> tuple[int, int]:
    """고유목적사업준비금 조정(001563/제29조).

    반환: (손금산입액, 한도초과 손금불산입액). 비영리내국법인의 법정 손금산입 한도는
    수익사업 소득·이자배당 등 구성에 따라 달라 회계사가 확정 입력한다.
    """
    booked = max(0, int(booked_reserve or 0))
    limit = max(0, int(deductible_limit or 0))
    return min(booked, limit), max(0, booked - limit)
