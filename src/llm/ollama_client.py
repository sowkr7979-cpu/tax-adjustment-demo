"""Ollama 로컬 LLM 클라이언트."""
from __future__ import annotations
import json
import os
import re

import requests


class OllamaClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model = model or os.environ.get("OLLAMA_MODEL", "gemma4:latest")

    def generate(self, prompt: str, system: str = "", temperature: float = 0.1) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "format": "json",  # JSON 출력 강제 (파싱 실패 방지)
            "options": {
                "temperature": temperature,
                "num_ctx": 8192,  # 기본 4096은 시스템 프롬프트 + 분개 배치에 부족
            },
        }
        resp = requests.post(f"{self.base_url}/api/generate", json=payload, timeout=600)
        resp.raise_for_status()
        return resp.json().get("response", "")

    def generate_json(self, prompt: str, system: str = "") -> list | dict:
        """JSON 출력 강제. 파싱 실패 시 빈 리스트 반환."""
        raw = self.generate(prompt, system=system)
        parsed = None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # ```json ... ``` 블록 추출 시도
            match = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
            if match:
                try:
                    parsed = json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
        if parsed is None:
            return []
        # 모델이 {"results": [...]} 처럼 객체로 감싼 경우 내부 배열을 추출
        if isinstance(parsed, dict):
            list_values = [v for v in parsed.values() if isinstance(v, list)]
            if len(list_values) == 1:
                return list_values[0]
        return parsed

    def is_available(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False
