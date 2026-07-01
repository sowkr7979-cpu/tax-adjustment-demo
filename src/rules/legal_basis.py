"""세무조정 항목 ↔ 국가법령정보센터(law.go.kr) 조문 매핑.

프로젝트 원칙: 모든 법인세 세무조정은 국가법령정보를 기반으로 한다.
각 조정 항목은 반드시 이 매핑을 통해 기준일(사업연도 종료일) 시점의
법령 조문 원문과 연결되어야 한다.
"""
from __future__ import annotations
from datetime import date
from functools import lru_cache

from src.apis.law_api import LawApiClient

# 국가법령정보센터 법령ID (현행)
LAW_CORP_TAX = "001563"          # 법인세법
LAW_CORP_TAX_DECREE = "003608"   # 법인세법 시행령
LAW_CORP_TAX_RULE = "007229"     # 법인세법 시행규칙
LAW_SPECIAL_TAX = "001584"       # 조세특례제한법
LAW_SPECIAL_TAX_DECREE = "004920"  # 조세특례제한법 시행령
LAW_FARM_SURTAX = "001569"       # 농어촌특별세법
LAW_NATIONAL_TAX_BASIC = "001586"  # 국세기본법

# TaxAdjustmentResult 필드명 → (표시명, 법령ID, 조문번호 JO 6자리)
# JO: 조번호 4자리 + 가지번호 2자리 (제18조의2 → "001802")
ADJUSTMENT_LEGAL_BASIS: dict[str, tuple[str, str, str]] = {
    # ── 가산조정 (익금산입·손금불산입) ──
    "depreciation_excess":       ("법인세법 제23조 (감가상각비의 손금불산입)",        LAW_CORP_TAX,        "002300"),
    "depreciation_bibang_residual": ("법인세법 시행령 제26조제6항·제7항 (정률법 비망가액 — 취득가액 5%·1천원)", LAW_CORP_TAX_DECREE, "002600"),
    "entertainment_excess":      ("법인세법 제25조 (기업업무추진비의 손금불산입)",     LAW_CORP_TAX,        "002500"),
    "entertainment_no_receipt":  ("법인세법 제25조제2항 (적격증빙 미수취)",           LAW_CORP_TAX,        "002500"),
    "donation_excess":           ("법인세법 제24조 (기부금의 손금불산입)",            LAW_CORP_TAX,        "002400"),
    "pension_excess":            ("법인세법 제33조 (퇴직급여충당금의 손금산입)",       LAW_CORP_TAX,        "003300"),
    "bad_debt_excess":           ("법인세법 제34조 (대손충당금의 손금산입)",          LAW_CORP_TAX,        "003400"),
    "penalty":                   ("법인세법 제21조 (세금과 공과금의 손금불산입)",      LAW_CORP_TAX,        "002100"),
    "interest_unknown_creditor": ("법인세법 제28조제1항제1호 (채권자불분명 사채이자)", LAW_CORP_TAX,        "002800"),
    "interest_nonreal_name":     ("법인세법 제28조제1항제2호 (비실명 채권·증권의 이자)", LAW_CORP_TAX,       "002800"),
    "vehicle_disallowed":        ("법인세법 제27조의2 (업무용승용차 관련비용)",        LAW_CORP_TAX,        "002702"),
    "vehicle_depr_excess":       ("법인세법 제27조의2제3항 (승용차 감가상각비 한도초과·이월)", LAW_CORP_TAX,    "002702"),
    "officer_bonus_excess":      ("법인세법 시행령 제43조제2항 (임원 상여금 한도초과·법§26 위임)", LAW_CORP_TAX_DECREE, "004300"),
    "officer_retirement_excess": ("법인세법 시행령 제44조 (퇴직급여의 손금불산입)",     LAW_CORP_TAX_DECREE, "004400"),
    "interest_construction":     ("법인세법 제28조 (지급이자의 손금불산입)",          LAW_CORP_TAX,        "002800"),
    "interest_non_business":     ("법인세법 제28조제1항제4호 (업무무관자산 지급이자)", LAW_CORP_TAX,        "002800"),
    "corporate_tax_expense":     ("법인세법 제21조 (세금과 공과금의 손금불산입)",      LAW_CORP_TAX,        "002100"),
    "forex_loss_disallowed":     ("법인세법 제42조 (자산·부채의 평가)",               LAW_CORP_TAX,        "004200"),
    "derivative_loss_disallowed": ("법인세법 시행령 제76조 (외화자산 등의 평가)",      LAW_CORP_TAX_DECREE, "007600"),
    "forex_gain_excluded":       ("법인세법 제42조 (자산·부채의 평가)",               LAW_CORP_TAX,        "004200"),
    "derivative_gain_excluded":  ("법인세법 시행령 제76조 (외화자산 등의 평가)",       LAW_CORP_TAX_DECREE, "007600"),
    "securities_loss_disallowed": ("법인세법 시행령 제75조 (유가증권의 평가)",         LAW_CORP_TAX_DECREE, "007500"),
    "securities_gain_excluded":  ("법인세법 시행령 제75조 (유가증권의 평가)",          LAW_CORP_TAX_DECREE, "007500"),
    "inventory_adjustment":      ("법인세법 시행령 제74조 (재고자산의 평가)",          LAW_CORP_TAX_DECREE, "007400"),
    "welfare_disallowed":        ("법인세법 시행령 제45조 (복리후생비의 손금불산입)",   LAW_CORP_TAX_DECREE, "004500"),
    "joint_expense_excess":      ("법인세법 시행령 제48조 (공동경비의 손금불산입)",     LAW_CORP_TAX_DECREE, "004800"),
    "non_business_expense":      ("법인세법 제27조 (업무와 관련 없는 비용)",           LAW_CORP_TAX,        "002700"),
    "punitive_damages":          ("법인세법 제21조의2 (징벌적 목적의 손해배상금)",      LAW_CORP_TAX,        "002102"),
    "deemed_interest":           ("법인세법 시행령 제89조 (시가의 범위 등·인정이자)",  LAW_CORP_TAX_DECREE, "008900"),
    "unfair_transaction":        ("법인세법 제52조 (부당행위계산의 부인)",            LAW_CORP_TAX,        "005200"),
    "deemed_dividend":           ("법인세법 제16조 (배당금 또는 분배금의 의제)",       LAW_CORP_TAX,        "001600"),
    "deemed_rental":             ("조세특례제한법 제138조 (임대보증금 등의 간주익금)",  LAW_SPECIAL_TAX,     "013800"),
    # 전기 △유보 추인(익금산입) — 추인 근거는 유보 발생 시 부인 조문에 따름(항목별 상이).
    #   대표 조문으로 법§34③(대손충당금 환입)을 둠 — 표시명에 '항목별 확인'을 명시해 대손충당금 오인 방지.
    "prior_reserve_reversal_add": ("전기 △유보의 당기 추인 (근거는 유보 발생 시 부인 조문 — 항목별 확인 필요; 예: 대손충당금 법§34③·감가상각 법§23)", LAW_CORP_TAX, "003400"),
    # ── 차감조정 (손금산입·익금불산입) ──
    "depreciation_approved":     ("법인세법 제23조 (전기 부인액 추인)",               LAW_CORP_TAX,        "002300"),
    # 전기 유보 추인(손금산입) — 추인 근거는 유보 발생 시 부인 조문에 따름(항목별 상이).
    "prior_reserve_reversal_deduct": ("전기 유보의 당기 추인 (근거는 유보 발생 시 부인 조문 — 항목별 확인 필요; 예: 대손충당금 법§34③·감가상각 법§23)", LAW_CORP_TAX, "003400"),
    "donation_carryforward_deduction": ("법인세법 제24조제5항·제6항 (이월 기부금 우선공제)", LAW_CORP_TAX,    "002400"),
    "dividend_exclusion":        ("법인세법 제18조의2 (수입배당금액의 익금불산입)",    LAW_CORP_TAX,        "001802"),
    "debt_relief_offset":        ("법인세법 제18조제6호 (자산수증익·채무면제익 중 이월결손금 보전 충당액 익금불산입)", LAW_CORP_TAX, "001800"),
    "refund_interest_excluded":  ("법인세법 제18조제4호 (국세·지방세 과오납 환급금 이자 익금불산입)", LAW_CORP_TAX, "001800"),
    "vat_output_excluded":       ("법인세법 제18조제5호 (부가가치세 매출세액 익금불산입)", LAW_CORP_TAX, "001800"),
    # ── 세액 (산출세액 이후) ──
    "farm_surtax":               ("농어촌특별세법 제5조 (과세표준과 세율 — 감면세액 20%)", LAW_FARM_SURTAX, "000500"),
    "land_transfer_tax":         ("법인세법 제55조의2 (토지등 양도소득에 대한 법인세)", LAW_CORP_TAX, "005502"),
    "surtax":                    ("국세기본법 제47조의2~4 (무신고·과소신고·납부지연 가산세)", LAW_NATIONAL_TAX_BASIC, "004702"),
    "pension_deduction":         ("법인세법 시행령 제44조의2 (퇴직연금 부담금 손금산입)", LAW_CORP_TAX_DECREE, "004402"),
    # ── 결손금 소급공제 환급 (세액 산정 후 별건 — 별지68호) ──
    "loss_carryback_refund":     ("법인세법 제72조 (중소기업의 결손금 소급공제에 따른 환급 — 영§110)", LAW_CORP_TAX, "007200"),
}


# 마지막으로 법령 원문 조회에 성공한 시각 — UI '법령 기준일' 표시용
LAST_LAW_FETCH_OK: str = ""


@lru_cache(maxsize=128)
def _fetch_article_cached(law_id: str, jo: str, effective_date_str: str) -> str:
    """조문 원문 조회 (법령ID·조문번호 직접 지정, 캐시됨). 실패 시 빈 문자열."""
    global LAST_LAW_FETCH_OK
    try:
        ef = date.fromisoformat(effective_date_str)
        text = LawApiClient().get_article_text(law_id, jo, ef)
        if text:
            from datetime import datetime
            LAST_LAW_FETCH_OK = datetime.now().strftime("%Y-%m-%d %H:%M")
        return text
    except Exception:
        return ""


def fetch_legal_text(field_name: str, effective_date_str: str) -> str:
    """조정 항목 필드명으로 기준일 시점 조문 원문 조회 (캐시됨).

    effective_date_str: 'YYYY-MM-DD' (lru_cache 적용을 위해 문자열로 받음)
    실패 시 빈 문자열 반환 — UI에서 '조회 실패' 안내 처리.
    """
    basis = ADJUSTMENT_LEGAL_BASIS.get(field_name)
    if basis is None:
        return ""
    _, law_id, jo = basis
    return _fetch_article_cached(law_id, jo, effective_date_str)


# 1차 규칙 분류 이슈코드(IssueCode.value) → 조문 매핑 — LLM 분석 시 조문 첨부용 (수준 1 RAG)
ISSUE_TO_ARTICLE: dict[str, tuple[str, str, str]] = {
    "ENTERTAINMENT_EXPENSE":    ("법인세법 제25조 (기업업무추진비)",        LAW_CORP_TAX,        "002500"),
    "DONATION_CLASSIFICATION":  ("법인세법 제24조 (기부금)",               LAW_CORP_TAX,        "002400"),
    "CONSTRUCTION_INTEREST":    ("법인세법 제28조 (지급이자)",             LAW_CORP_TAX,        "002800"),
    "OFFICER_BONUS":            ("법인세법 제26조 (과다경비)",             LAW_CORP_TAX,        "002600"),
    "OFFICER_RETIREMENT":       ("법인세법 시행령 제44조 (임원 퇴직급여)",   LAW_CORP_TAX_DECREE, "004400"),
    "VEHICLE_EXPENSE":          ("법인세법 제27조의2 (업무용승용차)",       LAW_CORP_TAX,        "002702"),
    "PENALTY":                  ("법인세법 제21조 (세금과 공과금)",         LAW_CORP_TAX,        "002100"),
    "FOREX_TRANSACTION":        ("법인세법 제42조 (자산·부채의 평가)",      LAW_CORP_TAX,        "004200"),
    "DIVIDEND_INCOME":          ("법인세법 제18조의2 (수입배당금)",         LAW_CORP_TAX,        "001802"),
    "DEBT_FORGIVENESS":         ("법인세법 제18조 (평가이익 등의 익금불산입)", LAW_CORP_TAX,       "001800"),
    "ASSET_GIFT":               ("법인세법 제18조 (평가이익 등의 익금불산입)", LAW_CORP_TAX,       "001800"),
    "BAD_DEBT":                 ("법인세법 제34조 (대손충당금)",            LAW_CORP_TAX,        "003400"),
    "RELATED_PARTY_LOAN":       ("법인세법 제52조 (부당행위계산 부인)",      LAW_CORP_TAX,        "005200"),
    "RELATED_PARTY_TRANSACTION": ("법인세법 제52조 (부당행위계산 부인)",     LAW_CORP_TAX,        "005200"),
    "DEPRECIATION_MISMATCH":    ("법인세법 제23조 (감가상각비)",            LAW_CORP_TAX,        "002300"),
}


def fetch_articles_for_issues(
    issue_codes: frozenset[str] | set[str],
    effective_date_str: str,
    max_articles: int = 2,
    max_chars: int = 900,
) -> str:
    """이슈코드 집합에 해당하는 조문 원문을 LLM 프롬프트용으로 조회.

    max_articles·max_chars: 로컬 LLM 컨텍스트(8192토큰) 보호를 위한 상한.
    실패한 조문은 건너뛴다 (LLM 분석 자체는 계속 진행).
    """
    parts: list[str] = []
    for code in sorted(issue_codes)[:max_articles]:
        basis = ISSUE_TO_ARTICLE.get(code)
        if basis is None:
            continue
        name, law_id, jo = basis
        text = _fetch_article_cached(law_id, jo, effective_date_str)
        if text:
            parts.append(f"[{name}]\n{text[:max_chars]}")
    return "\n\n".join(parts)
