"""Anthropic Claude API 클라이언트 (배포 데모 전용 — AI 검토 보조).

⚠️ 이 모듈은 '라이브 배포 데모'를 위해 로컬 Ollama를 대체한다.
   - 프로젝트 원칙(로컬 전용·외부 LLM 금지, ADR-001/002)은 실무 사용을 전제로 한 것이고,
     공개 데모에서 면접관이 라이브로 만져볼 수 있게 하려고 호스팅 LLM을 사용한다.
   - 데모에서는 반드시 더미(가상) 데이터만 사용한다. 실제 고객 세무자료 업로드 금지.

API 키는 절대 코드/깃에 넣지 않는다:
   - Streamlit Cloud: 앱 Settings → Secrets 에 ANTHROPIC_API_KEY 입력
   - 로컬: .streamlit/secrets.toml (gitignore) 또는 환경변수 ANTHROPIC_API_KEY

OllamaClient와 동일한 인터페이스(generate / generate_json / is_available / .model)를
노출해 JournalAnalyzer 등 하위 코드를 수정 없이 재사용한다.
"""
from __future__ import annotations

import json
import os
import re

# 기본 모델 — claude-api 스킬 권장 기본값. 공개 데모 비용을 낮추려면
# secrets/환경변수 ANTHROPIC_MODEL 을 "claude-haiku-4-5" 로 바꾸면 된다.
_DEFAULT_MODEL = "claude-opus-4-8"

# 검토 보조 응답은 짧은 JSON 배열 — 비스트리밍 안전 범위(<16k)
_MAX_TOKENS = 4096


def _secret(name: str) -> str:
    """st.secrets → 환경변수 순으로 비밀값 조회 (없으면 빈 문자열).

    키는 코드에 두지 않고 배포 플랫폼 Secrets/환경변수에서만 읽는다.
    """
    try:
        import streamlit as st  # 지연 임포트 — 테스트/비-Streamlit 환경 보호

        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.environ.get(name, "")


def _extract_json(raw: str):
    """모델 응답 문자열에서 JSON(배열/객체)을 관대하게 추출. 실패 시 []."""
    if not raw:
        return []
    # 1) 그대로 파싱
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # 2) ```json ... ``` 코드블록
    m = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # 3) 첫 배열/객체 구간 절단 추출 (프롬프트 앞뒤 서술 제거)
    for opn, cls in (("[", "]"), ("{", "}")):
        s, e = raw.find(opn), raw.rfind(cls)
        if 0 <= s < e:
            try:
                return json.loads(raw[s : e + 1])
            except json.JSONDecodeError:
                continue
    return []


class AnthropicClient:
    """Claude API 클라이언트 — OllamaClient 호환 인터페이스."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or _secret("ANTHROPIC_API_KEY")
        self.model = model or _secret("ANTHROPIC_MODEL") or _DEFAULT_MODEL
        self._client = None

    def _sdk(self):
        if self._client is None:
            import anthropic  # 지연 임포트 — 미설치 환경에서 import 시점 오류 방지

            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def generate(self, prompt: str, system: str = "", temperature: float = 0.1) -> str:
        """단일 응답 텍스트 반환. (Opus 4.8은 temperature 미지원 — 인자는 호환용, 미사용)"""
        resp = self._sdk().messages.create(
            model=self.model,
            max_tokens=_MAX_TOKENS,
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")

    def generate_json(self, prompt: str, system: str = "") -> list | dict:
        """JSON 응답 파싱. 실패 시 빈 리스트.

        시스템 프롬프트에 'JSON 배열로만 출력' 지시가 포함돼 있어도 모델이
        서술을 덧붙일 수 있어 관대한 추출을 사용한다. {"results": [...]} 처럼
        객체로 감싼 경우 내부 배열을 꺼낸다 (OllamaClient와 동일 동작).
        """
        raw = self.generate(prompt, system=system)
        parsed = _extract_json(raw)
        if isinstance(parsed, dict):
            list_values = [v for v in parsed.values() if isinstance(v, list)]
            if len(list_values) == 1:
                return list_values[0]
        return parsed

    def is_available(self) -> bool:
        """API 키가 구성돼 있으면 사용 가능으로 본다 (네트워크 호출 없음 — 렌더 비용 절감)."""
        return bool(self.api_key)
