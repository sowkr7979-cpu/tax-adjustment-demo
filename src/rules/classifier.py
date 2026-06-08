"""1차 규칙 기반 분개 분류 — LLM 없이 계정코드·거래처 매핑."""
from __future__ import annotations

from src.utils.models import IssueCode, JournalLine, RuleClassificationResult

# 계정코드 접두어 → (이슈코드, 2차분석필요여부)
# 더존 Smart A 표준 코드 기준 — 실제 코드 체계에 맞게 조정 필요
_ACCOUNT_MAP: dict[str, tuple[IssueCode, bool]] = {
    # 기업업무추진비 계열
    "81320": (IssueCode.ENTERTAINMENT_EXPENSE, True),   # 기업업무추진비
    "81321": (IssueCode.ENTERTAINMENT_EXPENSE, True),
    # 기부금
    "81310": (IssueCode.DONATION_CLASSIFICATION, True),
    # 이자비용
    "83100": (IssueCode.CONSTRUCTION_INTEREST, True),   # 이자비용 (건설자금 포함 의심)
    # 임원급여
    "81010": (IssueCode.OFFICER_BONUS, True),           # 임원급여
    "81011": (IssueCode.OFFICER_BONUS, True),
    "81020": (IssueCode.OFFICER_RETIREMENT, True),      # 임원퇴직급여
    # 차량비용
    "81220": (IssueCode.VEHICLE_EXPENSE, True),         # 차량유지비
    "81221": (IssueCode.VEHICLE_EXPENSE, True),
    # 벌과금 → LLM 없이 규칙 엔진 직행
    "83910": (IssueCode.PENALTY, False),
    "83911": (IssueCode.PENALTY, False),
    # 외화환산손익
    "84200": (IssueCode.FOREX_TRANSACTION, False),
    "84201": (IssueCode.FOREX_TRANSACTION, False),
    # 수입배당금
    "71100": (IssueCode.DIVIDEND_INCOME, False),
    # 채무면제익
    "71910": (IssueCode.DEBT_FORGIVENESS, True),
    # 자산수증익
    "71920": (IssueCode.ASSET_GIFT, True),
    # 대손충당금환입/대손금
    "83200": (IssueCode.BAD_DEBT, True),
}

# 계정명 키워드 → 이슈코드 (코드 매핑 실패 시 폴백)
_NAME_KEYWORDS: list[tuple[str, IssueCode, bool]] = [
    ("기업업무추진비", IssueCode.ENTERTAINMENT_EXPENSE, True),
    ("접대비", IssueCode.ENTERTAINMENT_EXPENSE, True),
    ("기부금", IssueCode.DONATION_CLASSIFICATION, True),
    ("이자비용", IssueCode.CONSTRUCTION_INTEREST, True),
    ("임원급여", IssueCode.OFFICER_BONUS, True),
    ("임원퇴직", IssueCode.OFFICER_RETIREMENT, True),
    ("차량", IssueCode.VEHICLE_EXPENSE, True),
    ("벌과금", IssueCode.PENALTY, False),
    ("과태료", IssueCode.PENALTY, False),
    ("외화환산", IssueCode.FOREX_TRANSACTION, False),
    ("배당금수익", IssueCode.DIVIDEND_INCOME, False),
    ("채무면제", IssueCode.DEBT_FORGIVENESS, True),
    ("자산수증", IssueCode.ASSET_GIFT, True),
    ("가지급금", IssueCode.RELATED_PARTY_LOAN, True),
    ("대여금", IssueCode.RELATED_PARTY_LOAN, True),
]


def classify_journal(
    line: JournalLine,
    related_parties: set[str],
) -> RuleClassificationResult:
    """
    단일 분개 라인에 이슈 코드 부여.
    related_parties: 특수관계인 거래처코드·거래처명 집합
    """
    code = line.account_code.strip()
    name = line.account_name.strip()

    # 1) 계정코드 직접 매핑
    for prefix, (issue, forward) in _ACCOUNT_MAP.items():
        if code.startswith(prefix):
            return RuleClassificationResult(
                journal_id=line.journal_id,
                account_code=code,
                rule_issue_code=issue,
                forward_reason="계정코드_매핑",
                forward_to_stage2=forward,
            )

    # 2) 특수관계인 거래처 매칭
    counterparty = f"{line.counterparty_code}|{line.counterparty_name}"
    if any(rp in counterparty for rp in related_parties if rp):
        return RuleClassificationResult(
            journal_id=line.journal_id,
            account_code=code,
            rule_issue_code=IssueCode.RELATED_PARTY_TRANSACTION,
            forward_reason="특수관계인_매칭",
            forward_to_stage2=True,
        )

    # 3) 계정명 키워드 폴백
    for kw, issue, forward in _NAME_KEYWORDS:
        if kw in name:
            return RuleClassificationResult(
                journal_id=line.journal_id,
                account_code=code,
                rule_issue_code=issue,
                forward_reason="계정명_키워드",
                forward_to_stage2=forward,
            )

    # 4) 해당 없음
    return RuleClassificationResult(
        journal_id=line.journal_id,
        account_code=code,
        rule_issue_code=None,
        forward_reason=None,
        forward_to_stage2=False,
    )


def classify_all(
    lines: list[JournalLine],
    related_parties: set[str],
) -> list[RuleClassificationResult]:
    return [classify_journal(line, related_parties) for line in lines]
