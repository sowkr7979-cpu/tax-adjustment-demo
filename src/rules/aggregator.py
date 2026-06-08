"""분개장 → 규칙 산식 입력값 자동 집계.

더존식 접근: 분개를 LLM에 보내지 않고 계정코드·증빙유형 기준으로 집계하여
규칙 산식 모듈(entertainment, penalty 등)의 입력값으로 변환한다.
4만 건 분개도 밀리초 단위로 처리된다.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from src.utils.models import JournalLine

# 기업업무추진비 적격증빙 기준 (법인세법 §25②: 경조사비 외 건당 3만원 초과 시
# 신용카드·세금계산서 등 적격증빙 미수취분은 손금불산입)
ENTERTAINMENT_RECEIPT_THRESHOLD = 30_000

# 계정코드 접두어 (classifier.py와 동일 체계 — 더존 Smart A 표준)
_ENTERTAINMENT_PREFIXES = ("8132",)
_PENALTY_PREFIXES = ("8391",)
_DIVIDEND_PREFIXES = ("711",)
_REVENUE_PREFIXES = ("4",)

_ENTERTAINMENT_KEYWORDS = ("기업업무추진비", "접대비")
_PENALTY_KEYWORDS = ("벌과금", "과태료", "가산세", "범칙금", "벌금")
_DIVIDEND_KEYWORDS = ("배당금수익", "수입배당금")

# 적격증빙으로 인정되는 증빙유형 키워드
_QUALIFIED_EVIDENCE = ("카드", "세금계산서", "계산서", "현금영수증")


def _is_account(line: JournalLine, prefixes: tuple[str, ...], keywords: tuple[str, ...]) -> bool:
    code = line.account_code.strip()
    if any(code.startswith(p) for p in prefixes):
        return True
    name = line.account_name.strip()
    return any(kw in name for kw in keywords)


def _has_qualified_evidence(line: JournalLine) -> bool:
    # 카드번호가 기재돼 있으면 증빙유형 칸이 비어 있어도 카드거래로 본다
    if (line.card_no or "").strip():
        return True
    ev = (line.evidence_type or "").strip()
    return any(q in ev for q in _QUALIFIED_EVIDENCE)


@dataclass
class EntertainmentAggregate:
    """기업업무추진비 집계 — calc_entertainment() 입력값."""
    total_expense: int = 0
    card_expense: int = 0
    culture_expense: int = 0        # 적요 기반 추정 — 수동 보정 권장
    traditional_expense: int = 0    # 적요 기반 추정 — 수동 보정 권장
    no_receipt_expense: int = 0     # 건당 3만원 초과 + 적격증빙 미수취
    no_receipt_lines: list[JournalLine] = field(default_factory=list)  # 감사추적용
    evidence_unknown: bool = False  # 분개장에 증빙 정보 자체가 없음 — 판정 불가 (수동 확인)


@dataclass
class PenaltyAggregate:
    """벌과금·과태료 집계 — 전액 손금불산입 (법인세법 §21)."""
    total: int = 0
    lines: list[JournalLine] = field(default_factory=list)  # 감사추적용


@dataclass
class JournalAggregates:
    entertainment: EntertainmentAggregate = field(default_factory=EntertainmentAggregate)
    penalty: PenaltyAggregate = field(default_factory=PenaltyAggregate)
    dividend_income: int = 0  # 수입배당금 (익금불산입 산식 입력)
    revenue: int = 0  # 수입금액 (손익계산서 우선, 분개 집계는 폴백)
    # 외화·파생 평가손익 (법§42③, 영§76) — '평가/환산' 계정만, 실현분(외환차손익) 제외
    forex_eval_gain: int = 0      # 외화환산이익
    forex_eval_loss: int = 0      # 외화환산손실
    derivative_eval_gain: int = 0 # 통화선도 등 평가이익
    derivative_eval_loss: int = 0 # 통화선도 등 평가손실
    corporate_tax: int = 0        # 법인세비용 (법§21 1호 — 전액 손금불산입)
    vehicle_expense: int = 0      # 업무용승용차 관련비용 (감가상각비 제외분)
    # 유가증권 평가손익 (법§42, 영§75 — 일반법인은 원가법만 인정, 평가손익 부인)
    securities_eval_gain: int = 0
    securities_eval_loss: int = 0
    # 충당금 당기 설정액 (대변 기준 — 법§33·34 한도 계산의 회사계상액)
    pension_provision: int = 0    # 퇴직급여충당부채 당기 전입액
    bad_debt_provision: int = 0   # 대손충당금 당기 설정액
    interest_expense: int = 0     # 이자비용 총액 (법§28 지급이자 손금불산입 기준금액)
    # 집계 항목별 매칭 분개 (계산 내역 드릴다운용 — 키: 항목명)
    detail_lines: dict[str, list[JournalLine]] = field(default_factory=dict)


def sum_related_party_revenue(
    journals: list[JournalLine], rp_names: list[str],
) -> tuple[int, list[JournalLine]]:
    """특수관계인 거래 수입금액 집계 (법§25④2호 단서 — 접대비 한도 적용률 ×10%).

    매출 계정(코드 4xx 또는 계정명 '매출')의 대변 중 거래처가 특수관계인
    목록과 일치하는 분개를 합산한다. 매출원가·할인·환입·에누리는 제외.
    반환: (합계, 매칭 분개 — 드릴다운용)
    """
    total = 0
    lines: list[JournalLine] = []
    if not rp_names:
        return 0, []
    _exclude = ("매출원가", "매출할인", "매출환입", "에누리")
    for ln in journals:
        name_ns = ln.account_name.replace(" ", "")
        is_rev = ln.account_code.strip().startswith("4") or "매출" in name_ns
        if not is_rev or any(k in name_ns for k in _exclude):
            continue
        if ln.credit <= 0:
            continue
        cp = (ln.counterparty_name or "").strip()
        if cp and any(nm in cp or cp in nm for nm in rp_names):
            total += ln.credit
            lines.append(ln)
    return total, lines


def aggregate_journals(journals: list[JournalLine]) -> JournalAggregates:
    """분개장 전체를 1회 순회하며 산식 입력값 집계."""
    agg = JournalAggregates()

    # 분개장에 증빙 정보가 아예 없으면 (WEHAGO 분개장 등) 증빙불비 판정 불가
    # — 전부 무증빙으로 오판하지 않도록 판정을 건너뛰고 플래그만 남긴다
    has_evidence_data = any(
        (ln.evidence_type or "").strip() or (ln.card_no or "").strip()
        for ln in journals
    )
    agg.entertainment.evidence_unknown = not has_evidence_data

    def _track(key: str, ln: JournalLine) -> None:
        """계산 내역 드릴다운용 분개 수집."""
        agg.detail_lines.setdefault(key, []).append(ln)

    for ln in journals:
        amount = ln.debit  # 비용 계정은 차변 기준

        # ── 기업업무추진비 ──
        if _is_account(ln, _ENTERTAINMENT_PREFIXES, _ENTERTAINMENT_KEYWORDS):
            if amount <= 0:
                continue
            e = agg.entertainment
            e.total_expense += amount
            _track("기업업무추진비", ln)
            qualified = _has_qualified_evidence(ln)
            if qualified and "카드" in (ln.evidence_type or ""):
                e.card_expense += amount
            if "문화" in ln.description:
                e.culture_expense += amount
            if "전통시장" in ln.description:
                e.traditional_expense += amount
            # 건당 3만원 초과 + 적격증빙 미수취 → 손금불산입 대상
            # (분개장에 증빙 정보가 없으면 판정하지 않음 — evidence_unknown 플래그 참조)
            if has_evidence_data and amount > ENTERTAINMENT_RECEIPT_THRESHOLD and not qualified:
                e.no_receipt_expense += amount
                e.no_receipt_lines.append(ln)
            continue

        # ── 벌과금·과태료 (전액 손금불산입) ──
        if _is_account(ln, _PENALTY_PREFIXES, _PENALTY_KEYWORDS):
            if amount <= 0:
                continue
            agg.penalty.total += amount
            agg.penalty.lines.append(ln)
            _track("벌과금·과태료·가산세", ln)
            continue

        # ── 수입배당금 (수익 계정 → 대변 기준) ──
        if _is_account(ln, _DIVIDEND_PREFIXES, _DIVIDEND_KEYWORDS):
            agg.dividend_income += ln.credit
            if ln.credit:
                _track("수입배당금", ln)
            continue

        name_ns = ln.account_name.replace(" ", "")

        # ── 외화환산손익 (평가분 — 외환차손익 실현분과 구분) ──
        if "외화환산이익" in name_ns:
            agg.forex_eval_gain += ln.credit
            if ln.credit:
                _track("외화환산이익", ln)
            continue
        if "외화환산손실" in name_ns:
            agg.forex_eval_loss += ln.debit
            if ln.debit:
                _track("외화환산손실", ln)
            continue

        # ── 충당금 당기 설정액 (대변 = 전입) ──
        if "퇴직급여충당" in name_ns:
            agg.pension_provision += ln.credit
            if ln.credit:
                _track("퇴직급여충당금 설정", ln)
            continue
        if "대손충당금" in name_ns:
            agg.bad_debt_provision += ln.credit
            if ln.credit:
                _track("대손충당금 설정", ln)
            continue

        # ── 유가증권 평가손익 (영§75 — 일반법인 원가법, 평가손익 전액 부인) ──
        if ("증권평가" in name_ns or "금융자산평가" in name_ns):
            if "이익" in name_ns:
                agg.securities_eval_gain += ln.credit
                if ln.credit:
                    _track("유가증권 평가이익", ln)
            elif "손실" in name_ns:
                agg.securities_eval_loss += ln.debit
                if ln.debit:
                    _track("유가증권 평가손실", ln)
            continue

        # ── 통화선도 등 파생상품 평가손익 (거래/정산 실현분 제외) ──
        if any(k in name_ns for k in ("통화선도", "파생상품", "스왑", "통화옵션")) and "평가" in name_ns:
            if "이익" in name_ns:
                agg.derivative_eval_gain += ln.credit
                if ln.credit:
                    _track("파생상품 평가이익", ln)
            elif "손실" in name_ns:
                agg.derivative_eval_loss += ln.debit
                if ln.debit:
                    _track("파생상품 평가손실", ln)
            continue

        # ── 법인세비용 (전액 손금불산입, 법§21 1호) ──
        # 차변만 집계 — 분개장에 결산 대체분개(손익 마감 대변)가 포함될 수 있음
        if ln.account_code.strip().startswith("998") or name_ns in ("법인세비용", "법인세등"):
            agg.corporate_tax += ln.debit
            if ln.debit:
                _track("법인세비용", ln)
            continue

        # ── 업무용승용차 관련비용 ──
        if any(k in name_ns for k in ("차량유지비", "차량비")):
            agg.vehicle_expense += ln.debit
            if ln.debit:
                _track("업무용승용차 관련비용", ln)
            continue

        # ── 이자비용 (법§28 지급이자 손금불산입의 기준금액) ──
        if "이자비용" in name_ns or "사채이자" in name_ns:
            agg.interest_expense += ln.debit
            if ln.debit:
                _track("이자비용", ln)
            continue

        # ── 가지급금·대여금 (법§52 인정이자, 법§28①4호나목 — 드릴다운용 트래킹) ──
        if any(k in name_ns for k in ("가지급금", "대여금", "주임종")):
            if ln.debit or ln.credit:
                _track("가지급금·대여금", ln)
            continue

        # ── 수입금액 폴백 (손익계산서 없을 때) ──
        if ln.account_code.strip().startswith(_REVENUE_PREFIXES):
            agg.revenue += ln.credit

    return agg
