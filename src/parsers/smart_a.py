"""더존 Smart A Excel 내보내기 파싱 (7종)."""
from __future__ import annotations
import re
import warnings
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from src.parsers.normalizer import (
    read_any_table, parse_amount, is_total_row, expand_keywords,
)
from src.utils.models import FixedAsset, JournalLine


# ── 공통 유틸 ──────────────────────────────────────────────────────────────────

# 최근 read 진단 메타 {파일 경로 문자열: meta dict} — 로더가 UI 진단 리포트용으로 수거
_READ_META: dict[str, dict] = {}


def _read_excel(path: str | Path, sheet: str | int = 0) -> pd.DataFrame:
    """표준화 파이프라인(normalizer.read_any_table) 경유 읽기.

    포맷 스니핑(HTML형 .xls 포함)·인코딩 자동 시도·빈 행 제거·헤더 행 탐지를
    거치고, 감사추적용 __sheet__/__row__ 컬럼과 진단 메타를 남긴다.
    """
    df, meta = read_any_table(path, sheet=sheet)
    _READ_META[str(path)] = meta
    return df


# 회계 프로그램별 컬럼명 별칭 — Smart A·WEHAGO 등 버전·설정마다 다를 수 있어
# 우선순위 순으로 나열. (WEHAGO는 계정코드·거래처코드가 둘 다 'Code'로 내보내져
# pandas가 두 번째를 'Code.1'로 바꾼다)
_COL_ALIASES: dict[str, list[str]] = {
    "날짜":      ["날짜", "일자", "전표일자", "거래일자"],
    "전표번호":   ["전표번호", "전표No", "전표no"],
    "계정코드":   ["계정코드", "코드", "Code", "CODE", "code"],
    "계정명":     ["계정명", "계정과목", "계정과목명"],
    "적요":       ["적요", "비고", "내용"],
    "거래처코드":  ["거래처코드", "코드.1", "Code.1", "CODE.1", "code.1"],
    "거래처명":   ["거래처명", "거래처", "거래처명칭"],
    "차변":       ["차변", "차 변"],
    "대변":       ["대변", "대 변"],
    "증빙구분":   ["증빙구분", "증빙유형"],
    "증빙번호":   ["증빙번호"],
    "카드번호":   ["카드번호", "신용카드"],
    "차량번호":   ["차량번호", "현장"],
    "프로젝트":   ["프로젝트"],
}


def _col_get(row: "pd.Series", key: str) -> str:
    """컬럼 별칭 목록에서 처음 매칭되는 값을 반환한다."""
    for alias in _COL_ALIASES.get(key, [key]):
        v = row.get(alias)
        if v is not None:
            return str(v)
    return ""


def _to_int(val: str) -> int:
    """문자열 → 정수 변환. 쉼표·float 표기·(1,234)·△·▲ 음수 표기 모두 허용."""
    return parse_amount(val)


def _to_date(val: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            return datetime.strptime(val.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _is_report_statement(df: pd.DataFrame) -> bool:
    """더존 보고서형 재무제표인지 판정한다."""
    if {"계정코드", "계정명"} & {str(c).strip() for c in df.columns}:
        return False
    # 컬럼명의 공백을 제거해 더존의 공백 삽입 패턴(재 무 상 태 표, 손   익   계   산   서)을 모두 커버
    col_merged = "".join(str(c).replace(" ", "") for c in df.columns)
    if any(k in col_merged for k in (
        "재무상태표", "손익계산서", "원가명세서", "제조원가명세서",
        "계정별원장", "고정자산명세서", "고정자산대장",
    )):
        return True
    # WEHAGO 과목별 양식: 헤더가 '과 목 / 제 N (당)기 [...] / 제 N (전)기 [...]'
    if "(당)기" in col_merged or "(전)기" in col_merged:
        return True
    if "과목" in col_merged and "코드" not in col_merged and "code" not in col_merged.lower():
        return True
    # 셀 값에서도 체크 (기존 방식 유지)
    sample = " ".join(
        str(v)
        for v in df.head(20).to_numpy().ravel().tolist()
        if str(v).strip()
    )
    return any(
        key in sample
        for key in ("재 무 상 태 표", "손 익 계 산 서", "원 가 명 세 서", "과      목", "과 목")
    )


def _normalize_report_statement(df: pd.DataFrame, kind: str) -> pd.DataFrame:
    """
    더존 보고서형 재무제표를 내부 표준 컬럼으로 변환한다.

    보고서형 파일은 계정코드가 없는 "과목 / 당기 / 전기" 양식이다.
    이 경우 계정코드는 비워두고 계정명과 금액을 보존한다.
    """
    meta_cols = {"__sheet__", "__row__"}
    data_cols = [c for c in df.columns if c not in meta_cols]
    rows: list[dict] = []

    # 헤더에서 당기·전기 컬럼 그룹 식별 — WEHAGO '제 N (당)기 / Unnamed' 2단 금액 대응
    # (당기 그룹이 식별되면 전기 금액을 당기로 오인하지 않는다)
    cur_cols: list = []
    prev_cols: list = []
    _group = ""
    for c in data_cols[1:]:
        cs = str(c).replace(" ", "")
        if "(당)기" in cs or cs.startswith("당기"):
            _group = "cur"
        elif "(전)기" in cs or cs.startswith("전기"):
            _group = "prev"
        if _group == "cur":
            cur_cols.append(c)
        elif _group == "prev":
            prev_cols.append(c)

    # 제목 행: 포함 매칭 / 헤더 행("과목", "금액" 등): 공백 제거 후 정확 매칭
    # ("당기순이익", "당기 상품 매입액" 같은 실데이터 행이 잘려나가지 않도록)
    title_words = (
        "재 무 상 태 표", "손 익 계 산 서", "원 가 명 세 서",
        "제 조 원 가 명 세 서", "계 정 별 원 장", "고 정 자 산",
        "회사명", "단위", "현재",
    )
    header_exact = {"과목", "당기", "전기", "증감", "금액"}

    for _, row in df.iterrows():
        values = [str(row.get(c, "")).strip() for c in data_cols]
        nonempty = [v for v in values if v]
        if not nonempty:
            continue

        name = re.sub(r"\s+", " ", nonempty[0]).strip()
        if any(word in name for word in title_words):
            continue
        if name.replace(" ", "") in header_exact:
            continue
        if re.fullmatch(r"[\d,.\-()]+", name):
            continue  # 과목 칸이 비고 금액만 있는 행

        def _first_amount(cols: list) -> int:
            for c in cols:
                a = _to_int(str(row.get(c, "")))
                if a != 0:
                    return a
            return 0

        if cur_cols:
            cur_amt = _first_amount(cur_cols)
            prev_amt = _first_amount(prev_cols)
        else:
            # 헤더 정보 없음 — 기존 위치 기반 (첫 금액=당기, 둘째=전기)
            amounts = [a for a in (_to_int(v) for v in values[1:]) if a != 0]
            cur_amt = amounts[0] if amounts else 0
            prev_amt = amounts[1] if len(amounts) > 1 else 0

        if cur_amt == 0 and prev_amt == 0:
            continue

        out = {
            "계정코드": "",
            "계정명": name,
            "합계행": is_total_row(name),   # 합계·소계행 태그 (집계 시 이중계산 방지용)
            "__sheet__": row.get("__sheet__", ""),
            "__row__": row.get("__row__", 0),
        }
        if kind == "balance":
            out["기말잔액"] = cur_amt
            out["기초잔액"] = prev_amt
        else:
            out["당기금액"] = cur_amt
            out["전기금액"] = prev_amt   # 전년 대비 증감분석용
        rows.append(out)

    return pd.DataFrame(rows)


def _re_header(df: pd.DataFrame, keywords: list[str], min_hits: int = 2) -> pd.DataFrame:
    """보고서형 DataFrame에서 실제 헤더 행을 찾아 컬럼으로 설정한다.

    keywords 중 min_hits 개 이상이 한 행에 있으면 그 행을 새 헤더로 사용한다.
    """
    meta = {"__sheet__", "__row__"}
    data_cols = [c for c in df.columns if c not in meta]

    for i, (_, row) in enumerate(df.iterrows()):
        vals = [str(row.get(c, "")).strip() for c in data_cols]
        if sum(1 for kw in keywords if kw in vals) >= min_hits:
            # vals를 새 컬럼명으로 사용, 그 다음 행부터 데이터
            new_df = df.iloc[i + 1:].copy().reset_index(drop=True)
            new_col_names = vals + [c for c in df.columns if c in meta]
            # 길이 맞춤
            while len(new_col_names) < len(df.columns):
                new_col_names.append(f"Unnamed_{len(new_col_names)}")
            new_df.columns = new_col_names[:len(df.columns)]
            # __row__ 재계산 (헤더 행 이후부터)
            if "__row__" in new_df.columns:
                new_df["__row__"] = range(i + 3, len(new_df) + i + 3)
            return new_df
    return df


# ── 재무상태표 ─────────────────────────────────────────────────────────────────

def parse_balance_sheet(path: str | Path) -> pd.DataFrame:
    """재무상태표 → {계정코드, 계정명, 기초잔액, 기말잔액}"""
    df = _read_excel(path)
    if _is_report_statement(df):
        df = _normalize_report_statement(df, "balance")
    required = {"계정코드", "계정명"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"재무상태표에 필수 컬럼 누락: {missing}")
    for col in ("기초잔액", "기말잔액"):
        if col in df.columns:
            df[col] = df[col].apply(_to_int)
    return df


# ── 손익계산서 ─────────────────────────────────────────────────────────────────

def parse_income_statement(path: str | Path) -> pd.DataFrame:
    """손익계산서 → {계정코드, 계정명, 당기금액}"""
    df = _read_excel(path)
    if _is_report_statement(df):
        df = _normalize_report_statement(df, "income")
    if "당기금액" in df.columns:
        df["당기금액"] = df["당기금액"].apply(_to_int)
    return df


# ── 원가명세서 ─────────────────────────────────────────────────────────────────

def parse_cost_statement(path: str | Path) -> pd.DataFrame:
    """원가명세서 → {계정코드, 계정명, 당기금액}"""
    return parse_income_statement(path)


# ── 이익잉여금처분계산서 ───────────────────────────────────────────────────────

def parse_retained_earnings(path: str | Path) -> pd.DataFrame:
    df = _read_excel(path)
    for col in ("금액",):
        if col in df.columns:
            df[col] = df[col].apply(_to_int)
    return df


# ── 고정자산대장 ───────────────────────────────────────────────────────────────

_FIXED_ASSET_COLS = {
    "계정코드": "account_code",
    "자산코드": "asset_code",
    "자산명": "asset_name",
    "취득일": "acquired_date",
    "경비": "category",
    "전기말장부가액": "book_value_start",
    "전기말상각누계": "accumulated_depr_start",
    "전기말부인누계": "denied_depr_start",
    "전기말의제누계": "deemed_depr_start",
    "신규취득": "new_acquisition",
    "당기감소": "disposal",
    "연수": "useful_life",
    "상각률": "depr_rate",
    "월수": "months",
    "상각법": "method",
    "세무상당기상각비범위액": "tax_depr_limit",
    "회사계상상각비": "company_depr",
    "양도폐기일": "disposal_date",
}


_FA_HEADER_KEYWORDS = ["자산코드", "자산명", "취득일", "취득일자", "상각률", "상각율"]
_FA_COL_ALIASES: dict[str, list[str]] = {
    "자산코드":       ["자산코드", "자산번호"],
    "자산명":         ["자산명", "자산명칭"],
    "계정코드":       ["계정코드", "코드"],
    "취득일":         ["취득일", "취득일자"],
    "경비":           ["경비", "계정과목명", "계정과목"],
    # 더존 Smart A 실제 컬럼: 전기이월, 기초장부가액 등
    "전기말장부가액":  ["전기말장부가액", "기초장부가액", "전기이월", "장부가액"],
    "전기말상각누계":  ["전기말상각누계", "전기말상각누계액", "기초상각누계", "전기말충당금누계", "상각누계"],
    "전기말부인누계":  ["전기말부인누계", "기초부인누계"],
    "전기말의제누계":  ["전기말의제누계", "기초의제누계"],
    "신규취득":        ["신규취득", "당기취득", "당기증가", "당기증감"],
    "당기감소":        ["당기감소", "처분"],
    # 더존: 연수 → 년수, 상각률 → 상각율 표기 변형 모두 지원
    "연수":            ["연수", "년수", "내용연수"],
    "상각률":          ["상각률", "상각율"],
    "월수":            ["월수", "당기월수"],
    # 더존: 상각법이 '비고' 컬럼에 있음 (정액법/정률법)
    "상각법":          ["상각법", "상각방법", "비고"],
    "세무상당기상각비범위액": ["세무상당기상각비범위액", "세무상한도"],
    "회사계상상각비":   ["회사계상상각비", "당기감가상각비", "당기상각비"],
    "양도폐기일":       ["양도폐기일", "처분일"],
    # 더존 '감가상각비명세서' 양식: 기초가액 = 취득가액 (장부가액 아님)
    "취득가액":        ["취득가액", "기초가액"],
}

# 소계·합계 행 — '[소계] 차량운반구' 형태에서 계정과목명을 추출해
# 직전 자산 그룹에 역으로 부여한다 (개별 자산 행에 계정 정보가 없는 양식 대응)
# 주의: '계측기' 같은 자산명 오인 방지 — 소계·합계·총계 단어 또는 단독 '계'만 매칭
_FA_SUBTOTAL_RE = re.compile(r"^\[?\s*(소\s*계|합\s*계|총\s*계)\s*\]?\s*(.*)$")


def _infer_method(depr_rate: float, useful_life: int, raw: str) -> str:
    """상각법 추론: 명시값 우선, 없으면 상각률 ≈ 1/내용연수 → 정액법, 그 외 정률법."""
    if any(k in raw for k in ("정액", "정률", "배율", "생산량")):
        return raw
    if depr_rate > 0 and useful_life > 0:
        return "정액법" if abs(depr_rate - 1.0 / useful_life) < 0.005 else "정률법"
    if useful_life > 0 and depr_rate == 0:
        return "정액법"
    return "정률법"


def _fa_get(row: "pd.Series", key: str) -> str:
    for alias in _FA_COL_ALIASES.get(key, [key]):
        v = row.get(alias)
        if v is not None:
            return str(v)
    return ""


def parse_fixed_assets(path: str | Path) -> list[FixedAsset]:
    df = _read_excel(path)
    # 더존 보고서형: 실제 헤더 행을 찾아 재구성
    if _is_report_statement(df):
        df = _re_header(df, _FA_HEADER_KEYWORDS, min_hits=2)
    results: list[FixedAsset] = []
    pending: list[FixedAsset] = []   # 직전 소계 이후의 자산 (소계 행에서 계정명 역부여)
    skipped = 0
    for i, (_, row) in enumerate(df.iterrows()):
        try:
            name = _fa_get(row, "자산명").strip()
            if not name or name == "계":
                continue
            # '[소계] 차량운반구' / '소계' / '[합계]' — 그룹 경계 행
            m = _FA_SUBTOTAL_RE.match(name)
            if m:
                group_name = m.group(2).strip()
                if group_name:
                    for a in pending:
                        if not a.category:
                            a.category = group_name
                pending = []
                continue

            depr_rate_raw = _fa_get(row, "상각률").replace(",", "") or "0"
            try:
                depr_rate = float(depr_rate_raw)
            except ValueError:
                depr_rate = 0.0

            # 더존 '감가상각비명세서' 양식: 기초가액 = 취득가액 → 장부가액 = 취득가액 − 상각누계
            accum = _to_int(_fa_get(row, "전기말상각누계") or "0")
            book = _to_int(_fa_get(row, "전기말장부가액") or "0")
            if book == 0:
                cost = _to_int(_fa_get(row, "취득가액") or "0")
                if cost > 0:
                    book = max(0, cost - accum)

            useful_life = _to_int(_fa_get(row, "연수") or "5")
            asset = FixedAsset(
                asset_code=_fa_get(row, "자산코드") or f"FA{i + 1:04d}",
                asset_name=name,
                account_code=_fa_get(row, "계정코드"),
                acquired_date=_to_date(_fa_get(row, "취득일")) or date(2000, 1, 1),
                category=_fa_get(row, "경비"),
                book_value_start=book,
                accumulated_depr_start=accum,
                denied_depr_start=_to_int(_fa_get(row, "전기말부인누계") or "0"),
                deemed_depr_start=_to_int(_fa_get(row, "전기말의제누계") or "0"),
                new_acquisition=_to_int(_fa_get(row, "신규취득") or "0"),
                disposal=_to_int(_fa_get(row, "당기감소") or "0"),
                useful_life=useful_life,
                depr_rate=depr_rate,
                months=_to_int(_fa_get(row, "월수") or "12"),
                method=_infer_method(depr_rate, useful_life, _fa_get(row, "상각법")),
                tax_depr_limit=_to_int(_fa_get(row, "세무상당기상각비범위액") or "0"),
                company_depr=_to_int(_fa_get(row, "회사계상상각비") or "0"),
                disposal_date=_to_date(_fa_get(row, "양도폐기일")),
            )
            results.append(asset)
            pending.append(asset)
        except Exception as e:
            skipped += 1
            warnings.warn(
                f"고정자산대장 행 {i + 2} 건너뜀 ({_fa_get(row, '자산명') or '?'}): {e}",
                stacklevel=2,
            )
    if skipped:
        warnings.warn(
            f"고정자산대장: {len(results)}개 처리, {skipped}개 행 파싱 실패",
            stacklevel=2,
        )
    return results


# ── 분개장 ─────────────────────────────────────────────────────────────────────

def parse_journal(path: str | Path, source_file: str = "") -> list[JournalLine]:
    """분개장 Excel → JournalLine 리스트. 더존 Smart A 컬럼 별칭(_COL_ALIASES) 지원."""
    df = _read_excel(path)
    source = source_file or str(path)
    results = []
    skipped = 0
    for i, (_, row) in enumerate(df.iterrows()):
        try:
            dt = _to_date(_col_get(row, "날짜"))
            if dt is None:
                continue
            line = JournalLine(
                journal_id=_col_get(row, "전표번호"),
                line_no=0,
                date=dt,
                account_code=_col_get(row, "계정코드"),
                account_name=_col_get(row, "계정명"),
                description=_col_get(row, "적요"),
                counterparty_code=_col_get(row, "거래처코드"),
                counterparty_name=_col_get(row, "거래처명"),
                debit=_to_int(_col_get(row, "차변") or "0"),
                credit=_to_int(_col_get(row, "대변") or "0"),
                evidence_type=_col_get(row, "증빙구분"),
                evidence_no=_col_get(row, "증빙번호"),
                card_no=_col_get(row, "카드번호"),
                vehicle_no=_col_get(row, "차량번호"),
                project=_col_get(row, "프로젝트"),
                source_file=source,
                source_sheet=str(row.get("__sheet__", "")),
                source_row=_to_int(str(row.get("__row__", "0"))),
            )
            results.append(line)
        except Exception as e:
            skipped += 1
            warnings.warn(
                f"분개장 행 {i + 2} 건너뜀 ({_col_get(row, '전표번호') or '?'}): {e}",
                stacklevel=2,
            )
    if skipped:
        warnings.warn(
            f"분개장: {len(results)}개 처리, {skipped}개 행 파싱 실패",
            stacklevel=2,
        )
    return results


# ── 계정별원장 ─────────────────────────────────────────────────────────────────

def parse_ledger(path: str | Path) -> pd.DataFrame:
    """계정별원장 → DataFrame (분개 분석 보조용)."""
    df = _read_excel(path)
    for col in ("차변", "대변", "잔액"):
        if col in df.columns:
            df[col] = df[col].apply(_to_int)
    return df


# ── 통합 로더 ─────────────────────────────────────────────────────────────────

class SmartALoader:
    """Smart A Excel 파일 세트 로드 및 검증."""

    def __init__(self) -> None:
        self.balance_sheet: pd.DataFrame | None = None
        self.income_statement: pd.DataFrame | None = None
        self.cost_statement: pd.DataFrame | None = None
        self.retained_earnings: pd.DataFrame | None = None
        self.fixed_assets: list[FixedAsset] = []
        self.journals: list[JournalLine] = []
        self.ledger: pd.DataFrame | None = None
        self.account_statement: pd.DataFrame | None = None  # 계정별 잔액명세서
        # 행 수준 파싱 경고 {파일유형: [경고메시지, ...]}
        self.parse_warnings: dict[str, list[str]] = {}
        # 파일별 표준화 진단 메타 {파일유형: {format, encoding, header_row, ...}}
        self.file_meta: dict[str, dict] = {}

    def load(self, paths: dict[str, str]) -> dict[str, str]:
        """paths: {"재무상태표": "...", ...}
        파일별로 독립 파싱. 반환값: {파일명: 오류메시지} (성공 파일은 포함 안 됨)."""
        _loaders = {
            "재무상태표":          ("balance_sheet",    parse_balance_sheet),
            "손익계산서":          ("income_statement", parse_income_statement),
            "원가명세서":          ("cost_statement",   parse_cost_statement),
            "이익잉여금처분계산서": ("retained_earnings", parse_retained_earnings),
            "고정자산대장":        ("fixed_assets",     parse_fixed_assets),
            "분개장":              ("journals",         parse_journal),
            "계정별원장":          ("ledger",           parse_ledger),
            # 잔액 구조가 재무상태표와 동일 (계정코드/계정명/잔액) — 동일 파서 재사용
            "계정별명세서":        ("account_statement", parse_balance_sheet),
        }
        # 빈 초기값 — 파싱 실패 시 이전(다른 회사) 데이터가 남지 않도록 반드시 초기화
        _empty: dict[str, object] = {
            "balance_sheet": None, "income_statement": None,
            "cost_statement": None, "retained_earnings": None,
            "fixed_assets": [], "journals": [], "ledger": None,
            "account_statement": None,
        }
        errors: dict[str, str] = {}
        self.parse_warnings = {}
        self.file_meta = {}
        for name, path in paths.items():
            if name in _loaders and path:
                attr, fn = _loaders[name]
                try:
                    with warnings.catch_warnings(record=True) as caught:
                        warnings.simplefilter("always")
                        setattr(self, attr, fn(path))
                    if caught:
                        self.parse_warnings[name] = [str(w.message) for w in caught]
                except Exception as e:
                    errors[name] = str(e)
                    # 실패한 파일유형의 기존 데이터를 비운다 — 이전 업로드 잔존 방지
                    setattr(self, attr, _empty[attr])
                # 표준화 진단 메타 수거 (성공·실패 무관 — 어디까지 읽었는지 표시)
                if str(path) in _READ_META:
                    self.file_meta[name] = _READ_META.pop(str(path))

        # 보고서형 재무제표(계정코드 없음)에 분개장의 계정명→코드 매핑 적용
        # — Smart A·WEHAGO 등 프로그램이 달라도 분개장 코드 체계로 통일
        self._backfill_codes_from_journals()
        return errors

    def _backfill_codes_from_journals(self) -> None:
        """분개장에서 계정명→계정코드 매핑을 학습해 재무제표의 빈 계정코드를 채운다."""
        if not self.journals:
            return
        from collections import Counter

        def _norm(name: str) -> str:
            # 보고서형 과목명 정리: 로마숫자·번호 접두어·공백 제거
            n = re.sub(r"^[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ]+\s*\.?\s*", "", str(name))
            n = re.sub(r"^\(\d+\)\s*", "", n)
            n = re.sub(r"^\d+\.\s*", "", n)
            return n.replace(" ", "").strip()

        votes: dict[str, Counter] = {}
        for j in self.journals:
            code = j.account_code.strip()
            nm = _norm(j.account_name)
            if code and nm:
                votes.setdefault(nm, Counter())[code] += 1
        if not votes:
            return  # 분개장에도 코드가 없음 — 역보충 불가
        code_map = {nm: c.most_common(1)[0][0] for nm, c in votes.items()}

        for attr in ("income_statement", "balance_sheet", "cost_statement"):
            df = getattr(self, attr)
            if df is None or df.empty:
                continue
            if "계정코드" not in df.columns or "계정명" not in df.columns:
                continue
            mask = df["계정코드"].astype(str).str.strip() == ""
            if not mask.any():
                continue
            df.loc[mask, "계정코드"] = (
                df.loc[mask, "계정명"].astype(str).map(lambda n: code_map.get(_norm(n), ""))
            )

    def validate(self) -> list[str]:
        """필수 항목 존재 여부·대차 균형 검증. 경고 메시지 리스트 반환."""
        warnings: list[str] = []
        if self.balance_sheet is None:
            warnings.append("재무상태표 미업로드")
        if self.income_statement is None:
            warnings.append("손익계산서 미업로드")
        if not self.journals:
            warnings.append("분개장 미업로드 — LLM 분석 불가")
        if not self.fixed_assets:
            warnings.append("고정자산대장 미업로드 — 감가상각 자동계산 불가")
        return warnings

    def get_account_total(self, account_code_prefix: str) -> int:
        """손익계산서에서 특정 계정 코드 접두어로 합계 조회."""
        if self.income_statement is None:
            return 0
        mask = self.income_statement.get("계정코드", pd.Series(dtype=str)).str.startswith(
            account_code_prefix
        )
        return int(self.income_statement.loc[mask, "당기금액"].sum())

    def get_amount_by_name(self, keywords: tuple[str, ...]) -> int:
        """손익계산서에서 계정명 키워드로 당기금액 조회.

        보고서형 재무제표(계정코드 없음) 폴백용. 첫 매칭 행의 금액 반환.
        계정명 동의어(접대비↔기업업무추진비 등)까지 확장해 검색한다.
        """
        if self.income_statement is None or self.income_statement.empty:
            return 0
        names = self.income_statement.get("계정명")
        if names is None:
            return 0
        kws = expand_keywords(keywords)
        mask = names.astype(str).str.replace(" ", "").apply(
            lambda n: any(kw in n for kw in kws)
        )
        if not mask.any():
            return 0
        return int(self.income_statement.loc[mask, "당기금액"].iloc[0])

    def get_net_income(self) -> int:
        """당기순이익 조회 — 손익계산서의 '당기순이익/당기순손실' 행만 신뢰.

        찾지 못하면 0을 반환한다. 계정코드 추정(4번대 − 8번대)은 더존 코드체계에서
        매출원가가 4번대에 들어가 틀릴 수 있으므로 사용하지 않는다 — 호출부(5단계)가
        0이면 계산을 중단하고 수기 입력을 요구한다 (세액 계산의 출발값 보호).
        """
        profit = self.get_amount_by_name(("당기순이익",))
        if profit:
            return profit
        loss = self.get_amount_by_name(("당기순손실",))
        if loss:
            return -loss
        return 0
