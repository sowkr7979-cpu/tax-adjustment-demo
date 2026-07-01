# 라이브 데모 배포 가이드 (Streamlit Community Cloud)

이력서에 넣을 공개 데모 URL을 만드는 절차입니다. 면접관이 접속해 **데모 데이터 불러오기**만 누르면
파일 업로드 없이 규칙엔진 결과를 라이브로 확인할 수 있습니다.

> ⚠️ 이 배포는 **가상(더미) 데이터 전용**입니다. 실제 고객 세무자료는 절대 올리지 마세요.
> 프로젝트 본래 원칙(로컬 전용·외부 LLM 금지)은 실무용이며, 공개 데모만 Claude API를 씁니다.

## 0. 사전 (한 번만)

- **Anthropic 키 재발급**: 대화창에 붙여넣은 키는 노출됐으니 콘솔에서 재발급하세요.
- **월 지출한도 설정**: Anthropic 콘솔 → Billing → Usage limits (게이트 없는 공개 데모라 필수 권장).
- GitHub 계정, Streamlit 계정(https://share.streamlit.io — GitHub 로그인).

## 1. GitHub에 올리기

민감파일은 `.gitignore`로 이미 제외됩니다(`.env`, `*.xls/xlsx/hwp`, `*.taxproj`, `.streamlit/secrets.toml`).
**키는 절대 커밋하지 마세요.**

```bash
# 새 GitHub 저장소(예: hwshin/tax-adjustment-demo)를 만든 뒤:
git checkout -b deploy
git add .
git commit -m "배포 데모: Claude API 검토보조 + OpenAI 스타일 + 더미 데모 데이터"
git remote add origin https://github.com/<사용자>/<저장소>.git
git push -u origin deploy
```

## 2. Streamlit Cloud에서 배포

1. https://share.streamlit.io → **Create app** → GitHub 저장소·브랜치(`deploy`) 선택
2. **Main file path**: `streamlit_app.py`  ← (루트 진입점, `src.` 임포트 경로를 잡아줌)
3. **Advanced settings → Secrets** 에 아래를 붙여넣기 (여기에만! 코드/깃 금지):
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-api03-...(재발급한 키)"
   # 비용을 더 낮추려면:
   # ANTHROPIC_MODEL = "claude-haiku-4-5"
   ```
4. **Deploy** → 몇 분 뒤 `https://<앱이름>.streamlit.app` URL 생성 → 이력서에 기재.

한글 폰트는 `packages.txt`(`fonts-nanum`)로 리눅스에 설치되며, PDF·화면 모두 정상 렌더됩니다.

## 3. 이력서 문구 예시

> 법인세 세무조정 자동화 (규칙엔진 + AI 검토보조) — 라이브 데모: https://<앱이름>.streamlit.app
> (좌측 사이드바 '데모 데이터 불러오기' → 2·5·6단계 확인, 가상 데이터)

## 4. 비용·안전 체크리스트

- [ ] Anthropic 키 재발급 완료 (대화창 노출 키 폐기)
- [ ] 월 지출한도 설정 완료
- [ ] Secrets는 Streamlit Cloud에만, 저장소엔 `secrets.toml.example`만
- [ ] 데모는 더미 데이터만 — 실제 고객파일 업로드 금지 문구 안내
