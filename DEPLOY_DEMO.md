# 라이브 데모 배포 가이드 (Streamlit Community Cloud)

이력서에 넣을 공개 데모 URL을 만드는 절차입니다. 면접관이 접속해 **데모 데이터 불러오기**만 누르면
파일 업로드 없이 규칙엔진 결과를 라이브로 확인할 수 있습니다.

> ⚠️ 이 배포는 **가상(더미) 데이터 전용**입니다. 실제 고객 세무자료는 절대 올리지 마세요.
> 이 프로젝트의 LLM은 **로컬 Ollama 전용**입니다(외부 LLM API 미사용, ADR-001/002).
> 클라우드 데모 환경에는 Ollama가 없으므로 **AI 검토보조는 '선택 기능 비활성'으로 표시**되고,
> 세무조정 계산(규칙엔진)은 데모에서도 전부 정상 동작합니다.

## 0. 사전 (한 번만)

- GitHub 계정, Streamlit 계정(https://share.streamlit.io — GitHub 로그인).

## 1. GitHub에 올리기

민감파일은 `.gitignore`로 이미 제외됩니다(`.env`, `*.xls/xlsx/hwp`, `*.taxproj`, `.streamlit/secrets.toml`).

```bash
# 새 GitHub 저장소(예: hwshin/tax-adjustment-demo)를 만든 뒤:
git checkout -b deploy
git add .
git commit -m "배포 데모: 규칙엔진 + 더미 데모 데이터 (LLM은 로컬 Ollama 전용)"
git remote add origin https://github.com/<사용자>/<저장소>.git
git push -u origin deploy
```

## 2. Streamlit Cloud에서 배포

1. https://share.streamlit.io → **Create app** → GitHub 저장소·브랜치 선택
2. **Main file path**: `streamlit_app.py`  ← (루트 진입점, `src.` 임포트 경로를 잡아줌)
3. **Deploy** → 몇 분 뒤 `https://<앱이름>.streamlit.app` URL 생성 → 이력서에 기재.

한글 폰트는 `packages.txt`(`fonts-nanum`)로 리눅스에 설치되며, PDF·화면 모두 정상 렌더됩니다.

## 3. 로컬에서 AI 검토보조까지 확인하려면

```bash
# Ollama 설치(https://ollama.com) 후 모델 준비
ollama pull gemma4
# 앱 실행 (또는 세무조정앱_실행.bat 더블클릭)
python -m streamlit run src/app.py
```

환경변수로 재정의 가능: `OLLAMA_BASE_URL`(기본 http://localhost:11434), `OLLAMA_MODEL`(기본 gemma4:latest).

## 4. 이력서 문구 예시

> 법인세 세무조정 자동화 (규칙엔진 + 로컬 LLM 검토보조) — 라이브 데모: https://<앱이름>.streamlit.app
> (좌측 사이드바 '데모 데이터 불러오기' → 2·5·6단계 확인, 가상 데이터)

## 5. 안전 체크리스트

- [ ] 데모는 더미 데이터만 — 실제 고객파일 업로드 금지 문구 안내
- [ ] 고객 재무자료는 로컬 실행에서만 취급 (외부 클라우드로 전송되지 않는 구조)
