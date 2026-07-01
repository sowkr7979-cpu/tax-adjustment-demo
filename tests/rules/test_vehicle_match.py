"""업무용승용차 근거분개 ↔ 차량번호 매칭 — 오매칭 방지·공통 포함 검증."""
from datetime import date

from src.rules.vehicle_match import (
    extract_plate, line_plate, registered_plates, filter_vehicle_lines,
    attribute_by_vehicle, allocate_other_expense,
)
from src.utils.models import JournalLine, FixedAsset


def _ln(desc="", vno="", debit=0) -> JournalLine:
    return JournalLine(
        journal_id="J1", line_no=0, date=date(2025, 3, 1),
        account_code="822", account_name="차량유지비", description=desc,
        counterparty_code="", counterparty_name="", debit=debit, credit=0,
        evidence_type="", evidence_no="", card_no="", vehicle_no=vno,
        project="", source_file="", source_sheet="", source_row=0,
    )


def _asset(name) -> FixedAsset:
    return FixedAsset(
        asset_code=name, asset_name=name, account_code="208",
        acquired_date=date(2022, 1, 1), category="차량운반구",
        book_value_start=0, accumulated_depr_start=0, denied_depr_start=0,
        deemed_depr_start=0, new_acquisition=0, disposal=0,
        useful_life=5, depr_rate=0.0, months=12, method="정률법",
        tax_depr_limit=0, company_depr=0, disposal_date=None,
    )


def test_extract_plate_formats():
    assert extract_plate("12가3456") == "12가3456"
    assert extract_plate("주유 12가 3456 휘발유") == "12가3456"   # 공백 정규화
    assert extract_plate("123허4567") == "123허4567"
    assert extract_plate("서울12가3456") == "12가3456"
    assert extract_plate("주유비 결제") is None
    assert extract_plate("") is None


def test_line_plate_prefers_vehicle_no_column():
    ln = _ln(desc="34나5678 적요", vno="12가3456")
    assert line_plate(ln) == "12가3456"   # 차량번호 컬럼 우선
    assert line_plate(_ln(desc="34나5678 주유")) == "34나5678"  # 컬럼 없으면 적요


def test_filter_excludes_other_vehicle_keeps_common_and_match():
    assets = [_asset("그랜저 12가3456")]
    plates = registered_plates(assets)
    assert plates == {"12가3456"}
    lines = [
        _ln(desc="12가3456 주유", debit=50_000),    # 등록 차량 → 포함
        _ln(desc="34나5678 주유", debit=60_000),    # 다른 차량 → 제외
        _ln(desc="세차비", debit=10_000),           # 식별불가(공통) → 포함
        _ln(desc="정비", vno="12가3456", debit=20_000),  # 컬럼 일치 → 포함
    ]
    kept, foreign = filter_vehicle_lines(lines, plates)
    assert [l.debit for l in kept] == [50_000, 10_000, 20_000]
    assert [l.debit for l in foreign] == [60_000]


def test_filter_no_plates_keeps_all():
    """등록 차량의 번호를 알 수 없으면(자산명에 번호 없음) 타차량 판정 불가 → 전부 유지."""
    assets = [_asset("차량운반구")]   # 번호 없음
    plates = registered_plates(assets)
    assert plates == set()
    lines = [_ln(desc="34나5678 주유", debit=1), _ln(desc="세차", debit=2)]
    kept, foreign = filter_vehicle_lines(lines, plates)
    assert len(kept) == 2 and foreign == []


def test_allocate_other_expense_preserves_total_and_attributes():
    """관련비용 차량별 귀속 — 매칭분 정확 귀속 + 공통/등록외 안분, 총액 보존."""
    a1, a2 = _asset("소나타 12가3456"), _asset("카니발 34나5678")
    a1.company_depr, a2.company_depr = 6_000_000, 4_000_000   # 안분 비율 6:4
    pool = [
        _ln(desc="12가3456 주유", debit=500_000),   # 소나타 매칭
        _ln(desc="정비", vno="34나5678", debit=300_000),  # 카니발 매칭(차량번호 컬럼)
        _ln(desc="세차 공통", debit=200_000),        # 공통(식별불가)
        _ln(desc="99수0000 타차량", debit=100_000),   # 등록외 → 안분 대상
    ]
    total = 1_100_000
    alloc = allocate_other_expense([a1, a2], pool, total)
    # 공통+등록외 = 1,100,000 − (500,000+300,000) = 300,000 → 6:4 안분 = 180,000 / 120,000
    assert alloc["소나타 12가3456"] == 500_000 + 180_000   # 680,000
    assert alloc["카니발 34나5678"] == 300_000 + 120_000   # 420,000
    assert sum(alloc.values()) == total                    # 총액 보존(세무조정 금액 불변)


def test_allocate_other_expense_preserves_total_with_rounding():
    """int 절사로도 총액 보존 — 나눠떨어지지 않는 공통분(마지막 차량 잔여 흡수)."""
    a1, a2, a3 = _asset("차량운반구1"), _asset("차량운반구2"), _asset("차량운반구3")
    a1.company_depr = a2.company_depr = a3.company_depr = 100  # 균등 1/3
    pool = []  # 매칭 없음 → 전액 공통
    # common=100, 1/3 = 33.33… → 33+33+34 = 100 (마지막이 잔여 흡수)
    alloc = allocate_other_expense([a1, a2, a3], pool, 100)
    assert sum(alloc.values()) == 100
    assert sorted(alloc.values()) == [33, 33, 34]
    # depr_sum=0 폴백도 보존
    b1, b2, b3 = _asset("X"), _asset("Y"), _asset("Z")  # company_depr=0
    alloc2 = allocate_other_expense([b1, b2, b3], [], 10)
    assert sum(alloc2.values()) == 10


def test_allocate_other_expense_no_plates_falls_back_to_ratio():
    """차량번호 식별 불가(자산명에 번호 없음) → 전액 감가상각비율 안분."""
    a1, a2 = _asset("차량운반구1"), _asset("차량운반구2")
    a1.company_depr, a2.company_depr = 7_000_000, 3_000_000
    pool = [_ln(desc="주유", debit=600_000), _ln(desc="정비", debit=400_000)]
    alloc = allocate_other_expense([a1, a2], pool, 1_000_000)
    assert alloc["차량운반구1"] == 700_000   # 7:3
    assert alloc["차량운반구2"] == 300_000
    assert sum(alloc.values()) == 1_000_000


def test_attribute_by_vehicle_exact_and_common():
    a1, a2 = _asset("소나타 12가3456"), _asset("카니발 34나5678")
    lines = [
        _ln(desc="12가3456 주유", debit=1),
        _ln(desc="34나5678 주유", debit=2),
        _ln(desc="99수0000 주유", debit=3),   # 등록 외 → 어느 차량에도 귀속 안 함
        _ln(desc="공통 세차", debit=4),         # 공통
    ]
    per = attribute_by_vehicle([a1, a2], lines)
    assert [l.debit for l in per["소나타 12가3456"]] == [1]
    assert [l.debit for l in per["카니발 34나5678"]] == [2]
    assert [l.debit for l in per["__공통__"]] == [4]
    # 99수0000(3)은 어디에도 없음
    assert all(l.debit != 3 for v in per.values() for l in v)
