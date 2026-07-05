"""AI 검토 보조 — 회계사가 선택한 검토 큐에만 로컬 LLM 적용."""
from __future__ import annotations
import hashlib
from datetime import date

from src.llm.ollama_client import OllamaClient
from src.rules.legal_basis import fetch_articles_for_issues
from src.utils.models import (
    IssueCode, JournalLine, LLMAnalysisResult, RuleClassificationResult,
)

PROMPT_VERSION = "v0.2"  # v0.2: 법령 조문 첨부 (수준 1 RAG)

_SYSTEM_PROMPT = """당신은 대한민국 법인세 세무조정 전문 분석 AI입니다.
아래 전표 묶음에 대해 세무조정 필요 여부와 근거를 JSON 형식으로 분석하십시오.

판단 원칙:
- 프롬프트에 [적용 법령] 조문이 제시되면 반드시 그 조문을 우선 근거로 판단할 것
- legal_basis_candidates에는 제시된 조문을 인용할 것 (임의로 지어내지 말 것)
- 금액을 직접 계산하지 말 것 (규칙 엔진이 담당)
- 세무조정 후보 여부와 근거만 제시할 것
- 확신이 없으면 review_required: true로 표시할 것
- 모든 출력은 반드시 JSON 배열로만 출력할 것

출력 스키마 (배열 원소):
{
  "journal_id": "전표번호",
  "line_id": 라인번호,
  "issue_possible": true/false,
  "tax_issue_code": "이슈코드",
  "tax_adjustment_type": "손금불산입_후보|익금산입_후보|...",
  "affected_amount": 금액,
  "confidence_score": 0.0~1.0,
  "review_required": true/false,
  "review_reason": "사유",
  "evidence_fields": {"적요": "...", "거래처명": "..."},
  "legal_basis_candidates": [{"법령": "법인세법 제XX조", "내용": "...", "기준일": "YYYY-MM-DD"}],
  "target_form_candidates": ["별지 제XX호서식"]
}"""


def _mask_pii(text: str) -> str:
    """계좌번호, 주민등록번호 패턴 마스킹."""
    import re
    text = re.sub(r"\d{3}-\d{2}-\d{6}", "***-**-******", text)
    text = re.sub(r"\d{6}-\d{7}", "******-*******", text)
    return text


def _escape_injection(text: str) -> str:
    """프롬프트 인젝션 방어: 시스템 프롬프트 관련 특수 시퀀스 제거."""
    dangerous = ["<|system|>", "<|user|>", "<|assistant|>", "###", "---SYSTEM"]
    for d in dangerous:
        text = text.replace(d, "")
    return text


def _build_journal_text(lines: list[JournalLine]) -> str:
    rows = []
    for ln in lines:
        desc = _escape_injection(_mask_pii(ln.description))
        rows.append(
            f"전표:{ln.journal_id} 라인:{ln.line_no} 날짜:{ln.date} "
            f"계정:{ln.account_code} {ln.account_name} "
            f"적요:{desc} 거래처:{ln.counterparty_name} "
            f"차변:{ln.debit:,} 대변:{ln.credit:,} 증빙:{ln.evidence_type}"
        )
    return "\n".join(rows)


class JournalAnalyzer:
    def __init__(
        self,
        client: OllamaClient,
        fiscal_year_end: date,
        company_name: str,
        is_sme: bool,
        related_parties: list[str],
    ) -> None:
        self.client = client
        self.fiscal_year_end = fiscal_year_end
        self.company_name = company_name
        self.is_sme = is_sme
        self.related_parties = related_parties

    def analyze_batch(
        self,
        journals: list[JournalLine],
        rule_results: list[RuleClassificationResult],
        batch_size: int = 5,
        progress_callback=None,
        issue_filter: set[str] | None = None,
    ) -> list[LLMAnalysisResult]:
        """LLM 대상으로 선별된 분개를 배치 단위로 정밀 분석.

        batch_size: CPU 추론 실측 기준 분개 1건당 약 1분 소요 (gemma4, 12 tok/s).
                    배치 5건 ≈ 5분 → 600초 타임아웃 내 안전.
        progress_callback: callable(done: int, total: int) — 배치 완료마다 호출.
        issue_filter: 분석할 이슈코드 집합 — None이면 2차 대상 전체,
                      지정 시 해당 이슈코드로 분류된 분개만 분석 (사용자 선택).
        """
        # 2차 분석 대상만 필터 (issue_filter 지정 시 선택된 이슈코드만)
        def _selected(r: RuleClassificationResult) -> bool:
            if not r.forward_to_stage2:
                return False
            if issue_filter is None:
                return True
            code = r.rule_issue_code.value if r.rule_issue_code is not None else "UNKNOWN"
            return code in issue_filter

        target_ids = {r.journal_id for r in rule_results if _selected(r)}
        # 전표 → 1차 분류 이슈코드 (법령 조문 첨부용)
        issue_by_journal: dict[str, str] = {
            r.journal_id: r.rule_issue_code.value
            for r in rule_results
            if _selected(r) and r.rule_issue_code is not None
        }
        target_lines = [j for j in journals if j.journal_id in target_ids]
        # 이슈코드별로 정렬 — 같은 배치가 같은 조문을 공유하도록 (조문 첨부 효율↑)
        target_lines.sort(key=lambda j: issue_by_journal.get(j.journal_id, ""))

        results: list[LLMAnalysisResult] = []
        total = len(target_lines)
        for i in range(0, total, batch_size):
            batch = target_lines[i : i + batch_size]
            batch_issues = frozenset(
                issue_by_journal[j.journal_id]
                for j in batch if j.journal_id in issue_by_journal
            )
            results.extend(self._analyze_batch(batch, batch_issues))
            if progress_callback:
                progress_callback(min(i + batch_size, total), total)
        return results

    def _analyze_batch(
        self,
        lines: list[JournalLine],
        issue_codes: frozenset[str] = frozenset(),
    ) -> list[LLMAnalysisResult]:
        sme_str = "중소기업" if self.is_sme else "일반법인"
        rp_str = ", ".join(self.related_parties[:20]) if self.related_parties else "없음"

        # 수준 1 RAG — 이슈 관련 조문을 국가법령정보센터에서 받아 프롬프트에 첨부
        # (기준일 = 사업연도 종료일 시행 법령. 조회 실패 시 조문 없이 진행)
        law_context = ""
        if issue_codes:
            articles = fetch_articles_for_issues(issue_codes, str(self.fiscal_year_end))
            if articles:
                law_context = (
                    f"## 적용 법령 (국가법령정보센터, {self.fiscal_year_end} 시행 기준)\n"
                    f"{articles}\n\n"
                )

        user_prompt = (
            f"{law_context}"
            f"법인명: {self.company_name} | {sme_str}\n"
            f"사업연도 종료일(법령기준일): {self.fiscal_year_end}\n"
            f"특수관계인: [{rp_str}]\n\n"
            f"분개 목록:\n{_build_journal_text(lines)}"
        )

        raw = self.client.generate_json(user_prompt, system=_SYSTEM_PROMPT)
        if not isinstance(raw, list):
            raw = [raw] if isinstance(raw, dict) else []

        prompt_hash = hashlib.sha256(
            (PROMPT_VERSION + _SYSTEM_PROMPT).encode()
        ).hexdigest()[:12]

        parsed: list[LLMAnalysisResult] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                # 모델이 enum 외 자유 텍스트 코드를 반환해도 항목을 버리지 않는다
                _code_raw = str(item.get("tax_issue_code", "UNKNOWN"))
                try:
                    _issue = IssueCode(_code_raw)
                except ValueError:
                    _issue = IssueCode.UNKNOWN
                _adj_type = str(item.get("tax_adjustment_type", ""))
                if _issue is IssueCode.UNKNOWN and _code_raw not in ("", "UNKNOWN"):
                    _adj_type = f"{_adj_type} [모델코드: {_code_raw}]".strip()

                result = LLMAnalysisResult(
                    journal_id=str(item.get("journal_id", "")),
                    line_id=int(item.get("line_id") or 0),
                    issue_possible=bool(item.get("issue_possible", False)),
                    tax_issue_code=_issue,
                    tax_adjustment_type=_adj_type,
                    affected_amount=int(item.get("affected_amount", 0) or 0),
                    confidence_score=float(item.get("confidence_score") or 0.0),
                    review_required=bool(item.get("review_required", True)),
                    review_reason=str(item.get("review_reason") or ""),
                    evidence_fields=item.get("evidence_fields") or {},
                    legal_basis_candidates=item.get("legal_basis_candidates") or [],
                    target_form_candidates=item.get("target_form_candidates") or [],
                    stage1_confidence=None,
                    stage2_confidence=float(item.get("confidence_score") or 0.0),
                )
                parsed.append(result)
            except (ValueError, KeyError, TypeError):
                continue
        return parsed
