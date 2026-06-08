"""세무 컨설팅 시나리오 문장화 — 로컬 LLM 톤 다듬기(선택·보조).

가드레일 (security·KICPA 리뷰 합의):
  - 토픽·숫자·법령·요건·효과는 규칙엔진(consulting.py)이 결정 — LLM은 **시나리오 action의 톤만** 다듬는다.
  - effect·requirement·risk·숫자·법령은 프롬프트에서 제외 → LLM이 손대지 못한다(환각 차단, ADR-002).
  - 외부 API 금지 — 로컬 Ollama만. 출력은 항상 '검토 초안(미확정)'.
"""
from __future__ import annotations

from src.llm.ollama_client import OllamaClient
from src.rag.reference_retriever import format_reference

_SYSTEM = (
    "너는 한국 세무 자문 보조다. 주어진 '행동(action)' 문장을 고객이 이해하기 쉬운 부드러운 "
    "한국어로 다듬기만 한다. 다음 규칙을 반드시 지켜라: "
    "(1) 새로운 사실·숫자·금액·법령조문·세액효과를 절대 추가하지 마라. 주어진 행동 내용만 바꿔 쓴다. "
    "(2) 단정하지 말고 '검토가 필요합니다/유리할 수 있습니다' 같은 미확정 어조를 쓴다. "
    "(3) 각 항목을 2문장 이내로 간결하게. "
    "(4) '참고자료'가 주어지면 취지만 반영하되, 참고자료에 없는 숫자·법령·요건을 지어내지 마라. "
    '반드시 JSON 배열로만 답하라: [{"key": "주어진 key 그대로", "narration": "다듬은 문장"}]'
)


def _scenario_key(title: str, scenario_name: str) -> str:
    """토픽·시나리오 식별 키 (narration dict 키)."""
    return f"{title}␟{scenario_name}"


def narrate_topics(topics: list, client: OllamaClient | None = None) -> dict[str, str]:
    """토픽 시나리오 action을 고객친화 문장으로 다듬어 {key: narration} 반환.

    key = "{토픽 title}␟{시나리오 name}". LLM 미가동·실패·누락 시 원문 action 유지(안전 폴백).
    """
    if not topics:
        return {}
    client = client or OllamaClient()

    def _refs(t) -> list[str]:
        return [format_reference(r) for r in (getattr(t, "references", None) or [])]

    # 규칙엔진 산출 중 action만 전달 — effect·요건·숫자·법령은 프롬프트에서 제외(환각 차단).
    _payload = []
    for t in topics:
        for sc in (getattr(t, "scenarios", None) or []):
            _payload.append({
                "key": _scenario_key(t.title, sc.name),
                "action": sc.action,
                "참고자료": _refs(t),
            })
    if not _payload:
        return {}

    import json
    prompt = (
        "다음 세무 자문 '행동(action)' 문장만 다듬어라. key는 그대로 두고 narration만 작성:\n"
        + json.dumps(_payload, ensure_ascii=False)
    )
    try:
        result = client.generate_json(prompt, system=_SYSTEM)
    except Exception:
        result = []
    out: dict[str, str] = {}
    if isinstance(result, list):
        for item in result:
            if isinstance(item, dict):
                _key = str(item.get("key", "")).strip()
                _narr = str(item.get("narration", "")).strip()
                if _key and _narr:
                    out[_key] = _narr
    # 폴백 — 다듬지 못한 시나리오는 원문 action 유지
    for t in topics:
        for sc in (getattr(t, "scenarios", None) or []):
            out.setdefault(_scenario_key(t.title, sc.name), sc.action)
    return out
