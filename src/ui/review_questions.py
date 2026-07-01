"""건별 질문형 수기입력 — 공통 프레임 (데이터 모델 + 순수 로직).

설계: 1_기획설계/수기입력_건별질문_설계.md
각 세무조정 검토항목을 '건별 질문 카드'로 선언하고, 회계사의 답(answers)을
조정금액·소득처분·별지15호 행으로 연결한다. UI 렌더러는 render_*.py가 담당하고,
이 모듈은 렌더링과 무관한 '질문 표시 조건·처분 결정·금액 산정' 순수 로직만 둔다
(streamlit 비의존 — 단위 테스트 가능).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

# 입력 단위 — 항목 성격에 따라 다름 (KICPA 리뷰 반영)
#   line     분개 건별 (부당행위·기부금·지급이자·복리후생·의제배당)
#   officer  임원 1인별 (임원 상여·퇴직)
#   category 재고 종류별
#   item     항목 1회 (자산수증익·외화 토글)
UNITS = frozenset({"line", "officer", "category", "item"})


# ── 질문 종류 ────────────────────────────────────────────────────────────────
# yesno        예/아니오
# select       보기 중 택1
# amount       금액(원)
# number       일반 수치(근속연수 등, 원 아님)
# counterparty 거래상대방(분개 거래처에서 선택 또는 입력)
# date         일자
QUESTION_KINDS = frozenset({"yesno", "select", "amount", "number", "counterparty", "date"})


@dataclass(frozen=True)
class Question:
    id: str                              # 답 저장 키 (카드 내 고유)
    text: str                            # 질문 문구 (회계사 친화)
    kind: str                            # QUESTION_KINDS 중 하나
    options: tuple[str, ...] = ()        # select 보기
    help: str = ""                       # 법령·실무 도움말
    show_when: tuple[tuple[str, object], ...] = ()  # (답id, 기대값) 모두 충족 시만 노출

    def __post_init__(self) -> None:
        if self.kind not in QUESTION_KINDS:
            raise ValueError(f"알 수 없는 질문 종류: {self.kind}")
        if self.kind == "select" and not self.options:
            raise ValueError(f"select 질문 '{self.id}'에는 options가 필요합니다")


@dataclass(frozen=True)
class DispositionRule:
    """답 → 소득처분(영§106) 매핑. by_question 답을 mapping으로 변환."""
    by_question: str
    mapping: dict                        # {답값: 처분문자열}
    default: str = "검토필요"


@dataclass
class ReviewItemSpec:
    key: str                             # coverage 항목명과 동일 (연계 키)
    legal_basis: str                     # 표시용 근거 (예: "법§52, 영§88")
    unit: str                            # UNITS: line|officer|category|item
    questions: list[Question]
    # answers(dict[str, object]) → 조정금액(int). 0이면 조정 없음(행 미생성).
    amount_fn: Callable[[dict], int]
    disposition: DispositionRule | None = None
    detect_account_keywords: tuple[str, ...] = ()   # coverage 재사용 — 건 후보 추출
    target_label: str = ""               # 별지15호 행 표시명 (없으면 key)
    add_or_deduct: str = "add"           # "add"(가산조정) | "deduct"(차감조정)
    allow_total_fallback: bool = True    # 분개 미매칭 시 총액 폴백 허용
    # 을표 연계 (KICPA 리뷰 #4): 유보성 결과를 합산할 TaxAdjustmentResult 집계 필드명.
    #   None이면 사외유출·기타(자본금과적립금(을) 비대상).
    reserve_field: str | None = None
    # 법령 요건 게이트 (예: 영§88③ 3억/5%). answers→False면 조정 제외(금액 0 취급).
    gate_fn: Callable[[dict], bool] | None = None

    def __post_init__(self) -> None:
        if self.unit not in UNITS:
            raise ValueError(f"[{self.key}] 알 수 없는 unit: {self.unit}")
        if self.add_or_deduct not in ("add", "deduct"):
            raise ValueError("add_or_deduct must be 'add' or 'deduct'")
        ids = [q.id for q in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError(f"[{self.key}] 질문 id 중복")
        # show_when·disposition이 가리키는 질문 id가 실재하는지 검증
        idset = set(ids)
        for q in self.questions:
            for ref, _ in q.show_when:
                if ref not in idset:
                    raise ValueError(f"[{self.key}] '{q.id}'의 show_when이 없는 질문 '{ref}' 참조")
        if self.disposition and self.disposition.by_question not in idset:
            raise ValueError(
                f"[{self.key}] disposition.by_question '{self.disposition.by_question}' 미존재"
            )


# ── 순수 로직 ────────────────────────────────────────────────────────────────

def should_show(question: Question, answers: dict) -> bool:
    """show_when 조건(모두 충족 = AND)을 평가. 조건 없으면 항상 표시.

    expected 가 tuple/list/set 이면 '답이 그 중 하나(OR 멤버십)'로 해석한다
    (예: 거래유형이 '해당없음'만 아니면 노출).
    """
    for ref_id, expected in question.show_when:
        actual = answers.get(ref_id)
        if isinstance(expected, (tuple, list, set, frozenset)):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def visible_questions(spec: ReviewItemSpec, answers: dict) -> list[Question]:
    """현재 답 상태에서 노출되는 질문 목록 (decision tree 순차 평가)."""
    return [q for q in spec.questions if should_show(q, answers)]


def resolve_disposition(spec: ReviewItemSpec, answers: dict) -> str:
    """답 → 소득처분. 규칙 없으면 빈 문자열."""
    rule = spec.disposition
    if rule is None:
        return ""
    return rule.mapping.get(answers.get(rule.by_question), rule.default)


@dataclass
class LineResult:
    """건별 결과 — 별지15호 행·감사추적·을표 집계 생성 입력."""
    label: str
    amount: int
    disposition: str
    legal_basis: str
    add_or_deduct: str
    line_ref: str = ""              # 전표|행 등 분개 참조 (감사추적)
    reserve_field: str | None = None  # 유보성이면 합산할 집계 필드 (을표 연계)


def passes_gate(spec: ReviewItemSpec, answers: dict) -> bool:
    """법령 요건 게이트(영§88③ 등) 통과 여부. 게이트 없으면 항상 통과."""
    if spec.gate_fn is None:
        return True
    return bool(spec.gate_fn(answers))


def build_result(spec: ReviewItemSpec, answers: dict, line_ref: str = "") -> LineResult | None:
    """한 건(또는 항목 1회)의 답을 LineResult로 변환.

    법령 게이트 미통과(예: 영§88③ 3억/5% 미달) 또는 조정금액 0이면 None(행 미생성).
    """
    if not passes_gate(spec, answers):
        return None
    amount = int(spec.amount_fn(answers) or 0)
    if amount == 0:
        return None
    return LineResult(
        label=spec.target_label or spec.key,
        amount=amount,
        disposition=resolve_disposition(spec, answers),
        legal_basis=spec.legal_basis,
        add_or_deduct=spec.add_or_deduct,
        line_ref=line_ref,
        reserve_field=spec.reserve_field,
    )


def build_results(spec: ReviewItemSpec, answers_list: list[dict]) -> list[LineResult]:
    """저장된 건별 답 목록(.taxproj의 review_answers[key]) → 유효 LineResult 목록.

    각 답 dict의 '_ref'(전표|행 등)는 감사추적 line_ref로 전달. 게이트/0금액 건은 제외.
    """
    out: list[LineResult] = []
    for ans in answers_list or []:
        r = build_result(spec, ans, line_ref=str(ans.get("_ref", "")))
        if r is not None:
            out.append(r)
    return out
