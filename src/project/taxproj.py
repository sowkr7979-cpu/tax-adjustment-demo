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
    # 비과세소득·소득공제 (법§13① 2호·3호) — 과세표준에서 차감, 분개 파싱 불가 (수기)
    non_taxable_income: int = 0                # 비과세소득 (법§51 공익신탁 등)
    income_deduction: int = 0                  # 소득공제 (법§13①3호 — 이 법·다른 법률)
    prior_reserves: list[dict] = field(default_factory=list)         # 유보잔액 항목별
    # 전기 유보 당기 추인 → 소득금액 반영 (회계사 명시 입력 — ADR-002 판단 보조)
    #   감가상각 부인누계(엔진 자동 추인)·기부금 이월(별도)은 제외. 대손충당금 총액법 환입 등 포함.
    prior_reserve_reversal_deduct: int = 0     # 전기 유보 당기 추인 손금산입액 (△유보)
    prior_reserve_reversal_add: int = 0        # 전기 △유보 당기 추인 익금산입액 (유보)
    depreciation_denial_cumulative: int = 0
    carryforward_tax_credits: list[dict] = field(default_factory=list)
    related_parties: list[str] = field(default_factory=list)          # 이름 목록 (다운스트림 매칭용)
    # 특수관계인 상세 (표 표시·출처 구분) — [{이름, 관계, 지분율(%), 출처('DART'|'수기')}]
    related_party_details: list[dict] = field(default_factory=list)
    non_business_assets: list[dict] = field(default_factory=list)
    pension_db_asset: int = 0                  # 기말 퇴직연금(DB) 운용자산(예치금) 잔액
    retirement_estimate: int = 0               # 퇴직급여추계액 (일시퇴직·보험수리 중 큰 값, 영§44의2④)
    prior_pension_deducted: int = 0            # 직전까지 손금산입한 퇴직연금 부담금 누계 (영§44의2④2호)
    receivable_balance: int = 0
    actual_bad_debt_rate: float = 0.01
    bad_debt_method: str = "총액법"           # 대손충당금 처리방식 (총액법/보충법 — 유보 증감 표시)

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
    interest_unknown_creditor: int = 0         # 채권자불분명 사채이자 (법§28①1호)
    interest_nonreal_name: int = 0             # 비실명 채권·증권이자 (법§28①2호)
    interest_construction: int = 0             # 건설자금이자
    interest_line_classes: dict = field(default_factory=dict)  # 이자비용 라인별 분류 {전표|행: 분류}
    non_business_asset_checks: dict = field(default_factory=dict)  # 업무무관자산 체크 {계정명: bool}
    non_business_asset_balance: int = 0        # 업무무관자산 잔액 합계 (법§28①4호, 영§53)
    # 수입금액 보정 (기업업무추진비 한도 분모, 법§25④·영§42① 기업회계기준 매출액)
    #   0이면 매출계정 자동집계 사용. 파서가 매출을 누락·오분류한 경우만 보정 (임의 가산 금지).
    revenue_manual: int = 0
    # 기부금 (법§24)
    donation_special: int = 0                  # 특례기부금
    donation_general: int = 0                  # 일반기부금
    donation_nondesignated: int = 0            # 비지정기부금 (전액 손금불산입)
    # 전기 이월 기부금 (법§24⑤, 10년) — 발생연도별 [{year, type:'특례'|'일반', amount}]
    donation_carryforwards: list[dict] = field(default_factory=list)
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
    related_loan_balance: int = 0              # 특수관계인 가지급금 평균잔액 (표 미사용 시 폴백)
    related_loan_interest: int = 0             # 수취 약정이자 (표 미사용 시 폴백)
    related_loan_rate: float = 0.0             # 가중평균차입이자율 (0이면 당좌대출이자율 적용, 영§89③)
    related_loan_opening: int = 0              # 기초 이월 가지급금 잔액 (표 미사용 시 폴백)
    # 거래상대방(차주)별 기초이월·약정이자 — 별지19호 1행/차주 (상대방 간 통산 금지)
    related_loan_parties: list[dict] = field(default_factory=list)  # [{name, opening, interest}]
    # 부당행위계산 부인 (법§52, 영§88) — 고가매입·저가양도 등 시가 비교는 수동 산정
    unfair_transaction_amount: int = 0     # (레거시 폴백) 분개 미매칭 시 총액 입력
    # 건별 질문형 수기입력 답 저장 — review_specs 항목키 → [건별 답 dict] (.taxproj 직렬화)
    #   예: review_answers["부당행위계산 부인"] = [{"type":"고가매입","market":..,"deal":..,"who":"주주","_ref":"J1|3"}]
    review_answers: dict = field(default_factory=dict)
    # 수입배당금 (법§18의2)
    dividend_ownership_ratio: float = 0.0      # 출자비율 (0~1)
    # 간주임대료 (조특법§138, 조특령§132)
    rental_deposit: int = 0                    # 임대보증금 기초총액 (받은 보증금 — 표 합계 또는 폴백)
    rental_deposit_items: list[dict] = field(default_factory=list)  # 임대물건 명세(표시용) [{물건, 기초보증금}]
    rental_debt: int = 0                       # 차입금 잔액
    rental_equity: int = 0                     # 자기자본
    rental_bank_rate: float = 0.035            # 정기예금이자율
    rental_construction_cost: int = 0          # 임대용부동산 건설비상당액 (토지 제외, 조특령§132⑥)
    rental_area_ratio: float = 0.0             # 임대 면적비율 (임대면적÷전체면적, 조특칙§59 — 건설비 적수 안분, 0이면 금액비율 폴백)
    rental_financial_income: int = 0           # 보증금 운용 금융수익 (이자·배당 등, 조특령§132⑤)
    # 자산수증익·채무면제익 이월결손금 보전 (법§18 6호, 영§16) — 보전충당액 익금불산입
    asset_gift_revenue: int = 0                # 자산수증이익 수익 계상액 (국고보조금 제외)
    debt_forgiveness_revenue: int = 0          # 채무면제이익 수익 계상액
    debt_forgiveness_equity_swap: bool = False # 출자전환 채무면제익 포함 (법§17①1호 단서·영§15)
    debt_relief_carryforward: int = 0          # 보전에 충당하는 이월결손금 (영§16, 공제기한 지난 것 포함)
    refund_interest_revenue: int = 0           # 수익 계상한 국세·지방세 환급금 이자 (법§18 4호 익금불산입)
    vat_output_revenue: int = 0                # 수익 계상한 부가가치세 매출세액 (법§18 5호 익금불산입)
    # 세액 단계 — 세액공제·감면, 가산세, 기납부세액 (법§55~64·73, 조특법)
    tax_credit_items: list[dict] = field(default_factory=list)  # [{name, amount, subject_to_min_tax}]
    surtax_amount: int = 0                     # 가산세 (법§75 계열·국기법§47의2~4 — 무신고·과소·납부지연 등)
    prepaid_tax_amount: int = 0                # 기납부세액 (중간예납 법§63 + 원천납부 법§73 + 수시부과)
    # 토지등 양도소득에 대한 법인세 (법§55의2)
    land_transfer_income: int = 0              # 토지등 양도소득 (양도가액 − 장부가액 등)
    land_transfer_type: str = "비사업용토지"   # 비사업용토지 / 주택별장 / 조합원입주권분양권
    land_transfer_unregistered: bool = False   # 미등기 양도 여부 (비사업용토지·주택별장은 40%)
    # 중소기업 결손금 소급공제 환급 (법§72, 영§110) — 당기 결손 시 직전 사업연도 법인세 환급
    loss_carryback_enabled: bool = False       # 소급공제 검토·신청 여부 (회계사 선택)
    loss_carryback_prior_tax_base: int = 0     # 직전 사업연도 과세표준
    loss_carryback_prior_gross_tax: int = 0    # 직전 산출세액 (§55의2 토지등양도 제외)
    loss_carryback_prior_credit: int = 0       # 직전 공제·감면세액 (가산세 제외 — 한도 산정)
    loss_carryback_requested_loss: int = 0     # 신청 소급공제 결손금 (0이면 상한 전액)
    loss_carryback_both_filed: bool = True     # 당기·직전 모두 기한내 신고 (법§72④ 요건)
    loss_carryback_step2_override: int = 0      # 직전<2023 세율 미수록 시 회계사 2호 직접 입력 (0=미입력)
    # 회계사 직접 입력 세무조정 (규칙엔진 미포착 항목 수동 가감) — 소득금액조정합계표에 직접 반영
    #   [{name, amount, category: 익금산입|손금불산입|손금산입|익금불산입, disposition, basis}]
    custom_adjustments: list[dict] = field(default_factory=list)


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
        # 전년 결손금 소급공제(법§72)를 적용했다면, 소급공제분은 차기 이월결손금에서 제외해야 한다.
        if pm.loss_carryback_enabled:
            _applied = int(ta.get("loss_carryback_applied_loss", 0) or 0)
            if _applied > 0:
                notes.append(
                    f"⚠ 전년 결손금 소급공제(법§72) 적용분 {_applied:,}원은 이월공제(법§13①1호) 대상에서 "
                    "제외 — 당기 이월결손금에 이 금액이 포함되지 않았는지 확인하세요(이중공제 방지).")
            else:
                notes.append(
                    "⚠ 전년 결손금 소급공제(법§72) 신청분은 이월공제 대상에서 제외 — "
                    "당기 이월결손금에 소급공제한 결손금이 포함되지 않도록 확인하세요.")

        # ── 전기 유보 — 전년 계산 결과의 유보 발생분이 있으면 그것을, 없으면 입력값 ──
        prev_reserves = ta.get("reserves") or pm.prior_reserves
        if prev_reserves:
            cm.prior_reserves = [dict(x) for x in prev_reserves]
            notes.append(f"전기 유보 {len(cm.prior_reserves)}건"
                         + (" (전년 자동계산 결과 기반)" if ta.get("reserves") else ""))

        # ── 이월 기부금 (법§24⑤) — 전년 계산의 차기 이월분이 있으면 그것을, 없으면 입력값 ──
        prev_don_cf = ta.get("donation_carryforwards") or pm.donation_carryforwards
        if prev_don_cf:
            cm.donation_carryforwards = [dict(x) for x in prev_don_cf]
            notes.append(f"이월 기부금 {len(cm.donation_carryforwards)}건 "
                         "(공제기한 10년 — 당기 우선공제 대상)")

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
