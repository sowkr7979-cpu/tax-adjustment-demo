"""검토필요 항목 근거법령·해석(_GUIDANCE) — law.go.kr 검증 매핑·정정 회귀 테스트."""
from datetime import date

from src.rules.coverage import run_coverage_check, _GUIDANCE, _CHECKLIST
from src.utils.models import JournalLine


def _ln(acc, name, desc="", debit=1_000_000) -> JournalLine:
    return JournalLine(
        journal_id="J", line_no=0, date=date(2025, 5, 1), account_code=acc,
        account_name=name, description=desc, counterparty_code="", counterparty_name="",
        debit=debit, credit=0, evidence_type="", evidence_no="", card_no="",
        vehicle_no="", project="", source_file="", source_sheet="S", source_row=1,
    )


def test_review_items_carry_law_basis_and_interpretation():
    """검토필요 항목은 law_id·jo·해석을 모두 갖는다."""
    cov = run_coverage_check([_ln("1300", "외화환산이익", "평가")])
    c = next(c for c in cov if c.item == "외화자산·부채 평가손익")
    assert c.status == "검토필요"
    assert c.law_id and c.jo and c.interpretation
    assert "확인이 필요" in c.interpretation  # ADR-002 — 단정 아닌 검토포인트 어조


def test_corrected_legal_basis_strings():
    """🔴 law-compliance 정정 반영 — 임원상여 영§43②, 외화평가 법§42①②."""
    cov = run_coverage_check([
        _ln("801", "상여금", "임원상여"),
        _ln("1300", "외화환산손실", "평가"),
    ])
    basis = {c.item: c.legal_basis for c in cov}
    assert basis["임원 상여금 한도"] == "법§26, 영§43②"        # ①(이익처분)→② 정정
    assert basis["외화자산·부채 평가손익"] == "법§42①②, 영§76"   # ③(평가손실)→①② 정정


def test_guidance_covers_all_review_specs():
    """_GUIDANCE가 검토필요(auto_calc=False) 카탈로그 항목을 모두 덮는지 — 누락 방지."""
    review_items = {s.item for s in _CHECKLIST if not s.auto_calc}
    missing = review_items - set(_GUIDANCE)
    assert not missing, f"_GUIDANCE 해석 누락: {missing}"


def test_guidance_jo_is_six_digits():
    """JO는 원문 조회용 6자리(조4+가지2)."""
    for item, g in _GUIDANCE.items():
        assert len(g["jo"]) == 6 and g["jo"].isdigit(), f"{item} JO 형식 오류: {g['jo']}"
        assert g["law_id"] in ("001563", "003608", "001584", "007229", "004920")
