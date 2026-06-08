"""세무 컨설팅 토픽 — 로컬 LLM 문장화(선택·보조).

가드레일 (security·KICPA 리뷰 합의):
  - 토픽·숫자·법령·요건은 규칙엔진(consulting.py)이 결정 — LLM은 **권고 문장의 톤만** 다듬는다.
  - 새로운 사실·숫자·법령·금액을 만들지 않는다(환각 차단). 실패·미가동 시 원문 유지.
  - 외부 API 금지 — 로컬 Ollama만. 출력은 항상 '검토 초안(미확정)'.
"""
from __future__ import annotations

from src.llm.ollama_client import OllamaClient

_SYSTEM = (
    "너는 한국 세무 자문 보조다. 주어진 '권고' 문장을 고객이 이해하기 쉬운 부드러운 한국어로 "
    "다듬기만 한다. 다음 규칙을 반드시 지켜라: "
    "(1) 새로운 사실·숫자·금액·법령조문·세액효과를 절대 추가하지 마라. 주어진 내용만 바꿔 쓴다. "
    "(2) 단정하지 말고 '검토가 필요합니다/유리할 수 있습니다' 같은 미확정 어조를 쓴다. "
    "(3) 각 항목을 2~3문장 이내로 간결하게. "
    '반드시 JSON 배열로만 답하라: [{"title": "원래 제목 그대로", "narration": "다듬은 문장"}]'
)


def narrate_topics(topics: list, client: OllamaClient | None = None) -> dict[str, str]:
    """토픽 권고를 고객친화 문장으로 다듬어 {title: narration} 반환.

    LLM 미가동·실패·항목 누락 시 해당 토픽은 원문 suggestion을 유지한다(안전 폴백).
    """
    if not topics:
        return {}
    client = client or OllamaClient()
    # 규칙엔진 산출(제목·권고)만 전달 — 숫자·법령은 프롬프트에 넣지 않아 LLM이 손대지 못하게 한다
    _payload = [{"title": t.title, "권고": t.suggestion} for t in topics]
    import json
    prompt = (
        "다음 세무 자문 항목들의 '권고' 문장만 다듬어라. 제목은 그대로 두고 narration만 작성:\n"
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
                _title = str(item.get("title", "")).strip()
                _narr = str(item.get("narration", "")).strip()
                if _title and _narr:
                    out[_title] = _narr
    # 폴백 — 다듬지 못한 토픽은 원문 권고 유지
    for t in topics:
        out.setdefault(t.title, t.suggestion)
    return out
