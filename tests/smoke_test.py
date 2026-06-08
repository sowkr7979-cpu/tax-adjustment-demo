"""앱 핵심 로직 E2E 스모크 테스트."""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import date
from src.ui.sme_checker import SME_REVENUE_LIMIT
from src.ui.manual_input import validate_manual_input
from src.project.taxproj import ManualInput
from src.rules.entertainment import calc_entertainment
from src.rules.depreciation import calc_depreciation
from src.rules.tax_base import calc_gross_tax
from src.rules.tax_credit import calc_final_tax
from src.rules.interest import calc_interest_disallowance
from src.rules.vehicle import calc_vehicle
from src.forms.registry import recommend_forms
from src.utils.models import TaxCredit, TaxAdjustmentResult, FixedAsset, LLMAnalysisResult, IssueCode

# 1. 중소기업 판정 기준
rev = 5_000_000_000
limit = SME_REVENUE_LIMIT["서비스업(일반)"]
assert rev < limit, f"중소기업 판정 오류: {rev} vs {limit}"
print(f"[1] SME 매출 판정: {rev:,} < {limit:,} (중소기업) OK")

# 2. 수기 입력 검증
mi = ManualInput(
    carryforward_losses=[{"year": 2000, "amount": 10_000_000}],
    prior_reserves=[{"code": "감가상각", "amount": -1_000_000, "disposition": "유보"}],
    carryforward_tax_credits=[{"year": 2010, "amount": 5_000_000}],
)
warns = validate_manual_input(mi, date(2025, 12, 31))
assert len(warns) == 3, f"검증 경고 수 오류: {len(warns)}"
print(f"[2] 수기입력 검증: 경고 {len(warns)}개 정상 탐지 OK")

# 3. 기업업무추진비
ent = calc_entertainment(
    total_expense=50_000_000, card_expense=45_000_000,
    no_receipt_expense=2_000_000, revenue=3_000_000_000, is_sme=True,
)
assert ent.no_receipt_disallowed == 2_000_000
assert ent.excess >= 0
print(f"[3] 접대비: 한도={ent.total_limit:,} 초과={ent.excess:,} OK")

# 4. 지급이자 손금불산입 (1호→3호→4호 순서)
interest = calc_interest_disallowance(
    total_interest=20_000_000,
    unknown_creditor_interest=2_000_000,
    construction_interest=3_000_000,
    non_business_asset=30_000_000,
    total_asset=100_000_000,
)
expected_nba = int((20_000_000 - 2_000_000 - 3_000_000) * 0.3)
assert interest.non_business_disallowed == expected_nba
print(f"[4] 지급이자: 업무무관={interest.non_business_disallowed:,} OK")

# 5. 업무용승용차 (감가상각 800만 한도 분리)
vehicle = calc_vehicle(
    vehicle_id="V001", depreciation=20_000_000, other_expense=3_000_000,
    business_use_ratio=1.0, has_insurance=True, has_logbook=True,
)
assert vehicle.depreciation_limit_excess == 12_000_000
assert vehicle.business_other_expense_allowed == 3_000_000
print(f"[5] 차량: 감가상각 이월={vehicle.depreciation_limit_excess:,} 기타비용 허용={vehicle.business_other_expense_allowed:,} OK")

# 6. 세율 + 최저한세 구간별
gross, _ = calc_gross_tax(tax_base=500_000_000, fiscal_year_start=date(2025, 1, 1))
assert gross == int(500_000_000 * 0.19) - 20_000_000
print(f"[6] 산출세액: {gross:,}원 (2025년 개시 2구간) OK")

final = calc_final_tax(
    gross_tax=gross,
    tax_credits=[TaxCredit("중소기업감면", 5_000_000, True)],
    tax_base=500_000_000, is_sme=True,
)
assert final["최저한세율"] == 0.07
print(f"[7] 최저한세: {final['최저한세율']*100:.0f}% 최저한세액={final['최저한세액']:,} OK")

# 7. 최저한세 일반법인 구간 검증
r1 = calc_final_tax(gross_tax=1_000_000_000, tax_credits=[], tax_base=8_000_000_000, is_sme=False)
assert r1["최저한세율"] == 0.10
r2 = calc_final_tax(gross_tax=5_000_000_000, tax_credits=[], tax_base=50_000_000_000, is_sme=False)
assert r2["최저한세율"] == 0.12
r3 = calc_final_tax(gross_tax=30_000_000_000, tax_credits=[], tax_base=200_000_000_000, is_sme=False)
assert r3["최저한세율"] == 0.17
print("[8] 최저한세 구간: 100억이하=10%, 1000억이하=12%, 초과=17% OK")

# 8. 서식 추천
forms = recommend_forms(
    has_depreciation=True, has_entertainment=True, has_donation=False,
    has_pension=False, has_bad_debt=False, has_interest=False,
    has_forex=False, has_dividend=False, has_vehicle=True,
    has_tax_credit=True, is_sme=True,
)
keys = [f.key for f in forms]
assert "DEPRECIATION" in keys
assert "ENTERTAINMENT_A" in keys
assert "VEHICLE_EXPENSE" in keys
print(f"[9] 서식 추천: {len(forms)}개 ({', '.join(keys[:4])}...) OK")

print()
print("=" * 50)
print("모든 핵심 로직 검증 통과")
