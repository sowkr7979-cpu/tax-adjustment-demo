"""감가상각비 세무조정 — 법인세법 제23조, 시행령 제26~28조.

영§26② (law.go.kr 원문 확인 — 2025-12-31 시행):
  정액법: 취득가액 × 내용연수에 따른 상각률 (균등 상각)
  정률법: 미상각잔액(취득가액 − 이미 손금에 산입한 상각액) × 상각률
          → 세무상 미상각잔액 = 회사 장부가액 + 전기 부인누계(유보) − 의제상각누계
  월할: 사업연도 중 취득 자산은 사용 월수 비례 (영§26⑨)

⚠ 고정자산대장의 '세무상한도' 컬럼은 회계 프로그램·회사에 따라 당기 상각비가
  들어 있는 경우가 있어 신뢰하지 않는다 — 항상 법령 산식으로 독립 계산하고,
  대장 기재값은 검증(대사)용으로만 표시한다.
"""
from dataclasses import dataclass

from src.utils.models import FixedAsset


@dataclass
class DepreciationResult:
    asset_code: str
    asset_name: str
    tax_limit: int          # 세무상 상각범위액 (법령 산식으로 계산한 값)
    company_depr: int       # 회사 계상 상각비
    excess: int             # 한도초과액 (손금불산입, 유보)
    approved: int           # 당기 시인액 (전기 부인액 환입, 손금산입)
    denial_end: int         # 당기말 부인누계액
    # ── 산식 검증 정보 ──
    method: str = ""        # 적용 상각방법
    base_amount: int = 0    # 상각기초가액 (정액법: 취득가액 / 정률법: 세무상 미상각잔액)
    applied_rate: float = 0.0  # 적용 상각률
    months: int = 12        # 월수
    ledger_limit: int = 0   # 고정자산대장 기재 '세무상한도' (대사용 — 계산에 사용 안 함)
    limit_mismatch: bool = False  # 산식 계산값과 대장 기재값의 불일치 (1% 초과 차이)
    rate_missing: bool = False    # 상각률·내용연수 모두 없어 대장값으로 폴백


def _rate_of(asset: FixedAsset) -> float:
    """적용 상각률: 대장의 상각률 우선, 없으면 1/내용연수 (정액법 기본)."""
    if 0.0 < asset.depr_rate <= 1.0:
        return asset.depr_rate
    if asset.useful_life:
        return 1.0 / asset.useful_life
    return 0.0


def calc_depreciation(asset: FixedAsset) -> DepreciationResult:
    """자산 단건 감가상각 세무조정 — 상각범위액은 항상 영§26② 산식으로 계산."""
    rate = _rate_of(asset)
    acquisition_cost = (
        asset.book_value_start + asset.accumulated_depr_start + asset.new_acquisition
    )

    if asset.method in ("정률법", "배율법"):
        # 정률법: 미상각잔액 = 취득가액 − 손금산입 상각누계
        #        = 회사 장부가액 + 전기 부인누계(아직 손금 아님) − 의제상각누계
        base = (
            asset.book_value_start + asset.new_acquisition
            + asset.denied_depr_start - asset.deemed_depr_start
        )
        method = "정률법"
    else:
        # 정액법: 취득가액 기준 균등 상각 (장부가액 기준 아님 — 영§26②1호)
        base = acquisition_cost
        method = "정액법"

    formula_limit = int(max(0, base) * rate * asset.months / 12)

    rate_missing = rate <= 0.0
    if rate_missing and asset.tax_depr_limit > 0:
        # 상각률·내용연수가 모두 없으면 산식 계산 불가 — 대장값으로 폴백 (경고 표시)
        tax_limit = asset.tax_depr_limit
    else:
        tax_limit = formula_limit

    ledger = asset.tax_depr_limit
    mismatch = (
        ledger > 0 and not rate_missing
        and abs(ledger - formula_limit) > max(formula_limit, 1) * 0.01
    )

    excess = max(0, asset.company_depr - tax_limit)
    # 전기 부인누계 중 당기 상각 여력만큼 시인
    spare = max(0, tax_limit - asset.company_depr)
    approved = min(asset.denied_depr_start, spare)
    denial_end = asset.denied_depr_start + excess - approved

    return DepreciationResult(
        asset_code=asset.asset_code,
        asset_name=asset.asset_name,
        tax_limit=tax_limit,
        company_depr=asset.company_depr,
        excess=excess,
        approved=approved,
        denial_end=denial_end,
        method=method,
        base_amount=int(max(0, base)),
        applied_rate=rate,
        months=asset.months,
        ledger_limit=ledger,
        limit_mismatch=mismatch,
        rate_missing=rate_missing,
    )


def calc_depreciation_all(assets: list[FixedAsset]) -> list[DepreciationResult]:
    return [calc_depreciation(a) for a in assets]
