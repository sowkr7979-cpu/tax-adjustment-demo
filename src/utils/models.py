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
    """AI 검토 보조 결과."""
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
    farm_surtax_taxable: bool = False  # True: 농어촌특별세 과세대상 (농특세법§5①, §4 비과세 제외)


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
    interest_nonreal_name: int = 0       # 비실명 채권·증권이자 (법§28①2호) — 전액 손금불산입
    interest_construction: int = 0
    interest_non_business: int = 0
    vehicle_disallowed: int = 0
    vehicle_depr_excess: int = 0   # 업무용승용차 감가상각 한도초과(유보) — vehicle_disallowed의 부분집합
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
    stock_compensation_excess: int = 0    # 주식매수선택권·주식기준보상 비용 한도초과 (조특§13의2)
    construction_revenue_add: int = 0     # 작업진행률 수익인식 익금산입 (영§69)
    treasury_stock_loss_disallowed: int = 0  # 자기주식처분손실 손금불산입 (법§15·§17)
    proper_purpose_reserve_excess: int = 0   # 고유목적사업준비금 한도초과 (법§29)

    # 익금산입
    deemed_interest: int = 0
    deemed_rental: int = 0
    deemed_dividend: int = 0             # 의제배당 (법§16① — 감자·해산·합병·무상증자 등)
    unfair_transaction: int = 0          # 부당행위계산 부인 (법§52, 영§88 — 고가매입·저가양도 등)
    construction_revenue_excluded: int = 0  # 작업진행률 수익인식 익금불산입 (영§69)
    treasury_stock_gain_excluded: int = 0   # 자기주식처분이익 익금불산입 (법§17)
    # 전기 △유보 당기 추인 익금산입 (회계사 명시 입력 — 감가상각·기부금이월 제외)
    prior_reserve_reversal_add: int = 0

    # 손금산입
    depreciation_approved: int = 0
    # 전기 유보 당기 추인 손금산입(△유보) — 대손충당금 총액법 환입(법§34③) 등, 감가상각 제외
    prior_reserve_reversal_deduct: int = 0

    # 익금불산입
    dividend_exclusion: int = 0
    forex_gain_excluded: int = 0         # 외화환산이익 (평가방법 미신고)
    derivative_gain_excluded: int = 0    # 파생상품 평가이익 (미신고)
    securities_gain_excluded: int = 0    # 유가증권 평가이익 (영§75)
    # 전기 이월 기부금 당기 손금산입 (법§24⑤⑥ 이월분 우선공제 — 처분 "기타")
    donation_carryforward_deduction: int = 0
    # 자산수증익·채무면제익 중 이월결손금 보전 충당액 (법§18 6호, 영§16 — 익금불산입)
    # 자산수증익·채무면제익은 수익 계상되어 이미 net_income에 포함 → 보전충당분만 손금산입(△)
    debt_relief_offset: int = 0
    refund_interest_excluded: int = 0    # 국세·지방세 과오납 환급금 이자 (법§18 4호 — 익금불산입)
    vat_output_excluded: int = 0         # 부가가치세 매출세액 (법§18 5호 — 익금불산입)
    proper_purpose_reserve_deduction: int = 0  # 고유목적사업준비금 손금산입 (법§29)

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
    land_transfer_tax: int = 0    # 토지등 양도소득에 대한 법인세 (법§55의2 — 일반 법인세에 추가 납부)
    final_tax_due: int = 0
    farm_surtax: int = 0          # 농어촌특별세 (농특세법§5① — 감면세액×20%, 법인세와 별도 신고·납부)

    # 가지급금 인정이자 거래상대방별 익금산입 내역 — 소득처분 귀속자 입력용 (영§106)
    deemed_interest_parties: list = field(default_factory=list)  # [{"name", "amount"}]
    # 부당행위계산 부인 건별 내역 — 건별 소득처분 (영§106). 비면 레거시 단일행.
    unfair_transaction_lines: list = field(default_factory=list)  # [{"amount","disposition","basis","ref"}]
    # 복리후생비(열거 외) 건별 내역 — 건별 소득처분 (영§45·106). 비면 레거시 단일행.
    welfare_disallowed_lines: list = field(default_factory=list)
    # 의제배당 건별 내역 (법§16①) — 사유별 익금산입.
    deemed_dividend_lines: list = field(default_factory=list)
    # 회계사 직접 입력 세무조정 (규칙엔진 미포착 항목) — 소득금액조정합계표에 직접 가감
    #   [{name, amount, category: 익금산입|손금불산입|손금산입|익금불산입, disposition, basis}]
    custom_adjustment_lines: list = field(default_factory=list)

    rule_engine_version: str = "0.1.0"
    law_reference_date: date = field(default_factory=date.today)

    # 가산/차감 구분 카테고리 (소득금액조정합계표)
    _ADD_CATEGORIES = ("익금산입", "손금불산입")
    _DEDUCT_CATEGORIES = ("손금산입", "익금불산입")

    @property
    def custom_add_back(self) -> int:
        return sum(int(x.get("amount", 0)) for x in self.custom_adjustment_lines
                   if x.get("category") in self._ADD_CATEGORIES)

    @property
    def custom_deduct(self) -> int:
        return sum(int(x.get("amount", 0)) for x in self.custom_adjustment_lines
                   if x.get("category") in self._DEDUCT_CATEGORIES)

    @property
    def total_add_back(self) -> int:
        return self.custom_add_back + (
            self.depreciation_excess + self.entertainment_excess
            + self.entertainment_no_receipt + self.donation_excess
            + self.pension_excess + self.bad_debt_excess
            + self.interest_unknown_creditor + self.interest_nonreal_name
            + self.interest_construction
            + self.interest_non_business + self.vehicle_disallowed
            + self.penalty + self.officer_bonus_excess
            + self.officer_retirement_excess
            + self.corporate_tax_expense
            + self.forex_loss_disallowed + self.derivative_loss_disallowed
            + self.securities_loss_disallowed + self.inventory_adjustment
            + self.welfare_disallowed + self.joint_expense_excess
            + self.non_business_expense + self.punitive_damages
            + self.stock_compensation_excess + self.construction_revenue_add
            + self.treasury_stock_loss_disallowed + self.proper_purpose_reserve_excess
            + self.deemed_interest + self.deemed_rental + self.deemed_dividend
            + self.unfair_transaction
            + self.prior_reserve_reversal_add
        )

    @property
    def total_deduct(self) -> int:
        return self.custom_deduct + (
            self.depreciation_approved + self.dividend_exclusion
            + self.forex_gain_excluded + self.derivative_gain_excluded
            + self.securities_gain_excluded + self.pension_deduction
            + self.debt_relief_offset
            + self.refund_interest_excluded + self.vat_output_excluded
            + self.construction_revenue_excluded + self.treasury_stock_gain_excluded
            + self.proper_purpose_reserve_deduction
            + self.prior_reserve_reversal_deduct
            + self.donation_carryforward_deduction
        )
