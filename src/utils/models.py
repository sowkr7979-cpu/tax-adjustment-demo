"""공통 데이터 모델."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class AccountClass(Enum):
    ENTERTAINMENT = "기업업무추진비"
    DEPRECIATION = "감가상각"
    INTEREST_EXPENSE = "이자비용"
    DONATION = "기부금"
    ALLOWANCE = "충당금"
    RELATED_PARTY = "특수관계인"
    FOREX = "외화"
    VEHICLE = "업무용승용차"
    OFFICER = "임원"
    PENALTY = "벌과금"
    DIVIDEND = "배당"
    OTHER_ADJUSTMENT = "기타조정"


class IssueCode(str, Enum):
    ENTERTAINMENT_EXPENSE = "ENTERTAINMENT_EXPENSE"
    DONATION_CLASSIFICATION = "DONATION_CLASSIFICATION"
    RELATED_PARTY_LOAN = "RELATED_PARTY_LOAN"
    CONSTRUCTION_INTEREST = "CONSTRUCTION_INTEREST"
    NON_BUSINESS_EXPENSE = "NON_BUSINESS_EXPENSE"
    OFFICER_BONUS = "OFFICER_BONUS"
    OFFICER_RETIREMENT = "OFFICER_RETIREMENT"
    PENALTY = "PENALTY"
    FOREX_TRANSACTION = "FOREX_TRANSACTION"
    DEBT_FORGIVENESS = "DEBT_FORGIVENESS"
    ASSET_GIFT = "ASSET_GIFT"
    DIVIDEND_INCOME = "DIVIDEND_INCOME"
    VEHICLE_EXPENSE = "VEHICLE_EXPENSE"
    BAD_DEBT = "BAD_DEBT"
    INVENTORY_LOSS = "INVENTORY_LOSS"
    DEFERRED_REVENUE_EXPENSE = "DEFERRED_REVENUE_EXPENSE"
    GOVT_SUBSIDY = "GOVT_SUBSIDY"
    DEPRECIATION_MISMATCH = "DEPRECIATION_MISMATCH"
    RELATED_PARTY_TRANSACTION = "RELATED_PARTY_TRANSACTION"
    PENDING_LLM_REVIEW = "PENDING_LLM_REVIEW"
    UNKNOWN = "UNKNOWN"


# 이슈코드 → 한글 표시명 (UI 표시용)
ISSUE_LABELS_KO: dict[str, str] = {
    "ENTERTAINMENT_EXPENSE":    "기업업무추진비",
    "DONATION_CLASSIFICATION":  "기부금 분류",
    "RELATED_PARTY_LOAN":       "가지급금·특수관계 대여금",
    "CONSTRUCTION_INTEREST":    "지급이자 (건설자금·채권자불분명 의심)",
    "NON_BUSINESS_EXPENSE":     "업무무관비용",
    "OFFICER_BONUS":            "임원 상여·급여",
    "OFFICER_RETIREMENT":       "임원 퇴직급여",
    "PENALTY":                  "벌과금·과태료·가산세",
    "FOREX_TRANSACTION":        "외화환산손익",
    "DEBT_FORGIVENESS":         "채무면제이익",
    "ASSET_GIFT":               "자산수증이익",
    "DIVIDEND_INCOME":          "수입배당금",
    "VEHICLE_EXPENSE":          "업무용승용차 비용",
    "BAD_DEBT":                 "대손금·대손충당금",
    "INVENTORY_LOSS":           "재고자산 평가손실",
    "DEFERRED_REVENUE_EXPENSE": "손익 귀속시기 검토",
    "GOVT_SUBSIDY":             "국고보조금",
    "DEPRECIATION_MISMATCH":    "감가상각 불일치",
    "RELATED_PARTY_TRANSACTION": "특수관계인 거래",
    "PENDING_LLM_REVIEW":       "LLM 검토 대기",
    "UNKNOWN":                  "미분류",
}


def issue_label(code: str) -> str:
    """이슈코드 → '한글명' 표시 문자열. 미등록 코드는 원문 유지."""
    return ISSUE_LABELS_KO.get(code, code)


@dataclass
class JournalLine:
    """분개 라인 (전표 내 단일 행)."""
    journal_id: str
    line_no: int
    date: date
    account_code: str
    account_name: str
    description: str
    counterparty_code: str
    counterparty_name: str
    debit: int
    credit: int
    evidence_type: str        # 세금계산서/카드/현금영수증/무증빙 등
    evidence_no: str
    card_no: str
    vehicle_no: str
    project: str
    source_file: str
    source_sheet: str
    source_row: int


@dataclass
class RuleClassificationResult:
    """1차 규칙 분류 결과."""
    journal_id: str
    account_code: str
    rule_issue_code: IssueCode | None
    forward_reason: str | None
    forward_to_stage2: bool


@dataclass
class LLMAnalysisResult:
    """2차 LLM 정밀 분석 결과."""
    journal_id: str
    line_id: int
    issue_possible: bool
    tax_issue_code: IssueCode
    tax_adjustment_type: str
    affected_amount: int
    confidence_score: float
    review_required: bool
    review_reason: str
    evidence_fields: dict[str, str]
    legal_basis_candidates: list[dict]
    target_form_candidates: list[str]
    stage1_confidence: float | None
    stage2_confidence: float


@dataclass
class FixedAsset:
    """고정자산 대장 한 행."""
    asset_code: str
    asset_name: str
    account_code: str
    acquired_date: date
    category: str
    book_value_start: int           # 전기말 장부가액
    accumulated_depr_start: int     # 전기말 상각누계액
    denied_depr_start: int          # 전기말 부인누계액
    deemed_depr_start: int          # 전기말 의제누계액
    new_acquisition: int
    disposal: int
    useful_life: int
    depr_rate: float
    months: int                     # 해당 기 상각 월수
    method: str                     # 정률법/정액법
    tax_depr_limit: int             # 세무상 상각범위액
    company_depr: int               # 회사 계상 상각비
    disposal_date: date | None


@dataclass
class TaxCredit:
    """세액공제·감면 항목."""
    name: str
    amount: int
    subject_to_min_tax: bool  # True: 최저한세 적용 대상


@dataclass
class TaxAdjustmentResult:
    """세무조정 계산 최종 결과."""
    fiscal_year_start: date
    fiscal_year_end: date
    is_sme: bool

    # 손금불산입
    depreciation_excess: int = 0
    entertainment_excess: int = 0
    entertainment_no_receipt: int = 0
    donation_excess: int = 0
    pension_excess: int = 0
    pension_deduction: int = 0   # 퇴직연금 부담금 손금산입 (영§44의2④, △유보)
    bad_debt_excess: int = 0
    interest_unknown_creditor: int = 0
    interest_construction: int = 0
    interest_non_business: int = 0
    vehicle_disallowed: int = 0
    penalty: int = 0
    officer_bonus_excess: int = 0
    officer_retirement_excess: int = 0
    corporate_tax_expense: int = 0       # 법인세비용 (법§21 1호, 전액)
    forex_loss_disallowed: int = 0       # 외화환산손실 (평가방법 미신고, 법§42③)
    derivative_loss_disallowed: int = 0  # 파생상품 평가손실 (미신고, 영§76)
    securities_loss_disallowed: int = 0  # 유가증권 평가손실 (영§75 — 원가법 외 부인)
    inventory_adjustment: int = 0        # 재고자산 평가 조정 (영§74, 유보)
    welfare_disallowed: int = 0          # 열거 외 복리후생비 (영§45)
    joint_expense_excess: int = 0        # 공동경비 분담 초과 (영§48)
    non_business_expense: int = 0        # 업무무관비용 (법§27)
    punitive_damages: int = 0            # 징벌적 손해배상금 (법§21의2)

    # 익금산입
    deemed_interest: int = 0
    deemed_rental: int = 0
    debt_forgiveness: int = 0
    asset_gift: int = 0
    unfair_transaction: int = 0          # 부당행위계산 부인 (법§52, 영§88 — 고가매입·저가양도 등)

    # 손금산입
    depreciation_approved: int = 0

    # 익금불산입
    dividend_exclusion: int = 0
    forex_gain_excluded: int = 0         # 외화환산이익 (평가방법 미신고)
    derivative_gain_excluded: int = 0    # 파생상품 평가이익 (미신고)
    securities_gain_excluded: int = 0    # 유가증권 평가이익 (영§75)

    # 집계 (calc() 호출 후 채워짐)
    net_income: int = 0
    business_income: int = 0
    tax_base: int = 0
    gross_tax: int = 0
    min_tax: int = 0
    tax_credits_min_subject: int = 0
    tax_credits_post_min: int = 0
    excluded_credits: int = 0
    surtax: int = 0
    prepaid_tax: int = 0
    final_tax_due: int = 0

    rule_engine_version: str = "0.1.0"
    law_reference_date: date = field(default_factory=date.today)

    @property
    def total_add_back(self) -> int:
        return (
            self.depreciation_excess + self.entertainment_excess
            + self.entertainment_no_receipt + self.donation_excess
            + self.pension_excess + self.bad_debt_excess
            + self.interest_unknown_creditor + self.interest_construction
            + self.interest_non_business + self.vehicle_disallowed
            + self.penalty + self.officer_bonus_excess
            + self.officer_retirement_excess
            + self.corporate_tax_expense
            + self.forex_loss_disallowed + self.derivative_loss_disallowed
            + self.securities_loss_disallowed + self.inventory_adjustment
            + self.welfare_disallowed + self.joint_expense_excess
            + self.non_business_expense + self.punitive_damages
            + self.deemed_interest + self.deemed_rental
            + self.debt_forgiveness + self.asset_gift
            + self.unfair_transaction
        )

    @property
    def total_deduct(self) -> int:
        return (
            self.depreciation_approved + self.dividend_exclusion
            + self.forex_gain_excluded + self.derivative_gain_excluded
            + self.securities_gain_excluded + self.pension_deduction
        )
