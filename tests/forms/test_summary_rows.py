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
