"""세액공제·감면 + 최저한세 계산 — 조세특례제한법 제132조."""
from src.utils.constants import get_min_tax_rate
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
    }
