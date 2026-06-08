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

    # ── 1단계: 별지서식 목록 조회 ──────────────────────────────────────────────

    def search_form_list(
        self,
        law_name: str = "법인세법 시행규칙",
        page: int = 1,
        display: int = 200,
    ) -> list[dict]:
        """
        target=licbyl + search=2(법령명 기준) 로 별지서식 목록 조회.
        반환: bylSeq, bylNm, bylNo, bylGbn 포함 리스트
        """
        params = {
            "OC": self.api_key,
            "target": "licbyl",
            "query": law_name,
            "search": 2,      # 법령명 기준 (기본값 1은 서식명만 검색 → 누락 위험)
            "type": "JSON",
            "display": display,
            "page": page,
        }
        resp = self.session.get(f"{BASE_URL}/lawSearch.do", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("bylList", {}).get("byl", [])

    # ── 2단계: 법령 본문 조회 (RAG용, 사업연도 종료일 기준) ──────────────────

    def get_law_text(self, law_id: str, effective_date: date) -> str:
        """
        target=law + efYd(시행일자) 파라미터로 기준일 시점 법령 조문 취득.
        """
        params = {
            "OC": self.api_key,
            "target": "law",
            "ID": law_id,
            "efYd": effective_date.strftime("%Y%m%d"),
            "type": "XML",
        }
        resp = self.session.get(f"{BASE_URL}/lawService.do", params=params, timeout=30)
        resp.raise_for_status()
        return resp.text

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
        if isinstance(jo_unit, list):
            jo_unit = jo_unit[0] if jo_unit else {}
        return "\n".join(_collect_article_text(jo_unit))

    # ── 3단계: 서식 파일 다운로드 URL 추적 ────────────────────────────────────

    def get_form_download_url(self, byl_seq: str) -> str | None:
        """서식 HWP/PDF 다운로드 URL 반환. 없으면 None."""
        params = {
            "OC": self.api_key,
            "target": "bylFile",
            "ID": byl_seq,
            "type": "JSON",
        }
        try:
            resp = self.session.get(f"{BASE_URL}/lawSearch.do", params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            files = data.get("bylFileList", {}).get("bylFile", [])
            if files:
                return files[0].get("fileUrl", None)
        except Exception:
            pass
        return None

    # ── 유틸: 법인세법 기준 서식 목록 전체 수집 ─────────────────────────────

    def fetch_all_forms(self) -> list[dict]:
        """페이지네이션 처리하여 법인세법 시행규칙 별지서식 전체 수집."""
        results = []
        page = 1
        while True:
            batch = self.search_form_list(page=page)
            if not batch:
                break
            results.extend(batch)
            if len(batch) < 200:
                break
            page += 1
        return results
