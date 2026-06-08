"""세율·한도·이자율 상수. 세법 개정 시 이 파일만 갱신한다."""
from datetime import date
from dataclasses import dataclass


@dataclass(frozen=True)
class TaxRateEntry:
    lower: int
    upper: int | None  # None = 상한 없음
    rate: float
    deduction: int  # 누진공제액


@dataclass(frozen=True)
class TaxRateTable:
    effective_from: date
    law_ref: str
    brackets: list[TaxRateEntry]


_RATE_TABLES: list[TaxRateTable] = [
    TaxRateTable(
        effective_from=date(2023, 1, 1),
        law_ref="법인세법 제55조 (2022.12.31. 개정)",
        brackets=[
            TaxRateEntry(0, 200_000_000, 0.09, 0),
            TaxRateEntry(200_000_000, 20_000_000_000, 0.19, 20_000_000),
            TaxRateEntry(20_000_000_000, 300_000_000_000, 0.21, 420_000_000),
            TaxRateEntry(300_000_000_000, None, 0.24, 9_420_000_000),
        ],
    ),
    TaxRateTable(
        effective_from=date(2026, 1, 1),
        law_ref="법인세법 제55조 (2025 개정, 1%p 인상)",
        brackets=[
            TaxRateEntry(0, 200_000_000, 0.10, 0),
            TaxRateEntry(200_000_000, 20_000_000_000, 0.20, 20_000_000),
            TaxRateEntry(20_000_000_000, 300_000_000_000, 0.22, 420_000_000),
            TaxRateEntry(300_000_000_000, None, 0.25, 9_420_000_000),
        ],
    ),
]


def get_tax_rate_table(fiscal_year_start: date) -> TaxRateTable:
    """사업연도 개시일 기준 세율 테이블 선택 (신고연도 기준 아님)."""
    table = _RATE_TABLES[0]
    for t in _RATE_TABLES:
        if fiscal_year_start >= t.effective_from:
            table = t
    return table


# 최저한세율 (조세특례제한법 제132조)
MIN_TAX_RATE_SME = 0.07

def get_min_tax_rate(tax_base: int, is_sme: bool) -> float:
    if is_sme:
        return MIN_TAX_RATE_SME
    if tax_base <= 10_000_000_000:
        return 0.10
    elif tax_base <= 100_000_000_000:
        return 0.12
    return 0.17


# 당좌대출이자율 (국세청 고시 — 매년 갱신, 규칙§43②: 현행 연 1,000분의 46 = 4.6%)
PRIME_RATE_BY_YEAR: dict[int, float] = {
    2023: 0.046,
    2024: 0.046,
    2025: 0.046,
}
_PRIME_RATE_DEFAULT = 0.046


def is_prime_rate_published(fiscal_year: int) -> bool:
    """해당 사업연도의 당좌대출이자율 고시값이 테이블에 등록되어 있는지."""
    return fiscal_year in PRIME_RATE_BY_YEAR


def get_prime_rate(fiscal_year: int) -> float:
    """당좌대출이자율. 미등록 연도는 최근 등록 연도값으로 폴백(고시 확인 필요).

    고시 변경 모니터링 누락 방지를 위해 등록 여부는 is_prime_rate_published()로 확인.
    """
    if fiscal_year in PRIME_RATE_BY_YEAR:
        return PRIME_RATE_BY_YEAR[fiscal_year]
    # 미등록 → 가장 가까운(최근) 등록 연도값 폴백
    if PRIME_RATE_BY_YEAR:
        _nearest = min(PRIME_RATE_BY_YEAR, key=lambda y: abs(y - fiscal_year))
        return PRIME_RATE_BY_YEAR[_nearest]
    return _PRIME_RATE_DEFAULT


# 농어촌특별세율 — 조특법 감면세액분 (농특세법§5① 1호)
FARM_SURTAX_RATE = 0.20

# 기업업무추진비 기본한도
ENTERTAINMENT_BASE_SME = 36_000_000
ENTERTAINMENT_BASE_GENERAL = 12_000_000

# 업무용승용차 한도 (법§27의2③, 영§50의2⑦·⑮ — 2025-12-31 시행 기준 law.go.kr 확인)
VEHICLE_DEPRECIATION_ANNUAL_LIMIT = 8_000_000       # 감가상각비 연 한도 (일반)
VEHICLE_DEPRECIATION_LIMIT_SPECIFIED = 4_000_000    # 특정법인 (영§50의2⑮: 800만→400만)
VEHICLE_NO_LOGBOOK_LIMIT = 15_000_000               # 운행기록부 미작성 전액인정 한도 (영§50의2⑦)
VEHICLE_NO_LOGBOOK_LIMIT_SPECIFIED = 5_000_000      # 특정법인 (영§50의2⑮: 1,500만→500만)

# 이월결손금 공제 한도 비율
LOSS_CARRYFORWARD_SME_RATE = 1.0
LOSS_CARRYFORWARD_GENERAL_RATE = 0.8
