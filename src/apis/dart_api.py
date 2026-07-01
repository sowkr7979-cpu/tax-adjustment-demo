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
# DART(전자공시) 문서 뷰어·기업개황 바로가기 — Open API가 아닌 공시 화면 URL
DART_DOC_VIEWER = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
DART_CORP_POPUP = "https://dart.fss.or.kr/dsae001/selectPopup.do?selectKey={corp_code}"


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
        """hyslrSttus(최대주주 현황 — 정기보고서 주요정보) 조회.
        반환: [{"nm": str, "relate": str, "ownership_pct": str(기말지분율)}, ...]

        ⚠ 엔드포인트 주의: 'majorstock'(대량보유 5% 상황보고)은 nm/relate/지분율 필드가 없어
          빈 목록이 된다(실데이터 검증 완료). 최대주주·특수관계인 명단+지분율은 'hyslrSttus'다.
          단, hyslrSttus는 정기보고서(사업보고서 등) 제출 회사만 — 비상장 미제출 법인은 자료 없음.
          (감사보고서 '특수관계자 거래' 주석은 Open API 구조화 제공 없음 — 주주명부·감사보고서 수기 확인.)

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
            "reprt_code": "11011",   # 사업보고서
        }
        resp = self.session.get(
            f"{DART_URL}/hyslrSttus.json", params=params, timeout=30
        )
        resp.raise_for_status()
        data = resp.json()

        status = data.get("status", "")
        if status == "013":          # 조회된 데이터가 없습니다 — 정상 (공시 없음)
            return []
        if status != "000":
            raise DartApiError(
                f"DART hyslrSttus 오류 status={status}: {data.get('message', '')}"
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

    # ── 감사보고서 바로가기 (최대주주현황 미제출 비상장 법인용) ────────────────

    def find_audit_report(
        self, corp_code: str, years_back: int = 6,
    ) -> dict | None:
        """list.json — 최신 감사보고서(또는 정기보고서) 1건을 찾아 문서 바로가기 정보 반환.

        hyslrSttus(최대주주현황)가 없는 비상장 법인의 특수관계인은 감사보고서의
        「주주현황」·「특수관계자 거래」 주석에서 확인해야 한다. Open API는 그 주석을
        구조화 제공하지 않으므로, 사용자가 원문 문서로 바로 이동하도록 rcept_no를 찾는다.

        우선순위: 외부감사관련(F, 감사보고서·연결감사보고서) → 정기공시(A, 사업보고서 등).
        외부감사 비대상으로 공시가 전혀 없으면 None.

        반환: {"rcept_no","report_nm","rcept_dt","url"} | None
        실패(네트워크·키 오류 등)는 예외를 그대로 던진다 — '자료 없음'(None)과 구분.
        """
        today = date.today()
        try:
            bgn_dt = today.replace(year=today.year - years_back)
        except ValueError:                       # 2/29 등
            bgn_dt = today - timedelta(days=365 * years_back)
        base = {
            "crtfc_key": self.api_key,
            "corp_code": corp_code,
            "bgn_de": bgn_dt.strftime("%Y%m%d"),
            "end_de": today.strftime("%Y%m%d"),
            "page_count": "100",
            "sort": "date",
            "sort_mth": "desc",
        }

        def _rank(item: dict) -> int:
            nm = item.get("report_nm", "")
            if "감사보고서" in nm and "연결" not in nm:
                return 0                          # 단독 감사보고서 우선
            if "감사보고서" in nm:
                return 1                          # 연결감사보고서
            return 2                              # 그 외(사업보고서 등)

        for pblntf_ty in ("F", "A"):              # F: 외부감사관련, A: 정기공시
            params = dict(base, pblntf_ty=pblntf_ty)
            resp = self.session.get(
                f"{DART_URL}/list.json", params=params, timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status", "")
            if status == "013":                   # 해당 유형 공시 없음 — 다음 유형 시도
                continue
            if status != "000":
                raise DartApiError(
                    f"DART list 오류 status={status}: {data.get('message', '')}"
                )
            items = [it for it in data.get("list", []) if it.get("rcept_no", "").strip()]
            if not items:
                continue
            # 이미 최신순 — 같은 접수일이면 단독 감사보고서를 우선
            items.sort(key=lambda it: (it.get("rcept_dt", ""), -_rank(it)), reverse=True)
            top = items[0]
            rcept_no = top.get("rcept_no", "").strip()
            return {
                "rcept_no":  rcept_no,
                "report_nm": top.get("report_nm", "").strip(),
                "rcept_dt":  top.get("rcept_dt", "").strip(),
                "url":       DART_DOC_VIEWER.format(rcept_no=rcept_no),
            }
        return None

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
