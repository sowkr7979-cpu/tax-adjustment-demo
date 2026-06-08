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
    bibang_applied: bool = False  # 영§26⑥⑦ 정률법 비망가액 특례 적용 (미상각잔액 전액 상각)
    bibang_partial_review: bool = False  # 월할 자산이 비망가액 임계 근처 — 처분/단기사업연도 회계사 확인


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

    # 영§26⑥·⑦ — 정률법 비망가액 특례 (law.go.kr 003608 JO=002600 제6·7항, efYd 사업연도 종료일 확인):
    #   정률법 잔존가액은 취득가액의 5%이며, 미상각잔액이 '최초로' 취득가액의 5% 이하가 되는
    #   사업연도에 그 잔존가액을 상각범위액에 가산한다(⑥). 다만 비망가액으로 취득가액의 5%와
    #   1천원 중 적은 금액을 남기고 손금산입하지 않는다(⑦).
    #   → 그 사업연도 상각범위액 = 미상각잔액 − min(취득가액×5%, 1,000원).
    #   ⚠ 5% 기준은 '취득가액'이지 '미상각잔액'이 아님(영§26⑥). 비망가액 1,000원 하드코딩 금지
    #     (취득가액 2만원 이하 소액자산은 취득가액×5%가 1,000원보다 작아 그 값이 비망가액).
    #   ⚠ 월할(months<12) 자산은 특례를 발동하지 않는다 (law.go.kr 확인 — 영§26⑨·법§55의2 체계):
    #     · 월할 규정 영§26⑨는 '기중 취득(신규 사용)연도'만 대상이고, 취득연도는 미상각잔액이 취득가액의
    #       5% 이하로 떨어질 수 없다(논리상 발동 불가).
    #     · 처분연도는 잔여 미상각잔액이 상각(손금)이 아니라 처분손익으로 실현된다 — 전액상각하면
    #       상각·처분손익 이중인식(과대상각). 영§26⑦도 '감가상각이 종료되는 자산의 장부가액'을 전제하므로
    #       장부에서 제거되는 처분자산엔 성립하지 않는다.
    #     → 말기 정상(12개월) 사업연도의 비망가액 도달만 특례 대상. 처분연도 월할일수·단기사업연도는
    #       회계사 판단 영역(bibang_partial_review로 노출).
    bibang_applied = False
    bibang_partial_review = False
    if method == "정률법" and rate > 0.0 and acquisition_cost > 0:
        five_pct = acquisition_cost * 0.05
        # 발동 판정은 '연 환산' 상각 후 잔액 기준 — 월할로 줄어든 formula_limit가 아니라
        # 미상각잔액이 취득가액 5% 이하 구간에 진입했는지로 본다(영§26⑥ '최초로 5% 이하').
        _full_year_limit = int(max(0, base) * rate)
        _near_threshold = max(0, base) - _full_year_limit <= five_pct
        if _near_threshold and asset.months >= 12:
            bibang = min(int(five_pct), 1000)           # 영§26⑦
            formula_limit = max(0, int(max(0, base) - bibang))
            bibang_applied = True
        elif _near_threshold and asset.months < 12:
            # 월할 자산이면서 비망가액 임계 근처 — 기중 처분/단기사업연도면 처분손익 귀속 확인 필요
            bibang_partial_review = True

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
        bibang_applied=bibang_applied,
        bibang_partial_review=bibang_partial_review,
    )


def calc_depreciation_all(assets: list[FixedAsset]) -> list[DepreciationResult]:
    return [calc_depreciation(a) for a in assets]
