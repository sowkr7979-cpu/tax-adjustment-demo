"""세액공제·감면 + 최저한세 계산 — 조세특례제한법 제132조."""
from src.utils.constants import get_min_tax_rate, FARM_SURTAX_RATE
from src.utils.models import TaxCredit


def calc_final_tax(
    *,
    gross_tax: int,
    tax_credits: list[TaxCredit],
    tax_base: int,
    is_sme: bool,
    surtax: int = 0,
    prepaid_tax: int = 0,
) -> dict:
    """
    최저한세 적용 순서 (조특§132):
    1. 산출세액 - 최저한세 적용대상 감면 = 감면후세액
    2. 감면후세액 < 최저한세액 → 초과분 감면 배제
    3. 최저한세 미적용 감면 추가 차감 (§132 제외 항목)
    4. 가산세 가산, 기납부세액 차감

    농어촌특별세(농특세법§5①): 농특세 과세대상 감면세액(farm_surtax_taxable=True) × 20%.
      배제된 감면은 실제 감면받지 못한 것이므로 농특세 과세표준에서 제외한다.
      단, 최저한세 배제(excluded)는 '최저한세 적용대상 감면 전체'에서 발생하므로,
      농특세 과세대상 감면에는 그 중 '농특세 과세대상 최저한세 감면'이 차지하는 비율만큼만
      안분하여 차감한다 (농특 비과세 감면의 배제분까지 빼면 농특세가 과소계상됨).
      농특세는 법인세와 별도로 신고·납부하므로 차감납부세액에 포함하지 않는다.
    """
    min_credits = sum(c.amount for c in tax_credits if c.subject_to_min_tax)
    post_credits = sum(c.amount for c in tax_credits if not c.subject_to_min_tax)

    after_credit = max(0, gross_tax - min_credits)
    min_rate = get_min_tax_rate(tax_base, is_sme)
    min_tax = int(tax_base * min_rate)

    if after_credit < min_tax:
        excluded = min_tax - after_credit
        after_min = min_tax
    else:
        excluded = 0
        after_min = after_credit

    final_tax = max(0, after_min - post_credits)
    final_due = max(0, final_tax + surtax - prepaid_tax)

    # 농어촌특별세 — 실제 감면된 농특세 과세대상 세액 기준 (최저한세 배제분 안분 차감)
    farm_min_credits = sum(
        c.amount for c in tax_credits if c.subject_to_min_tax and c.farm_surtax_taxable
    )
    farm_post_credits = sum(
        c.amount for c in tax_credits if not c.subject_to_min_tax and c.farm_surtax_taxable
    )
    # 배제분(excluded)은 최저한세 대상 감면(min_credits) 전체에서 발생 → 농특 과세분 비율만 안분
    farm_excluded = (excluded * farm_min_credits // min_credits) if min_credits > 0 else 0
    farm_allowed = farm_post_credits + max(0, farm_min_credits - farm_excluded)
    farm_surtax = int(farm_allowed * FARM_SURTAX_RATE)

    return {
        "산출세액": gross_tax,
        "최저한세_적용_감면합계": min_credits,
        "최저한세_미적용_감면합계": post_credits,
        "최저한세율": min_rate,
        "최저한세액": min_tax,
        "배제된_감면": excluded,
        "최종_세액": final_tax,
        "가산세": surtax,
        "기납부세액": prepaid_tax,
        "차감납부세액": final_due,
        "농어촌특별세": farm_surtax,
    }
