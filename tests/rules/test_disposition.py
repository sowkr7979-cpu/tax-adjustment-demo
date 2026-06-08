"""소득처분 결정 — 영§106① 단위 테스트."""
from src.rules.disposition import (
    resolve_disposition, split_unknown_creditor_interest, UNSET_DISPOSITION,
)


def test_attribution_mapping():
    assert resolve_disposition("주주") == "배당"
    assert resolve_disposition("임원·직원") == "상여"
    assert resolve_disposition("법인등") == "기타사외유출"
    assert resolve_disposition("기타") == "기타소득"
    assert resolve_disposition("불분명") == "대표자상여"


def test_unset_when_missing():
    assert resolve_disposition(None) == UNSET_DISPOSITION
    assert resolve_disposition("") == UNSET_DISPOSITION
    assert resolve_disposition("이상한값") == UNSET_DISPOSITION


def test_unknown_creditor_split():
    out = split_unknown_creditor_interest(10_000_000, 2_500_000)
    assert out == [(2_500_000, "기타사외유출"), (7_500_000, "대표자상여")]


def test_unknown_creditor_no_withholding():
    assert split_unknown_creditor_interest(10_000_000, 0) == [(10_000_000, "대표자상여")]


def test_unknown_creditor_clamp():
    # 원천세가 총액을 초과하면 전액 기타사외유출
    assert split_unknown_creditor_interest(5_000_000, 9_000_000) == [(5_000_000, "기타사외유출")]
