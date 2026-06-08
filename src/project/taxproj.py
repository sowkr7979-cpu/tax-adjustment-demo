"""프로젝트 파일(.taxproj) 관리."""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path


@dataclass
class CompanyInfo:
    name: str = ""
    business_no: str = ""
    representative: str = ""
    address: str = ""
    is_sme: bool = False
    sme_verified: bool = False
    sme_verification_notes: str = ""
    industry_code: str = ""
    fiscal_year_start: str = ""   # "YYYY-MM-DD"
    fiscal_year_end: str = ""
    corp_code: str = ""           # DART 고유번호
    acc_mt: str = ""              # 결산월 (DART)
    # 특정법인 (영§42②: ①지배주주등 지분 50% 초과 ②부동산임대 주업 또는
    # 임대·이자·배당 수입 ≥ 매출 50% ③상시근로자 5인 미만 — 모두 충족)
    # → 기업업무추진비 한도 50% (법§25⑤), 승용차 한도 800만→400만 (영§50의2⑮)
    is_specified_corp: bool = False
    specified_corp_notes: str = ""
    # 부동산임대업 주업 (조특령§132③: 자산총액 중 임대자산 50% 이상)
    # → 간주임대료 (조특법§138) 적용 요건
    is_rental_main: bool = False


@dataclass
class ManualInput:
    carryforward_losses: list[dict] = field(default_factory=list)   # [{year, amount}]
    prior_reserves: list[dict] = field(default_factory=list)         # 유보잔액 항목별
    depreciation_denial_cumulative: int = 0
    carryforward_tax_credits: list[dict] = field(default_factory=list)
    related_parties: list[str] = field(default_factory=list)
    non_business_assets: list[dict] = field(default_factory=list)
    pension_db_asset: int = 0                  # 기말 퇴직연금(DB) 운용자산(예치금) 잔액
    retirement_estimate: int = 0               # 퇴직급여추계액 (일시퇴직·보험수리 중 큰 값, 영§44의2④)
    prior_pension_deducted: int = 0            # 직전까지 손금산입한 퇴직연금 부담금 누계 (영§44의2④2호)
    receivable_balance: int = 0
    actual_bad_debt_rate: float = 0.01

    # ── 세무조정 필요자료 (체크리스트 '검토필요' → 자동계산 승격용) ──
    # 외화·파생상품 평가 (법§42③, 영§76)
    forex_method_reported: bool = False        # 마감환율 평가방법 신고 여부
    derivative_hedge_reported: bool = False    # 통화선도 등 평가방법 신고 여부
    # 임원 인건비 (법§26, 영§43~44)
    officer_names: list[str] = field(default_factory=list)  # 임원 명단 (분개장 거래처에서 선택)
    officer_bonus_paid: int = 0                # 임원 상여 지급액 (명단 선택 시 자동 집계)
    officer_bonus_limit: int = 0               # 정관·주총 결의 한도
    officer_retirement_paid: int = 0           # 임원 퇴직금 지급액 (명단 선택 시 자동 집계)
    officer_retirement_tenure: float = 0.0     # 근속연수
    officer_retirement_last_salary: int = 0    # 직전 1년 총급여
    # 업무용승용차 (법§27의2)
    vehicle_has_insurance: bool = True         # 업무전용보험 가입
    vehicle_has_logbook: bool = False          # 운행기록부 작성
    vehicle_business_ratio: float = 1.0        # 업무사용비율
    vehicle_depreciation: int = 0              # 승용차 감가상각비 계상액
    vehicle_asset_checks: dict = field(default_factory=dict)  # {자산코드: 업무용승용차 해당 여부}
    # 지급이자 (법§28)
    interest_unknown_creditor: int = 0         # 채권자불분명 사채이자
    interest_construction: int = 0             # 건설자금이자
    interest_line_classes: dict = field(default_factory=dict)  # 이자비용 라인별 분류 {전표|행: 분류}
    non_business_asset_checks: dict = field(default_factory=dict)  # 업무무관자산 체크 {계정명: bool}
    non_business_asset_balance: int = 0        # 업무무관자산 잔액 합계 (법§28①4호, 영§53)
    # 기부금 (법§24)
    donation_special: int = 0                  # 특례기부금
    donation_general: int = 0                  # 일반기부금
    donation_nondesignated: int = 0            # 비지정기부금 (전액 손금불산입)
    donation_line_classes: dict = field(default_factory=dict)  # 분개 라인별 분류 {전표|행: 분류}
    misc_line_checks: dict = field(default_factory=dict)       # 기타 항목 라인별 체크 {필드: {전표|행: bool}}
    # 재고자산 평가 (법§42, 영§74)
    inventory_valuation_adjustment: int = 0    # 평가방법 신고 차이 조정액 (가산, 유보)
    inventory_methods: dict = field(default_factory=dict)  # {종류: {"신고": 방법, "장부": 방법}}
    # 기타 손금불산입 (법§21의2·26·27, 영§45·48)
    welfare_disallowed: int = 0                # 열거 외 복리후생비 (영§45)
    joint_expense_excess: int = 0              # 공동경비 분담기준 초과액 (영§48)
    joint_total_pool: int = 0                  # 공동경비 총액 (전체 공동사업자 합계)
    joint_share_ratio: float = 0.0             # 법인의 분담비율 (출자 또는 매출 기준, 0~1)
    non_business_expense: int = 0              # 업무무관비용 (법§27)
    punitive_damages: int = 0                  # 징벌적 손해배상금 손금불산입액 (법§21의2)
    punitive_actual_known: bool = False        # 실손해액이 분명한가 (영§23②)
    punitive_actual_amount: int = 0            # 실제 발생한 손해액
    # 가지급금 인정이자 (법§52, 영§88①6호, 영§89③)
    related_loan_balance: int = 0              # 특수관계인 가지급금 평균잔액
    related_loan_interest: int = 0             # 수취 약정이자
    related_loan_rate: float = 0.0             # 가중평균차입이자율 (0이면 당좌대출이자율 적용, 영§89③)
    related_loan_opening: int = 0              # 기초 이월 가지급금 잔액 (적수 계산에 기초분 반영)
    # 부당행위계산 부인 (법§52, 영§88) — 고가매입·저가양도 등 시가 비교는 수동 산정
    unfair_transaction_amount: int = 0
    # 수입배당금 (법§18의2)
    dividend_ownership_ratio: float = 0.0      # 출자비율 (0~1)
    # 간주임대료 (조특법§138, 조특령§132)
    rental_deposit: int = 0                    # 임대보증금
    rental_debt: int = 0                       # 차입금 잔액
    rental_equity: int = 0                     # 자기자본
    rental_bank_rate: float = 0.035            # 정기예금이자율
    rental_construction_cost: int = 0          # 임대용부동산 건설비상당액 (토지 제외, 조특령§132⑥)
    rental_financial_income: int = 0           # 보증금 운용 금융수익 (이자·배당 등, 조특령§132⑤)


@dataclass
class TaxProject:
    version: str = "0.1.0"
    company: CompanyInfo = field(default_factory=CompanyInfo)
    manual_input: ManualInput = field(default_factory=ManualInput)
    input_files: dict[str, str] = field(default_factory=dict)
    form_selection: list[str] = field(default_factory=list)
    tax_adjustments: dict = field(default_factory=dict)
    review_queue: list[dict] = field(default_factory=list)
    outputs: dict[str, str] = field(default_factory=dict)
    status: str = "draft"
    created_at: str = ""
    updated_at: str = ""

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2, default=str)

    def carry_forward_from(self, prev: "TaxProject") -> list[str]:
        """전년도 프로젝트에서 당기로 승계 — 실무 시작점 (전기 유보·이월결손금·판단자료).

        전년 파일이 없으면 기존 수기 입력 필드를 그대로 쓰면 된다 (이 함수는 보조).
        반환: 승계 내역 설명 리스트 (UI 표시용).
        """
        notes: list[str] = []
        pm, cm = prev.manual_input, self.manual_input
        ta = prev.tax_adjustments or {}

        # ── 회사 정보 + 사업연도 1년 전진 ──
        if prev.company.name:
            self.company = CompanyInfo(**{
                **prev.company.__dict__,
                "sme_verified": False,
            })
            try:
                ps = date.fromisoformat(prev.company.fiscal_year_start)
                pe = date.fromisoformat(prev.company.fiscal_year_end)
                self.company.fiscal_year_start = str(ps.replace(year=ps.year + 1))
                self.company.fiscal_year_end = str(pe.replace(year=pe.year + 1))
                notes.append(
                    f"회사 정보 승계 + 사업연도 1년 전진: "
                    f"{self.company.fiscal_year_start} ~ {self.company.fiscal_year_end}"
                )
            except ValueError:
                notes.append("회사 정보 승계 (사업연도는 1단계에서 직접 설정)")

        # ── 이월결손금 (전년 입력 그대로 — 당기 공제분 차감은 회계사 확인) ──
        if pm.carryforward_losses:
            cm.carryforward_losses = [dict(x) for x in pm.carryforward_losses]
            notes.append(f"이월결손금 {len(cm.carryforward_losses)}건 "
                         f"(당기 공제분 차감 여부 확인 필요)")

        # ── 전기 유보 — 전년 계산 결과의 유보 발생분이 있으면 그것을, 없으면 입력값 ──
        prev_reserves = ta.get("reserves") or pm.prior_reserves
        if prev_reserves:
            cm.prior_reserves = [dict(x) for x in prev_reserves]
            notes.append(f"전기 유보 {len(cm.prior_reserves)}건"
                         + (" (전년 자동계산 결과 기반)" if ta.get("reserves") else ""))

        # ── 감가상각 부인누계 — 전년 당기말 부인누계 승계 ──
        if ta.get("depreciation_denial_end"):
            cm.depreciation_denial_cumulative = int(ta["depreciation_denial_end"])
            notes.append(f"감가상각 부인누계 {cm.depreciation_denial_cumulative:,}원 (전년 당기말)")
        elif pm.depreciation_denial_cumulative:
            cm.depreciation_denial_cumulative = pm.depreciation_denial_cumulative
            notes.append(f"감가상각 부인누계 {cm.depreciation_denial_cumulative:,}원 (전년 입력값)")

        # ── 판단 자료 (해마다 거의 동일 — 변동 시 수정) ──
        _JUDGMENT_FIELDS = [
            ("related_parties", "특수관계인 목록"),
            ("forex_method_reported", "외화 평가방법 신고"),
            ("derivative_hedge_reported", "파생 평가방법 신고"),
            ("officer_names", "임원 명단"),
            ("officer_bonus_limit", "임원 상여 한도"),
            ("officer_retirement_tenure", "임원 근속연수"),
            ("officer_retirement_last_salary", "임원 직전 총급여"),
            ("vehicle_has_insurance", "승용차 보험"),
            ("vehicle_has_logbook", "운행기록부"),
            ("vehicle_business_ratio", "업무사용비율"),
            ("vehicle_asset_checks", "승용차 자산 분류"),
            ("inventory_methods", "재고 평가방법"),
            ("dividend_ownership_ratio", "수입배당 출자비율"),
            ("rental_bank_rate", "정기예금이자율"),
            ("related_loan_rate", "가중평균차입이자율"),
            ("actual_bad_debt_rate", "대손실적률"),
            ("joint_share_ratio", "공동경비 분담비율"),
            ("non_business_asset_checks", "업무무관자산 체크"),
        ]
        carried = []
        for f_name, label in _JUDGMENT_FIELDS:
            v = getattr(pm, f_name, None)
            if v:
                setattr(cm, f_name, v.copy() if isinstance(v, (list, dict)) else v)
                carried.append(label)
        if carried:
            notes.append("판단자료 승계: " + ", ".join(carried))

        # ── 회사 판정 (재판정 필요 표시) ──
        self.company.is_sme = prev.company.is_sme
        self.company.is_specified_corp = prev.company.is_specified_corp
        self.company.is_rental_main = prev.company.is_rental_main
        self.company.sme_verified = False   # 매년 재판정
        notes.append(
            f"전년 판정 참고: {'중소기업' if prev.company.is_sme else '일반법인'}"
            f"{' · 특정법인' if prev.company.is_specified_corp else ''}"
            f"{' · 임대주업' if prev.company.is_rental_main else ''} — 당기 재판정 필요"
        )
        return notes

    @classmethod
    def load(cls, path: str | Path) -> "TaxProject":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        proj = cls()
        proj.version = data.get("version", "0.1.0")
        proj.company = CompanyInfo(**data.get("company", {}))
        proj.manual_input = ManualInput(**data.get("manual_input", {}))
        proj.input_files = data.get("input_files", {})
        proj.form_selection = data.get("form_selection", [])
        proj.tax_adjustments = data.get("tax_adjustments", {})
        proj.review_queue = data.get("review_queue", [])
        proj.outputs = data.get("outputs", {})
        proj.status = data.get("status", "draft")
        return proj
