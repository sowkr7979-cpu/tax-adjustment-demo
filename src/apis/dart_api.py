"""DART Open API 클라이언트 — 법인 기본정보 조회 + 회사명 검색."""
from __future__ import annotations
import io
import json
import os
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import requests


DART_URL = "https://opendart.fss.or.kr/api"


class DartApiError(Exception):
    """DART API 오류 (인증·한도 등) — '자료 없음'과 구분하기 위한 예외."""
_CACHE_DIR = Path.home() / ".cache" / "taxproj"
_CORP_CODE_CACHE = _CACHE_DIR / "corp_codes.json"
_CACHE_MAX_AGE_DAYS = 7


@dataclass
class CompanyBasicInfo:
    corp_code: str
    corp_name: str
    stock_code: str
    corp_cls: str       # Y:유가 / K:코스닥 / N:코넥스 / E:기타 (≠ 세법상 중소기업)
    jurir_no: str
    bizr_no: str        # 사업자등록번호
    adres: str
    hm_url: str
    ir_url: str
    phn_no: str
    est_dt: str         # 설립일 YYYYMMDD
    acc_mt: str         # 결산월 MM
    ceo_nm: str         # 대표자명
    industry_code: str  # 업종코드


# ── 캐시 유틸 ─────────────────────────────────────────────────────────────────

def _load_cache() -> list[dict] | None:
    """로컬 캐시에서 corp code 목록 로드. 7일 이상 지나면 None."""
    if not _CORP_CODE_CACHE.exists():
        return None
    mtime = date.fromtimestamp(_CORP_CODE_CACHE.stat().st_mtime)
    if (date.today() - mtime) > timedelta(days=_CACHE_MAX_AGE_DAYS):
        return None
    with open(_CORP_CODE_CACHE, encoding="utf-8") as f:
        return json.load(f)


def _save_cache(codes: list[dict]) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(_CORP_CODE_CACHE, "w", encoding="utf-8") as f:
        json.dump(codes, f, ensure_ascii=False)


# ── 클라이언트 ─────────────────────────────────────────────────────────────────

class DartApiClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("DART_API_KEY", "")
        self.session = requests.Session()

    # ── corp code 목록 ────────────────────────────────────────────────────────

    def _get_corp_codes(self) -> list[dict]:
        """DART corp code XML ZIP 다운로드 후 파싱. 7일간 로컬 캐시."""
        cached = _load_cache()
        if cached is not None:
            return cached

        resp = self.session.get(
            f"{DART_URL}/corpCode.xml",
            params={"crtfc_key": self.api_key},
            timeout=60,
        )
        resp.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            xml_name = next(n for n in zf.namelist() if n.lower().endswith(".xml"))
            xml_bytes = zf.read(xml_name)

        root = ET.fromstring(xml_bytes)
        codes = [
            {
                "corp_code": (item.findtext("corp_code") or "").strip(),
                "corp_name": (item.findtext("corp_name") or "").strip(),
                "stock_code": (item.findtext("stock_code") or "").strip(),
            }
            for item in root.findall(".//list")
            if (item.findtext("corp_code") or "").strip()
        ]
        _save_cache(codes)
        return codes

    def search_by_name(self, name: str, limit: int | None = None) -> list[dict]:
        """회사명으로 corp code 검색 (부분 일치). 정확 일치 → 접두 일치 → 포함 순.

        limit=None이면 매칭되는 모든 회사 반환 — 동일 상호·다른 업종 법인이
        다수 존재하므로 기본적으로 자르지 않는다.
        """
        if not name.strip():
            return []
        codes = self._get_corp_codes()
        q = name.strip().replace(" ", "")

        exact, prefix, contain = [], [], []
        for c in codes:
            cn = c["corp_name"].replace(" ", "")
            if cn == q:
                exact.append(c)
            elif cn.startswith(q):
                prefix.append(c)
            elif q in cn:
                contain.append(c)

        merged = exact + prefix + contain
        return merged[:limit] if limit else merged

    # ── 법인 기본정보 ─────────────────────────────────────────────────────────

    def get_financial_summary(
        self, corp_code: str, bsns_year: str | None = None,
    ) -> dict:
        """fnlttSinglAcnt — 매출액·자산총계 조회.
        반환: {"revenue": int|None, "total_assets": int|None, "year": str}
        """
        year = bsns_year or str(date.today().year - 1)
        params = {
            "crtfc_key": self.api_key,
            "corp_code": corp_code,
            "bsns_year": year,
            "reprt_code": "11011",   # 사업보고서
        }
        try:
            resp = self.session.get(
                f"{DART_URL}/fnlttSinglAcnt.json", params=params, timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            return {
                "revenue": None, "total_assets": None, "year": year,
                "fail_reason": f"네트워크 오류 — {type(e).__name__}. 인터넷 연결을 확인하세요.",
            }

        result: dict = {"revenue": None, "total_assets": None, "year": year, "fail_reason": ""}
        status = data.get("status")
        if status != "000":
            _STATUS_MSG = {
                "010": "등록되지 않은 API 키입니다 (.env의 DART_API_KEY 확인)",
                "011": "사용할 수 없는 API 키입니다",
                "013": f"{year}년 사업보고서 공시 자료가 없습니다 (비상장·미공시 법인 — 수기 입력 필요)",
                "020": "API 요청 한도 초과 — 잠시 후 다시 시도하세요",
                "800": "DART 시스템 점검 중",
            }
            result["fail_reason"] = _STATUS_MSG.get(
                status, f"DART 오류 (status={status}): {data.get('message', '')}"
            )
            return result

        for item in data.get("list", []):
            acct = item.get("account_nm", "")
            raw  = item.get("thstrm_amount", "").replace(",", "").replace(" ", "")
            try:
                amt = int(raw) if raw else None
            except ValueError:
                amt = None
            # 매출액
            if result["revenue"] is None and any(
                k in acct for k in ("매출액", "수익(매출액)", "영업수익")
            ):
                result["revenue"] = amt
            # 자산총계
            if result["total_assets"] is None and any(
                k in acct for k in ("자산총계", "자산 총계", "자산합계")
            ):
                result["total_assets"] = amt

        return result

    def get_major_shareholders(
        self, corp_code: str, bsns_year: str | None = None,
    ) -> list[dict]:
        """majorstock — 최대주주 및 특수관계인 현황 조회.
        반환: [{"nm": str, "relate": str, "ownership_pct": str}, ...]

        구분 원칙 (실패 ≠ 자료 없음 — 특수관계인 판단은 세무상 중요):
          - 네트워크·HTTP·파싱 오류 → 예외를 그대로 던진다 (호출부가 '조회 실패' 안내)
          - DART status '013'(조회된 데이터 없음) → 빈 리스트 (공시 없음 — 비상장 등)
          - 그 외 status 오류 (키 오류 '010'/'011', 한도 초과 '020' 등)
            → DartApiError (자료 없음으로 오해하지 않도록)
        """
        year = bsns_year or str(date.today().year - 1)
        params = {
            "crtfc_key": self.api_key,
            "corp_code": corp_code,
            "bsns_year": year,
            "reprt_code": "11011",
        }
        resp = self.session.get(
            f"{DART_URL}/majorstock.json", params=params, timeout=30
        )
        resp.raise_for_status()
        data = resp.json()

        status = data.get("status", "")
        if status == "013":          # 조회된 데이터가 없습니다 — 정상 (공시 없음)
            return []
        if status != "000":
            raise DartApiError(
                f"DART majorstock 오류 status={status}: {data.get('message', '')}"
            )

        return [
            {
                "nm":            item.get("nm", "").strip(),
                "relate":        item.get("relate", "").strip(),
                "ownership_pct": item.get("trmend_posesn_stock_qota_rt", "").strip(),
            }
            for item in data.get("list", [])
            if item.get("nm", "").strip()
        ]

    # ── 법인 기본정보 ─────────────────────────────────────────────────────────

    def get_company_info(self, corp_code: str) -> CompanyBasicInfo | None:
        """corp_code로 DART 법인 기본정보 조회."""
        params = {"crtfc_key": self.api_key, "corp_code": corp_code}
        resp = self.session.get(f"{DART_URL}/company.json", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "000":
            return None
        return CompanyBasicInfo(
            corp_code=data.get("corp_code", ""),
            corp_name=data.get("corp_name", ""),
            stock_code=data.get("stock_code", ""),
            corp_cls=data.get("corp_cls", ""),
            jurir_no=data.get("jurir_no", ""),
            bizr_no=data.get("bizr_no", ""),
            adres=data.get("adres", ""),
            hm_url=data.get("hm_url", ""),
            ir_url=data.get("ir_url", ""),
            phn_no=data.get("phn_no", ""),
            est_dt=data.get("est_dt", ""),
            acc_mt=data.get("acc_mt", ""),
            ceo_nm=data.get("ceo_nm", ""),
            industry_code=data.get("induty_code", ""),
        )
