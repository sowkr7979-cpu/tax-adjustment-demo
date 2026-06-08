"""익금산입 항목 계산 — 인정이자(법령§89), 간주임대료(법법§56) 등."""
from dataclasses import dataclass

from src.utils.constants import get_prime_rate


@dataclass
class DeemedInterestResult:
    loan_balance: int
    prime_rate: float
    months: int
    deemed_interest: int
    actual_interest: int
    inclusion_amount: int   # 익금산입액


@dataclass
class PartyInterest:
    """거래상대방별 인정이자 계산 (별지 제19호 가지급금등의인정이자조정명세서 구조)."""
    name: str
    jeoksu: int             # 가지급금 적수 (가수금 상계 후, 영§53③)
    deemed: int             # 인정이자 = 적수 × 이자율 ÷ 365
    actual: int             # 수취 약정이자 (이자수익 분개 자동 매칭)
    diff: int               # 차액 (인정이자 − 약정이자)
    applied: bool           # 영§88③: 차액 ≥ 3억 또는 시가의 5% 이상일 때만 부당행위 적용
    inclusion: int          # 익금산입액


@dataclass
class DeemedInterestByPartyResult:
    rate: float
    days: int
    parties: list[PartyInterest]
    inclusion_amount: int   # 익금산입 합계 (상대방별 양수 합 — 상대방 간 상계 없음)


def calc_deemed_interest_by_party(
    parties: list[tuple[str, int, int]],   # [(상대방, 가지급금 적수, 약정이자)]
    *,
    rate: float,
    days: int = 365,
) -> DeemedInterestByPartyResult:
    """가지급금 인정이자 — 거래상대방별 계산 (법§52, 영§88①6호·③, 영§89③⑤).

    law.go.kr 원문 확인:
      영§89⑤: 시가와의 차액을 익금산입
      영§88③: 6호(금전 대여)는 차액이 3억원 이상이거나 시가의 5% 이상인 경우에 한해 적용
      적수·가수금 상계는 동일인(상대방)별 — 상대방 간 통산하지 않는다
    """
    out: list[PartyInterest] = []
    total = 0
    for name, jeoksu, actual in parties:
        deemed = int(jeoksu * rate / days) if days else 0
        diff = deemed - actual
        applied = diff > 0 and (diff >= 300_000_000 or diff >= deemed * 0.05)
        inclusion = diff if applied else 0
        total += inclusion
        out.append(PartyInterest(
            name=name, jeoksu=jeoksu, deemed=deemed, actual=actual,
            diff=diff, applied=applied, inclusion=inclusion,
        ))
    return DeemedInterestByPartyResult(
        rate=rate, days=days, parties=out, inclusion_amount=total,
    )


@dataclass
class DebtReliefOffsetResult:
    """자산수증익·채무면제익의 이월결손금 보전 충당액 익금불산입 (법§18 6호)."""
    asset_gift: int             # 자산수증이익 (수익 계상액, 국고보조금 제외)
    debt_forgiveness: int       # 채무면제이익 (수익 계상액)
    carryforward_available: int # 보전 대상 이월결손금 (영§16 — 공제기한 지난 것 포함)
    gross: int                  # 자산수증익 + 채무면제익
    offset: int                 # 보전 충당액 = min(gross, 이월결손금) — 익금불산입(손금산입 △)


def calc_debt_relief_offset(
    *,
    asset_gift: int,
    debt_forgiveness: int,
    carryforward_available: int,
) -> DebtReliefOffsetResult:
    """자산수증익·채무면제익 중 이월결손금 보전 충당액의 익금불산입 (법§18 6호, 영§16).

    law.go.kr 원문 확인 (법§18 6호, efYd=사업연도 종료일):
      "결손금이 발생한 법인이 무상으로 받은 자산의 가액(제36조 국고보조금등 제외)과
       채무의 면제·소멸로 인한 부채의 감소액 중 이월결손금을 보전하는 데에 충당한 금액"은
       익금에 산입하지 아니한다(익금불산입).

    영§16: 보전 대상 이월결손금 = 법§14②의 결손금 중 법§13①1호로 공제되지 않은 금액.
      → 법§13의 공제기한(15년) 적용을 받는 과세표준 공제용 이월결손금과 달리,
        공제기한이 지난 결손금도 보전 대상에 포함된다(자기자본 결손 보전 목적).
      → 따라서 tax_base의 eligible_carryforward_total을 재사용하지 않고
        별도 입력값(carryforward_available)으로 받는다.

    자산수증익·채무면제익은 영업외수익으로 계상되어 이미 당기순이익에 포함되므로,
    세무조정은 보전 충당액의 익금불산입(손금산입 △, 소득처분 '기타')이다.
    보전에 충당할지·얼마를 충당할지는 납세자의 선택이므로 carryforward_available은
    '보전에 충당하는 이월결손금'을 수기 입력으로 받는다.
    """
    gross = max(0, asset_gift) + max(0, debt_forgiveness)
    offset = min(gross, max(0, carryforward_available))
    return DebtReliefOffsetResult(
        asset_gift=max(0, asset_gift),
        debt_forgiveness=max(0, debt_forgiveness),
        carryforward_available=max(0, carryforward_available),
        gross=gross,
        offset=offset,
    )


@dataclass
class DeemedRentalResult:
    deposit: int
    debt: int
    equity: int
    construction_cost: int      # 임대용부동산 건설비상당액 (토지가액 제외, 조특령§132⑥)
    financial_income: int       # 보증금 운용 금융수익 (이자·배당 등)
    bank_rate: float
    applicable: bool            # 적용 대상 여부 (주업 + 차입금 과다)
    reason: str                 # 미적용 사유 / 적용 근거
    inclusion_amount: int


def calc_deemed_interest(
    *,
    loan_balance: int,
    actual_interest: int,
    fiscal_year: int,
    months: int = 12,
    override_rate: float = 0.0,
) -> DeemedInterestResult:
    """특수관계인 가지급금 인정이자 익금산입 (법§52, 영§88①6호, 영§89③).

    영§89③: 시가 = 가중평균차입이자율 원칙. 적용 불가·5년 초과 대여·신고 선택 시
    당좌대출이자율. override_rate > 0이면 가중평균차입이자율로 사용,
    0이면 당좌대출이자율(국세청 고시)을 적용한다.
    """
    rate = override_rate if override_rate > 0 else get_prime_rate(fiscal_year)
    deemed = int(loan_balance * rate * months / 12)
    inclusion = max(0, deemed - actual_interest)
    return DeemedInterestResult(
        loan_balance=loan_balance,
        prime_rate=rate,
        months=months,
        deemed_interest=deemed,
        actual_interest=actual_interest,
        inclusion_amount=inclusion,
    )


def calc_deemed_rental(
    *,
    deposit: int,
    debt: int,
    equity: int,
    bank_rate: float,
    is_rental_main: bool = True,
    construction_cost: int = 0,
    financial_income: int = 0,
    deposit_jeoksu: int = 0,
    debt_jeoksu: int = 0,
    construction_jeoksu: int = 0,
    days: int = 365,
) -> DeemedRentalResult:
    """임대보증금 등의 간주익금 (조특법§138, 조특령§132 — law.go.kr 확인).

    적용 요건 (조특법§138①, 조특령§132①·③):
      1. 부동산임대업 주업 — 자산총액 중 임대사업 자산가액 50% 이상
      2. 차입금 과다 — 차입금 '적수' > 자기자본 '적수' × 2 (조특령§132①)

    산식 (조특령§132⑤) — 적수(積數) 기준:
      익금가산액 = (보증금등 적수 − 건설비상당액 적수) × 1/365 × 정기예금이자율
                   − 임대사업 금융수익 (이자·할인료·배당금 등)
      음수이면 0. 건설비상당액은 토지가액 제외 (조특령§132⑥).
      "적수의 계산은 매월말 현재의 잔액에 경과일수를 곱하여 계산할 수 있다"

    deposit_jeoksu·debt_jeoksu·construction_jeoksu: 분개장에서 일별 잔액으로 계산한 적수.
      0이면 기말잔액 × 일수로 근사 (잔액 변동이 없다고 가정).
    자기자본 적수는 기말 자기자본 × 일수로 근사 (변동 시 조특령§132① 후단 수동 재계산).
    """
    _dep_j = deposit_jeoksu or deposit * days
    _debt_j = debt_jeoksu or debt * days
    _eq_j = equity * days
    _con_j = construction_jeoksu or construction_cost * days

    if not is_rental_main:
        return DeemedRentalResult(
            deposit=deposit, debt=debt, equity=equity,
            construction_cost=construction_cost, financial_income=financial_income,
            bank_rate=bank_rate, applicable=False,
            reason="부동산임대업 주업 아님 (조특법§138① — 자산총액 중 임대자산 50% 미만)",
            inclusion_amount=0,
        )
    if _debt_j <= _eq_j * 2:
        return DeemedRentalResult(
            deposit=deposit, debt=debt, equity=equity,
            construction_cost=construction_cost, financial_income=financial_income,
            bank_rate=bank_rate, applicable=False,
            reason=f"차입금 적수({_debt_j:,}) ≤ 자기자본 적수({_eq_j:,})×2 — "
                   f"차입금 과다 요건 미충족 (조특령§132①)",
            inclusion_amount=0,
        )
    gross = int(max(0, _dep_j - _con_j) * bank_rate / days) if days else 0
    inclusion = max(0, gross - financial_income)
    return DeemedRentalResult(
        deposit=deposit, debt=debt, equity=equity,
        construction_cost=construction_cost, financial_income=financial_income,
        bank_rate=bank_rate, applicable=True,
        reason="부동산임대업 주업 + 차입금 적수 > 자기자본 적수×2 (조특법§138 적용)",
        inclusion_amount=inclusion,
    )
