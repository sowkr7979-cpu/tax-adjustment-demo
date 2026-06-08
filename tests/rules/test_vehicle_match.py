"""업무용승용차 근거분개 ↔ 차량번호 매칭 — 오매칭 방지·공통 포함 검증."""
from datetime import date

from src.rules.vehicle_match import (
    extract_plate, line_plate, registered_plates, filter_vehicle_lines,
    attribute_by_vehicle,
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
