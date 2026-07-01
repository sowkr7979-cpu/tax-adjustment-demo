"""국가법령정보센터 Open API 클라이언트."""
from __future__ import annotations
import os
from datetime import date
from typing import Any

import requests


BASE_URL = "https://www.law.go.kr/DRF"  # 평문 HTTP → HTTPS (응답 무결성·OC키 보호)


def _collect_article_text(node: Any) -> list[str]:
    """조문단위 JSON에서 조문내용·항내용·호내용 등을 순서대로 평탄화."""
    out: list[str] = []
    if isinstance(node, dict):
        for key, val in node.items():
            if key.endswith("내용") and isinstance(val, str):
                stripped = val.strip()
                if stripped:
                    out.append(stripped)
            else:
                out.extend(_collect_article_text(val))
    elif isinstance(node, list):
        for item in node:
            out.extend(_collect_article_text(item))
    return out


class LawApiClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("LAW_API_KEY", "")
        self.session = requests.Session()

    # ── 조문 단위 원문 조회 (세무조정 근거 인용용) ───────────────────────────

    def get_article_text(
        self,
        law_id: str,
        jo: str,
        effective_date: date | None = None,
    ) -> str:
        """
        조문 단위 원문 조회.
        jo: 6자리 = 조번호 4자리 + 가지번호 2자리 (예: 제25조 → '002500', 제18조의2 → '001802')
        effective_date: 사업연도 종료일 — 그 시점 시행 법령 기준으로 조회
        """
        params: dict[str, Any] = {
            "OC": self.api_key,
            "target": "law",
            "ID": law_id,
            "JO": jo,
            "type": "JSON",
        }
        if effective_date:
            params["efYd"] = effective_date.strftime("%Y%m%d")
        resp = self.session.get(f"{BASE_URL}/lawService.do", params=params, timeout=30)
        resp.raise_for_status()
        jo_unit = resp.json().get("법령", {}).get("조문", {}).get("조문단위", {})
        # 조문단위가 list면 [전문(본문 없는 조 제목), 실제 조문] 순으로 오는 경우가 있어(법§52·조특§24 등)
        # 첫 요소만 취하면 본문이 통째로 누락된다 → 모든 단위의 본문을 연결(빈 단위는 자연 제외).
        if isinstance(jo_unit, list):
            parts: list[str] = []
            for _u in jo_unit:
                parts.extend(_collect_article_text(_u))
            return "\n".join(p for p in parts if p)
        return "\n".join(_collect_article_text(jo_unit))
