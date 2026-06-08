"""가산세 산정 — 국세기본법 제47조의2~4 (무신고·과소신고·납부지연).

law.go.kr 원문 확인 (국세기본법 ID 001586, efYd=사업연도 종료일):
- §47의2 무신고가산세: 무신고납부세액 × 20%(일반)·40%(부정)·60%(역외부정).
  법인·복식부기의무자는 그 금액과 '수입금액 × 1만분의7(일반)·1만분의14(부정)' 중 큰 금액.
- §47의3 과소신고·초과환급: 부정분 × 40%(역외 60%) + 일반분 × 10%.
- §47의4 납부지연: 미납·과소납부 세액 × 미납일수 × 이자율(국기령 — 현행 1일 22/100,000).

지급명세서·계산서 등 불성실 가산세(법§75 계열)는 항목·요율이 다양하여 자동 산정하지 않고
수기 입력으로 합산한다(이 모듈은 핵심 3종 + 합산만 담당).
"""
from __future__ import annotations
from dataclasses import dataclass

# 납부지연 가산세 1일 이자율 (국기령 §27의4 — 2022.2.15 이후 22/100,000)
LATE_PAYMENT_DAILY_RATE = 22 / 100_000  # 0.00022


def calc_no_filing_penalty(
    no_filing_tax: int,
    *,
    fraud: bool = False,
    offshore: bool = False,
    revenue: int = 0,
    is_corp_or_double_entry: bool = True,
) -> int:
    """무신고가산세 (국기법§47의2).

    일반 20% / 부정 40% / 역외부정 60%. 법인·복식부기의무자는 수입금액 기준
    (일반 0.07%·부정 0.14%)과 비교해 큰 금액 (§47의2②1호).
    """
    if no_filing_tax <= 0:
        return 0
    if fraud:
        rate = 0.60 if offshore else 0.40
        revenue_rate = 0.0014
    else:
        rate = 0.20
        revenue_rate = 0.0007
    base = int(no_filing_tax * rate)
    if is_corp_or_double_entry and revenue > 0:
        base = max(base, int(revenue * revenue_rate))
    return base


def calc_under_report_penalty(
    under_report_tax: int,
    *,
    fraud_portion: int = 0,
    offshore: bool = False,
) -> int:
    """과소신고·초과환급 가산세 (국기법§47의3).

    부정분 × 40%(역외 60%) + (과소신고세액 − 부정분) × 10%.
    """
    if under_report_tax <= 0:
        return 0
    fraud_portion = max(0, min(fraud_portion, under_report_tax))
    fraud_rate = 0.60 if offshore else 0.40
    fraud_amt = int(fraud_portion * fraud_rate)
    general_amt = int((under_report_tax - fraud_portion) * 0.10)
    return fraud_amt + general_amt


def calc_late_payment_penalty(
    unpaid_tax: int,
    days: int,
    *,
    daily_rate: float = LATE_PAYMENT_DAILY_RATE,
) -> int:
    """납부지연 가산세 (국기법§47의4①1호).

    미납·과소납부 세액 × 미납일수 × 1일 이자율(국기령, 현행 22/100,000).
    """
    if unpaid_tax <= 0 or days <= 0:
        return 0
    return int(unpaid_tax * days * daily_rate)


@dataclass
class SurtaxResult:
    """가산세 산정 결과 (감사추적·검토메모용)."""
    no_filing: int = 0
    under_report: int = 0
    late_payment: int = 0
    other_manual: int = 0      # 지급명세서·계산서 등 법§75 계열 수기 합산

    @property
    def total(self) -> int:
        return self.no_filing + self.under_report + self.late_payment + self.other_manual


def aggregate_surtax(
    *,
    no_filing_tax: int = 0,
    no_filing_fraud: bool = False,
    no_filing_offshore: bool = False,
    revenue: int = 0,
    under_report_tax: int = 0,
    under_report_fraud_portion: int = 0,
    under_report_offshore: bool = False,
    unpaid_tax: int = 0,
    unpaid_days: int = 0,
    daily_rate: float = LATE_PAYMENT_DAILY_RATE,
    other_manual: int = 0,
) -> SurtaxResult:
    """무신고·과소신고·납부지연 가산세를 각각 산정해 합산.

    무신고와 과소신고는 동시 적용되지 않는다(무신고면 과소신고 없음) — 호출자가 둘 중
    하나만 입력하도록 한다. other_manual은 법§75 계열 수기 합산분.
    """
    return SurtaxResult(
        no_filing=calc_no_filing_penalty(
            no_filing_tax, fraud=no_filing_fraud, offshore=no_filing_offshore,
            revenue=revenue,
        ),
        under_report=calc_under_report_penalty(
            under_report_tax, fraud_portion=under_report_fraud_portion,
            offshore=under_report_offshore,
        ),
        late_payment=calc_late_payment_penalty(unpaid_tax, unpaid_days, daily_rate=daily_rate),
        other_manual=max(0, other_manual),
    )
