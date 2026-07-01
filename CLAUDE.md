# 법인세 세무조정 자동화 (Streamlit 로컬 앱)

KICPA의 법인세 세무조정 용역 보조도구. 더존 Smart A·WEHAGO 재무자료를 파싱해
규칙 엔진으로 세무조정을 자동 계산하고, 로컬 LLM이 검토 후보를 보조한다.
**AI가 세무판단을 확정하지 않는다** — 초안·근거·검토 포인트 생성이 목적.

## 기술 스택
- Python 3.14 + Streamlit (로컬 실행, SaaS 아님 — ADR-001)
- pandas / openpyxl / xlrd / lxml (HTML형 .xls 파싱)
- Ollama 로컬 LLM (현재 gemma4) — 검토 보조 전용

## CRITICAL 규칙 (위반 금지)
- **모든 세무조정은 국가법령정보(law.go.kr) 기반.** 조정 항목마다
  `src/rules/legal_basis.py`의 법령 매핑(법령ID·조문번호) 등록 필수.
  법령에 없는 임의 규칙(예: 운행기록부 미작성 50% 강제) 금지.
  산식 구현·수정 전 law.go.kr API로 원문 확인 (efYd = 사업연도 종료일).
  법령ID: 법인세법 001563 / 시행령 003608 / 시행규칙 007229 / 조특법 001584 / 조특령 004920.
- **외부 LLM API (OpenAI·Claude API 등) 사용 금지.** 모든 분석은 로컬 Ollama.
- **네트워크는 국가법령정보센터·DART API만 허용.**
- **파일 삭제는 사용자 permission을 받을 것.**
- 고객자료(*.xls/xlsx/hwp)·`.env`는 git 제외 유지. 폴더 압축 공유 전 .env 제거.
- 세무조정 금액 확정·한도·세액 계산은 규칙 엔진만 — LLM에 맡기지 않는다 (ADR-002).
- 업로드 임시파일·출력 임시파일은 사용 직후 삭제.
- 적수(積數) 계산은 B/S 기초잔액 + 분개장 당기 증감의 일별 계산 (`src/rules/jeoksu.py`).
- 인정이자는 거래상대방별 계산 — 상대방 간 통산 금지 (영§88③ 기준 적용).

## 구조
```
src/app.py        라우팅·사이드바만 (~120줄)
src/views/        1~6단계 화면 모듈 (basic_info/upload/manual/llm/calc/output + common)
src/parsers/      normalizer(표준화 파이프라인) + smart_a(더존·WEHAGO 파서)
src/rules/        규칙 엔진 (산식·적수·legal_basis·coverage[+검토필요 근거법령]·aggregator·consulting·vehicle_match)
src/rag/          국가법령 외 — 국세청 참고파일 키워드 검색 (reference_retriever, 벡터DB 없음, 컨설팅·PDF 보조)
src/llm/          Ollama 클라이언트·분석기 (Level 1 RAG — 조문 프롬프트 첨부) + consultant(컨설팅 문장화)
src/apis/         law.go.kr·DART 클라이언트 (실패 ≠ 자료 없음 구분 / 최대주주는 hyslrSttus)
src/forms/        검토패키지 PDF·감사추적 Excel·별지 추천 / src/project/ .taxproj
```

## 명령어
```
python -m pytest tests          # 전체 테스트 (규칙·파서 + 페이지 렌더 스모크)
세무조정앱_실행.bat              # 앱 실행 → http://localhost:8501
```
앱 재시작(개발 중): 8501 포트 프로세스 종료 후
`C:\Users\hwshin\AppData\Local\Temp\run_streamlit.bat` 실행 (한글 경로 우회).

## 개발 프로세스
- 산식 변경 시: law.go.kr 원문 확인 → 구현 → 단위 테스트 추가 → 실데이터 회귀
  (티엘 WEHAGO: 분개 49,060건 — 핵심 수치 일치 확인) → 설계 md 갱신.
- UI 변경 시 페이지 렌더 스모크(`tests/test_app_pages.py`)가 통과해야 한다.
- 계산 항목 추가 시 5단계 계산 내역(산식·사유·분개 드릴다운)과
  별지15호 행, legal_basis 매핑을 함께 추가한다.

## 문서·폴더 구조 (개발 단계별)
- `docs/` — 공식 문서: PRD · ARCHITECTURE · ADR · UI_GUIDE
- `1_기획설계/` — 상세 설계: `법인세_세무조정_자동화_전체설계.md` (마스터),
  `규칙엔진_세무조정계산_설계.md`, `LLM_분개전체분석_설계.md`, `별지서식_금액매핑_설계.md`
- `2_참고자료/` — `원본/`(국세청 PDF·검토서식) + `추출텍스트/`(PDF 추출·법령 검색 중간 산출물)
- `src/` · `tests/` — 구현·검증 (이동 금지 — import 경로·실행 bat이 의존)
