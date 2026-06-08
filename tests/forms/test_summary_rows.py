"""소득금액조정합계표 행 — 동적 소득처분(영§106) 테스트."""
from datetime import date

from src.forms.summary_rows import adjustment_rows
from src.rules.disposition import UNSET_DISPOSITION
from src.utils.models import TaxAdjustmentResult


def _r(**kw):
    r = TaxAdjustmentResult(
        fiscal_year_start=date(2025, 1, 1),
        fiscal_year_end=date(2025, 12, 31),
        is_sme=True,
    )
    for k, v in kw.items():
        setattr(r, k, v)
    return r


def _add(rows, name):
    return [x for x in rows[0] if x[1] == name]


def _ded(rows, name):
    return [x for x in rows[1] if x[1] == name]


def test_legacy_single_deemed_interest_row():
    """choices 미전달(레거시) → 인정이자 단일 행, 기존 라벨 유지."""
    r = _r(deemed_interest=12_000_000,
           deemed_interest_parties=[{"name": "김", "amount": 8_000_000},
                                    {"name": "법인", "amount": 4_000_000}])
    add, _ = adjustment_rows(r)  # 레거시
    rows = _add((add, _), "가지급금 인정이자")
    assert len(rows) == 1
    assert rows[0][2] == 12_000_000 and rows[0][4] == "상여 등"


def test_per_party_disposition():
    """choices 전달 → 거래상대방별 행 + 귀속자별 처분."""
    r = _r(deemed_interest=12_000_000,
           deemed_interest_parties=[{"name": "김", "amount": 8_000_000},
                                    {"name": "법인", "amount": 4_000_000}])
    choices = {"인정이자|김": "임원·직원", "인정이자|법인": "법인등"}
    add, _ = adjustment_rows(r, choices)
    kim = _add((add, _), "가지급금 인정이자 (김)")[0]
    corp = _add((add, _), "가지급금 인정이자 (법인)")[0]
    assert kim[2] == 8_000_000 and kim[4] == "상여"
    assert corp[2] == 4_000_000 and corp[4] == "기타사외유출"


def test_unselected_party_is_flagged():
    """choices는 있으나 해당 상대방 미선택 → 검토필요 처분."""
    r = _r(deemed_interest=8_000_000,
           deemed_interest_parties=[{"name": "김", "amount": 8_000_000}])
    add, _ = adjustment_rows(r, {})  # 빈 choices(비레거시)
    kim = _add((add, _), "가지급금 인정이자 (김)")[0]
    assert kim[4] == UNSET_DISPOSITION


def test_unknown_creditor_split_rows():
    """채권자불분명 사채이자 — 원천세 분리 시 2행."""
    r = _r(interest_unknown_creditor=10_000_000)
    choices = {"채권자불분명 사채이자|원천세": 2_500_000}
    add, _ = adjustment_rows(r, choices)
    rows = _add((add, _), "채권자불분명 사채이자")
    assert sorted([(x[2], x[4]) for x in rows]) == sorted(
        [(2_500_000, "기타사외유출"), (7_500_000, "대표자상여")])


def test_vehicle_disposition_split():
    """업무용승용차 — 개인사용분(귀속자) + 감가상각 한도초과(유보) 분리."""
    r = _r(vehicle_disallowed=10_000_000, vehicle_depr_excess=3_000_000)
    add, _ = adjustment_rows(r, {"업무용승용차 개인사용분": "임원·직원"})
    personal = _add((add, _), "업무용승용차 개인사용분")[0]
    depr = _add((add, _), "업무용승용차 감가상각 한도초과")[0]
    assert personal[2] == 7_000_000 and personal[4] == "상여"
    assert depr[2] == 3_000_000 and depr[4] == "유보"


def test_party_sum_mismatch_falls_back_single():
    """상대방 합이 총액과 다르면(약정이자 차감 등) 단일 행으로 폴백."""
    r = _r(deemed_interest=10_000_000,  # 총액 ≠ 상대방 합(12M)
           deemed_interest_parties=[{"name": "김", "amount": 12_000_000}])
    add, _ = adjustment_rows(r, {"인정이자|김": "주주"})
    assert len(_add((add, _), "가지급금 인정이자")) == 1
    assert _add((add, _), "가지급금 인정이자 (김)") == []


def test_nonreal_name_interest_split_rows():
    """비실명 채권·증권이자(법§28①2호) — 원천세 분리 시 2행 (1호와 동일 처분)."""
    r = _r(interest_nonreal_name=10_000_000)
    add, ded = adjustment_rows(r, {"비실명 채권·증권이자|원천세": 3_000_000})
    rows = _add((add, ded), "비실명 채권·증권이자")
    assert sorted([(x[2], x[4]) for x in rows]) == sorted(
        [(3_000_000, "기타사외유출"), (7_000_000, "대표자상여")])


def test_section18_4_5_6_deduct_rows():
    """법§18 4·5·6호 익금불산입이 차감조정 행으로 출력된다 (신규 분기)."""
    r = _r(debt_relief_offset=5_000_000,
           refund_interest_excluded=1_500_000,
           vat_output_excluded=500_000)
    add, ded = adjustment_rows(r)
    assert _ded((add, ded), "자산수증익·채무면제익 (이월결손금 보전)")[0][2] == 5_000_000
    assert _ded((add, ded), "국세환급금 이자")[0][2] == 1_500_000
    assert _ded((add, ded), "부가가치세 매출세액")[0][2] == 500_000
    # 모두 '기타' 처분 (사외유출 아님)
    assert all(_ded((add, ded), n)[0][4] == "기타" for n in
               ("국세환급금 이자", "부가가치세 매출세액"))


def test_unfair_transaction_per_line_disposition():
    """부당행위 — 건별 내역 있으면 건별 행 + 건별 소득처분 (영§106)."""
    r = _r(unfair_transaction=70_000_000,
           unfair_transaction_lines=[
               {"amount": 50_000_000, "disposition": "배당", "basis": "법§52, 영§88③", "ref": "J3|5"},
               {"amount": 20_000_000, "disposition": "상여", "basis": "법§52, 영§88③", "ref": ""},
           ])
    add, ded = adjustment_rows(r, {})
    배당 = _add((add, ded), "부당행위계산 부인 (J3|5)")[0]
    상여 = _add((add, ded), "부당행위계산 부인")[0]
    assert 배당[2] == 50_000_000 and 배당[4] == "배당"
    assert 상여[2] == 20_000_000 and 상여[4] == "상여"


def test_unfair_transaction_legacy_single_row():
    """건별 내역 없으면(총액 폴백) 단일 행."""
    r = _r(unfair_transaction=30_000_000)
    add, ded = adjustment_rows(r, {})
    rows = _add((add, ded), "부당행위계산 부인")
    assert len(rows) == 1 and rows[0][2] == 30_000_000


def test_welfare_per_line_disposition():
    """복리후생비(열거 외) — 건별 행 + 건별 소득처분."""
    r = _r(welfare_disallowed=6_000_000,
           welfare_disallowed_lines=[
               {"amount": 4_000_000, "disposition": "상여", "basis": "영§45①", "ref": "J1|2"},
               {"amount": 2_000_000, "disposition": "배당", "basis": "영§45①", "ref": ""},
           ])
    add, ded = adjustment_rows(r, {})
    상여 = _add((add, ded), "복리후생비 (열거 외) (J1|2)")[0]
    배당 = _add((add, ded), "복리후생비 (열거 외)")[0]
    assert 상여[2] == 4_000_000 and 상여[4] == "상여"
    assert 배당[2] == 2_000_000 and 배당[4] == "배당"


def test_deemed_dividend_per_line_rows():
    """의제배당 — 건별 익금산입 행 (법§16①)."""
    r = _r(deemed_dividend=40_000_000,
           deemed_dividend_lines=[
               {"amount": 40_000_000, "disposition": "유보", "basis": "법§16①", "ref": "J7|1"},
           ])
    add, ded = adjustment_rows(r, {})
    row = _add((add, ded), "의제배당 (J7|1)")[0]
    assert row[0] == "익금산입" and row[2] == 40_000_000


def test_prior_reserve_reversal_rows():
    """전기 유보 추인 — 익금산입(가산)·손금산입(차감) 양방향 행."""
    r = _r(prior_reserve_reversal_add=5_000_000,
           prior_reserve_reversal_deduct=12_000_000)
    add, ded = adjustment_rows(r)
    assert _add((add, ded), "전기 △유보 추인")[0][2] == 5_000_000
    assert _ded((add, ded), "전기 유보 추인")[0][2] == 12_000_000
