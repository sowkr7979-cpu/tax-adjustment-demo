"""참고자료 키워드 검색기 — 국세청 참고파일(추출텍스트) 청크 검색.

가드레일:
  - 로컬 텍스트만 읽는다(외부 네트워크/LLM API 없음 — CLAUDE.md 네트워크 제한 준수).
  - 계산엔진과 분리 — 컨설팅 토픽 '검토 근거 자료' 보조에만 사용한다.
  - 벡터DB·임베딩 없이 키워드(부분문자열) 검색. 인덱스는 모듈 캐시(읽기 전용).
  - 참고파일이 없거나 깨져도 [] 반환 — 호출부(PDF·컨설팅)가 무너지지 않게 한다.
"""
from __future__ import annotations

import re
from pathlib import Path

# 추출텍스트 폴더 (src/rag/ → 프로젝트 루트 → 2_참고자료/추출텍스트)
_DIR = Path(__file__).resolve().parents[2] / "2_참고자료" / "추출텍스트"

# 색인 대상 파일 → 사용자에게 보일 출처명 (국세청 공식 참고파일)
_CORPUS: dict[str, str] = {
    "sme_pdf.txt": "중소기업 세제·세정지원제도(2026, 국세청)",
    "ceo_pdf.txt": "최고경영자의 현명한 세무관리(2026, 국세청)",
    "ceo_key_pages.txt": "최고경영자의 현명한 세무관리(2026) — 발췌",
    "self_verify_checklist.txt": "자기검증 지원용 검토서식(2026)",
    "self_verify_forms.txt": "자기검증 지원용 검토서식(2026) — 서식",
    "law_changes.txt": "2026 법인세 신고안내 — 세법개정·검토서식",
    "pdf_extracted.txt": "2026 법인세 신고안내(국세청)",
}

# "=== 페이지 12 ===" / "=== PDF페이지 56 ===" 양식 모두 인식
_PAGE_RE = re.compile(r"^===\s*(?:PDF)?페이지\s*(\d+)\s*===\s*$", re.M)
_TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]+")
_WS_RE = re.compile(r"\s+")

_SNIPPET_LEN = 160       # 발췌 표시 길이 (핵심 1~2문장 — 참고자료는 간결히)
_CHUNK_TARGET = 700      # 페이지 마커 없는 파일의 문단 청크 목표 길이
# 문장 경계 (한국어 종결 + 마침표) — 발췌를 어절 중간이 아닌 문장에서 자르기
_SENT_END_RE = re.compile(r"(?:다\.|음\.|요\.|함\.|됨\.|\.)\s")

# PDF 추출 텍스트의 반각·특수 글리프 → 맑은고딕에 있는 문자로 정규화 (PDF 누락 글리프 방지)
_GLYPH_MAP = {"･": "·", "｢": "「", "｣": "」", "‣": "·", "╷": "|",
              "舊": "(舊)", "": "·", "": "·", "": "·"}
_PUA_RE = re.compile(r"[-]")   # 사용자정의영역(깨진 불릿 등) 제거


def _normalize_glyphs(s: str) -> str:
    for k, v in _GLYPH_MAP.items():
        s = s.replace(k, v)
    return _PUA_RE.sub("·", s)

# 모듈 캐시 — {filename: [(chunk_label, text), ...]}
_cache: dict[str, list[tuple[str, str]]] = {}


def _chunk_text(text: str) -> list[tuple[str, str]]:
    """페이지 마커가 있으면 페이지 단위, 없으면 문단 블록(~700자)으로 청킹."""
    marks = list(_PAGE_RE.finditer(text))
    if marks:
        chunks: list[tuple[str, str]] = []
        for i, m in enumerate(marks):
            start = m.end()
            end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            body = text[start:end].strip()
            if body:
                chunks.append((f"p.{m.group(1)}", body))
        return chunks
    # 페이지 마커 없음 — 빈 줄 기준 문단을 ~700자로 묶는다
    blocks: list[str] = []
    buf: list[str] = []
    size = 0
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        buf.append(para)
        size += len(para)
        if size >= _CHUNK_TARGET:
            blocks.append("\n".join(buf))
            buf, size = [], 0
    if buf:
        blocks.append("\n".join(buf))
    return [(f"#{i + 1}", b) for i, b in enumerate(blocks)]


def _load(filename: str) -> list[tuple[str, str]]:
    if filename in _cache:
        return _cache[filename]
    path = _DIR / filename
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        chunks = _chunk_text(text)
    except OSError:
        chunks = []
    _cache[filename] = chunks
    return chunks


def _tokenize(query: str) -> list[str]:
    """2자 이상 한글/영숫자 토큰만 추출(조사·기호 제거)."""
    seen: list[str] = []
    for w in _TOKEN_RE.findall(query or ""):
        if len(w) >= 2 and w not in seen:
            seen.append(w)
    return seen


def _score(text: str, keywords: list[str]) -> tuple[float, int]:
    """청크 점수 = 키워드 빈도(상한) + 포함한 키워드 수 가산점. (점수, 첫 매칭 위치)."""
    score = 0.0
    distinct = 0
    first_pos = -1
    for kw in keywords:
        c = text.count(kw)
        if c:
            distinct += 1
            score += 1.0 + min(c, 5) * 0.2   # 빈도는 상한 — 한 단어 도배 방지
            pos = text.find(kw)
            if first_pos < 0 or pos < first_pos:
                first_pos = pos
    if distinct == 0:
        return 0.0, -1
    return score + distinct * 0.5, first_pos   # 여러 키워드를 덮을수록 가산


def _snippet(text: str, at: int) -> str:
    """첫 매칭 위치를 포함한 핵심 1~2문장 발췌 (~160자, 문장 경계에서 자름).

    원문에서 문장을 잘라 보여줄 뿐 요약·재작성하지 않는다 (RAG 원문 발췌 원칙 — 환각 차단).
    """
    if at < 0:
        at = 0
    # 매칭 위치 앞쪽 문장 시작으로 후퇴 (직전 문장 종결 다음부터)
    head = text[:at]
    _starts = list(_SENT_END_RE.finditer(head))
    start = _starts[-1].end() if _starts else max(0, at - 40)
    body = text[start:]
    # 매칭 이후 문장 경계까지 확장하되 _SNIPPET_LEN 상한
    _ends = list(_SENT_END_RE.finditer(body))
    end = len(body)
    for m in _ends:
        if m.end() >= min(len(body), _SNIPPET_LEN) and (at - start) < m.end():
            end = m.end()
            break
    else:
        end = min(len(body), _SNIPPET_LEN)
    frag = _WS_RE.sub(" ", body[:end].strip())
    frag = _normalize_glyphs(frag)
    if start > 0:
        frag = "… " + frag
    if start + end < len(text):
        frag = frag.rstrip() + " …"
    return frag


def search_references(
    query: str,
    top_k: int = 5,
    keywords: list[str] | None = None,
) -> list[dict]:
    """참고파일에서 query/keywords와 관련된 청크를 점수순 top_k개 반환.

    반환: [{"source": 출처명, "chunk_id": "p.12"|"#3", "text": 발췌, "score": float}]
    매칭 없으면 [] (참고파일 미존재·무관 시 안전).
    """
    kws = keywords if keywords else _tokenize(query)
    if not kws:
        return []
    hits: list[dict] = []
    for filename, label in _CORPUS.items():
        for chunk_id, body in _load(filename):
            sc, pos = _score(body, kws)
            if sc <= 0:
                continue
            hits.append({
                "source": label,
                "chunk_id": chunk_id,
                "text": _snippet(body, pos),
                "score": round(sc, 2),
            })
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits[:top_k]


def enrich_topics_with_references(topics: list, top_k: int = 2) -> list:
    """컨설팅 토픽에 참고파일 발췌(references)를 채운다(보조 자료).

    토픽의 keywords(있으면)로 검색, 없으면 title을 질의로 사용.
    토픽별 try/except — 한 토픽 실패가 전체 PDF/컨설팅을 막지 않게 한다.
    """
    for t in (topics or []):
        try:
            kws = list(getattr(t, "keywords", None) or [])
            snippets = search_references(getattr(t, "title", ""), top_k=top_k,
                                         keywords=kws or None)
            if hasattr(t, "references"):
                t.references = snippets
        except Exception:
            if hasattr(t, "references"):
                t.references = []
    return topics


def format_reference(ref: dict) -> str:
    """참고자료 한 건 → '〔출처명 p.12〕 내용' 표시 문자열 (화면·PDF 공용).

    페이지 마커가 없는 청크(chunk_id='#3')는 페이지 대신 '(발췌)'로 표기.
    """
    cid = str(ref.get("chunk_id", ""))
    loc = cid if cid.startswith("p.") else "(발췌)"
    return f"〔{ref.get('source', '')} {loc}〕 {ref.get('text', '')}"
