# Architecture

## 현재 구조

```text
src/
  app.py              # Streamlit 진입점, 페이지 라우팅, 세션 초기화
  views/              # 1~6단계 화면 모듈
  parsers/            # 더존/WEHAGO 엑셀, HTML형 xls, CSV 파싱
  rules/              # 세무조정 규칙 계산 엔진 (+ consulting 토픽, coverage 근거법령, vehicle_match)
  rag/                # 국세청 참고파일 키워드 검색 (reference_retriever) — 컨설팅·PDF·LLM 보조
  llm/                # Ollama 기반 로컬 LLM 분석 (analyzer) + 컨설팅 문장화 (consultant)
  apis/               # DART, 법령정보 API 클라이언트
  forms/              # 별지 추천, 검토패키지 PDF, 감사추적 Excel 생성
  project/            # .taxproj 저장/로드 모델
  ui/                 # 수기입력 UI, SME 체커, 스타일
  utils/              # 공통 데이터 모델과 상수
tests/
  parsers/            # 파일 파싱 테스트
  rules/              # 세무조정 계산 테스트
  smoke_test.py       # 핵심 로직 스모크 테스트
```

## 화면 흐름
1. `src/app.py`가 Streamlit 앱을 시작하고 세션 상태를 초기화한다.
2. 사용자는 사이드바에서 1~6단계 화면을 선택한다.
3. 각 화면은 `src/views/`의 모듈이 렌더링한다.
4. 업로드 화면은 `SmartALoader`를 통해 파일을 파싱한다.
5. 계산 화면은 `rules/`의 규칙 계산 모듈을 호출한다.
6. 출력 화면은 감사추적 Excel과 `.taxproj` 파일을 만든다.

## 데이터 흐름
```text
사용자 업로드 파일
  -> parsers.normalizer / parsers.smart_a
  -> SmartALoader
  -> 분개장 집계 / 규칙엔진 / LLM 후보 분석
  -> TaxAdjustmentResult
  -> 감사추적 Excel / 프로젝트 파일 / 화면 표시
```

## 기능 → 파일 매핑 (어떤 기능이 어디서 돌아가는가)

| 기능 | 핵심 파일 | 표시 화면 |
|------|----------|----------|
| 파일 표준화 (포맷 스니핑·인코딩·헤더 탐지·음수 표기) | `src/parsers/normalizer.py` | 2단계 진단 리포트 |
| 더존/WEHAGO 파싱 (분개장·재무제표·고정자산 소계 역부여) | `src/parsers/smart_a.py` | 2단계 |
| 전기 자료 (증감분석·기초잔액 대사용 별도 로더 — B/S·P&L·원가명세서·고정자산·분개장·원장·잔액명세서 7종) | `src/views/upload.py` (`prev_loader` 세션) | 2단계 하단 |
| 전년도 .taxproj 승계 (유보·결손금·판단자료) | `src/project/taxproj.py` `carry_forward_from` | 3단계 상단 |
| 분개장 1-pass 집계 (+특수관계인 매출) | `src/rules/aggregator.py` | 5단계 |
| 적수(積數) — B/S 기초 + 분개 증감 일별 계산 | `src/rules/jeoksu.py` | 5단계 계산 내역 |
| 세무조정 산식 (접대비·감가상각·인정이자·간주임대료 등) | `src/rules/` 항목별 모듈 | 5단계 |
| 법령 매핑·원문 조회·마지막 확인일 (law.go.kr) | `src/rules/legal_basis.py` | 5단계 법령 원문 |
| 전수 검토 체크리스트 (검토필요 항목에 근거법령·해석 첨부 — _GUIDANCE, law.go.kr 검증) | `src/rules/coverage.py` | 5단계 + PDF 4-2 |
| 감가상각 정률법 비망가액 특례 (영§26⑥⑦ — 취득가액 5%·비망가액 1천원, 월할 자산 미발동) | `src/rules/depreciation.py` | 5단계 |
| 업무용승용차 근거분개 차량번호 매칭 (오매칭 차단·공통 포함) | `src/rules/vehicle_match.py` | 5단계 + PDF |
| 세무 컨설팅 토픽 (현재상황·근거·시나리오 — 결정론적 발굴) | `src/rules/consulting.py` | 5·6단계 + PDF 7 |
| 참고파일 RAG (국세청 PDF/HWP 추출텍스트 키워드 검색 — 컨설팅 근거 보조) | `src/rag/reference_retriever.py` | 컨설팅·PDF·LLM 문장화 |
| 컨설팅 시나리오 LLM 문장화 (action 톤만 — 숫자·법령 불변) | `src/llm/consultant.py` | 5단계 (선택) |
| 자료요청 리스트 + 위험도(H/M/L) | `src/rules/data_requests.py` | 5단계 + PDF |
| 전년 대비 증감분석·기초잔액 대사 | `src/rules/yoy_analysis.py` | 5단계 + PDF |
| 별지15호 행 구성 (화면·PDF 공용 단일 소스) | `src/forms/summary_rows.py` | 5단계 + PDF |
| 검토패키지 PDF (①~⑧섹션 + ④ 4-1 근거분개·4-2 근거법령, 맑은고딕, 메모리 생성) | `src/forms/review_pdf.py` | 6단계 |
| 고객 설명 메모 (결정론적 템플릿) | `src/forms/review_pdf.py` `build_client_memo` | 5단계 + PDF |
| 감사추적 Excel | `src/forms/audit_trail.py` | 6단계 |
| LLM 1차 분류·선택 분석·Level 1 RAG (법령 조문 첨부) | `src/rules/classifier.py`, `src/llm/analyzer.py` | 4단계 |
| 특수관계인 표 (DART 최대주주현황 자동입력·출처구분·지분율 하이라이트) | `src/views/basic_info.py` | 1단계 |
| 수기 입력 라인체크·분류 UI (지급이자·가지급금·기부금 등) | `src/ui/manual_input.py` | 3단계 |

## 핵심 설계 원칙
- 파일 형식은 확장자가 아니라 파일 내용으로 판별한다.
- 계산 가능한 항목은 LLM이 아니라 규칙엔진으로 계산한다.
- LLM은 확정 판단이 아니라 검토 후보, 설명 초안, 누락자료 요청에 사용한다.
- API 조회 결과는 실패와 자료 없음을 구분한다.
- 고객자료는 로컬 처리와 임시파일 삭제를 기본 원칙으로 한다.

## 현재 주의점
- `src/views/calc.py`와 `src/ui/manual_input.py`가 아직 크다. 추후 기능별 서비스 계층으로 더 나눌 수 있다.
- (해결됨 2026-06) 당기순이익 미인식 시 계산 차단 + 수기입력 요구 — `src/views/calc.py` 사전 확인 게이트.
- (해결됨 2026-06) 출력용 임시파일은 메모리로 읽은 직후 삭제 — `src/views/output.py`.
- (해결됨 2026-06) DART 조회 실패와 자료 없음 구분 — `DartApiError`.
- (해결됨 2026-06) 최대주주·특수관계인 조회 엔드포인트 수정 — `majorstock`(대량보유, 명단 필드 없음) →
  `hyslrSttus`(최대주주현황, nm·relate·지분율) `src/apis/dart_api.py`. 단 정기보고서 제출 회사만 제공.
- 참고파일 RAG는 벡터DB 없이 키워드 검색이며 **계산엔진과 분리**(컨설팅·검토메모·PDF 보조 전용). 외부 네트워크 없음(로컬 텍스트).
- 검토필요 항목의 근거법령·해석은 PDF 재현성을 위해 결정론적 사전(`_GUIDANCE`)에 고정하고, 조문 원문은 5단계에서 on-demand 조회한다.

## 관련 문서
- 상세 설계: `1_기획설계/법인세_세무조정_자동화_전체설계.md` (법령 산식·적수·구현 상태)
- 산식 상세: `1_기획설계/규칙엔진_세무조정계산_설계.md` / LLM 계층: `1_기획설계/LLM_분개전체분석_설계.md`
