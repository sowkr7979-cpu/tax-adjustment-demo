# Architecture

## 현재 구조

```text
src/
  app.py              # Streamlit 진입점, 페이지 라우팅, 세션 초기화
  views/              # 1~6단계 화면 모듈
  parsers/            # 더존/WEHAGO 엑셀, HTML형 xls, CSV 파싱
  rules/              # 세무조정 규칙 계산 엔진
  llm/                # Ollama 기반 로컬 LLM 분석
  apis/               # DART, 법령정보 API 클라이언트
  forms/              # 별지 추천, 감사추적 Excel 생성
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
| 전수 검토 체크리스트 33항목 | `src/rules/coverage.py` | 5단계 |
| 자료요청 리스트 + 위험도(H/M/L) | `src/rules/data_requests.py` | 5단계 + PDF |
| 전년 대비 증감분석·기초잔액 대사 | `src/rules/yoy_analysis.py` | 5단계 + PDF |
| 별지15호 행 구성 (화면·PDF 공용 단일 소스) | `src/forms/summary_rows.py` | 5단계 + PDF |
| 검토패키지 PDF (7섹션, 맑은고딕, 메모리 생성) | `src/forms/review_pdf.py` | 6단계 |
| 고객 설명 메모 (결정론적 템플릿) | `src/forms/review_pdf.py` `build_client_memo` | 5단계 + PDF |
| 감사추적 Excel | `src/forms/audit_trail.py` | 6단계 |
| LLM 1차 분류·선택 분석·Level 1 RAG | `src/rules/classifier.py`, `src/llm/analyzer.py` | 4단계 |
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

## 관련 문서
- 상세 설계: `1_기획설계/법인세_세무조정_자동화_전체설계.md` (법령 산식·적수·구현 상태)
- 산식 상세: `1_기획설계/규칙엔진_세무조정계산_설계.md` / LLM 계층: `1_기획설계/LLM_분개전체분석_설계.md`
