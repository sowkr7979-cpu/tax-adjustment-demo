"""별지 제68호 소급공제법인세액환급신청서 빌더 테스트."""
from datetime import date

from src.project.taxproj import CompanyInfo
from src.rules.loss_carryback import compute_loss_carryback
from src.forms.refund_request import build_refund_request


def _company():
    return CompanyInfo(
        name="㈜테스트", business_no="123-45-67890",
        representative="홍길동", address="서울시 강남구", industry_code="C26",
    )


def test_refund_request_structure():
    lcb = compute_loss_carryback(
        is_sme=True, current_loss=100_000_000,
        prior_tax_base=300_000_000, prior_gross_tax=37_000_000,
        prior_credit_exemption=0, prior_fiscal_start=date(2024, 1, 1),
    )
    form = build_refund_request(
        company=_company(), fy_start=date(2025, 1, 1), fy_end=date(2025, 12, 31), lcb=lcb,
    )
    assert form["byl"] == "법인세법 시행규칙 [별지 제68호서식]"
    assert form["title"] == "소급공제법인세액환급신청서"
    assert form["eligible"]
    assert form["refund"] == 19_000_000
    # 신청인 6란
    assert len(form["applicant"]) == 6
    assert form["applicant"][0]["내용"] == "㈜테스트"
    # 환급신청 내용 ⑦~⑮ (9란)
    rows = {r["란"][0]: r for r in form["refund_rows"]}  # 첫 글자(원문자)로 매핑
    assert form["refund_rows"][1]["금액"] == "300,000,000"   # ⑧ 직전 과세표준
    assert form["refund_rows"][2]["금액"] == "37,000,000"    # ⑨ 직전 산출세액
    assert form["refund_rows"][4]["금액"] == "37,000,000"    # ⑪ 한도
    assert form["refund_rows"][5]["금액"] == "100,000,000"   # ⑫ 소급공제 결손금
    assert form["refund_rows"][7]["금액"] == "18,000,000"    # ⑭ 소급공제 후 산출세액
    assert form["refund_rows"][8]["금액"] == "19,000,000"    # ⑮ 환급신청 세액


def test_refund_request_prior_year_shift():
    lcb = compute_loss_carryback(
        is_sme=True, current_loss=50_000_000,
        prior_tax_base=100_000_000, prior_gross_tax=9_000_000,
        prior_credit_exemption=0, prior_fiscal_start=date(2024, 1, 1),
    )
    form = build_refund_request(
        company=_company(), fy_start=date(2025, 1, 1), fy_end=date(2025, 12, 31), lcb=lcb,
    )
    # ⑦ 직전 사업연도 = 당기 −1년
    assert form["refund_rows"][0]["금액"] == "2024-01-01 ~ 2024-12-31"
    # ⑥ 결손 발생 사업연도 = 당기
    assert form["applicant"][5]["내용"] == "2025-01-01 ~ 2025-12-31"


def test_refund_request_ineligible_step15_honest():
    # 요건 미충족(중소기업 아님)이면 ⑮는 오해 없는 0원 표기 + calc_basis도 미충족 명시
    lcb = compute_loss_carryback(
        is_sme=False, current_loss=100_000_000,
        prior_tax_base=300_000_000, prior_gross_tax=37_000_000,
        prior_credit_exemption=0, prior_fiscal_start=date(2024, 1, 1),
    )
    form = build_refund_request(
        company=_company(), fy_start=date(2025, 1, 1), fy_end=date(2025, 12, 31), lcb=lcb,
    )
    assert not form["eligible"]
    assert "요건 미충족" in form["refund_rows"][8]["금액"]
    assert any("요건 미충족" in c for c in form["calc_basis"])
    # 직전연도 값 출처 + 추징 안내가 계산근거/주의에 포함
    assert any(".taxproj 승계" in c for c in form["calc_basis"])
    assert any("10만분의 22" in n for n in form["notes"])
