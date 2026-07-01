#!/usr/bin/env bash
# GitHub 저장소 생성 + 현재 브랜치 푸시 — 토큰은 인자로만 받고 화면/깃에 남기지 않는다.
#
# 사용법 (Git Bash):
#   bash scripts/push_to_github.sh <GITHUB_사용자명> <저장소이름> <PAT토큰> [public|private]
#
# PAT 토큰 발급: https://github.com/settings/tokens (classic, 'repo' 권한) 또는
#               https://github.com/settings/personal-access-tokens (fine-grained, Contents: RW)
#
# 예:  bash scripts/push_to_github.sh hwshin tax-adjustment-demo ghp_XXXX public
set -euo pipefail

USER="${1:?GitHub 사용자명 필요}"
REPO="${2:?저장소 이름 필요}"
TOKEN="${3:?PAT 토큰 필요}"
VIS="${4:-public}"
PRIVATE=false; [ "$VIS" = "private" ] && PRIVATE=true

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "▶ 저장소 생성: $USER/$REPO ($VIS) · 브랜치 $BRANCH"

# 1) 저장소 생성 (이미 있으면 422 → 무시하고 진행)
curl -sf -X POST https://api.github.com/user/repos \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -d "{\"name\":\"$REPO\",\"private\":$PRIVATE,\"description\":\"법인세 세무조정 자동화 — 라이브 데모(가상 데이터)\"}" \
  >/dev/null 2>&1 && echo "  저장소 생성 완료" || echo "  (저장소가 이미 있거나 생성 생략 — 계속)"

# 2) 원격 연결 (토큰은 URL에 임시로만; git config엔 토큰 없는 URL로 정리)
git remote remove origin 2>/dev/null || true
git push "https://${USER}:${TOKEN}@github.com/${USER}/${REPO}.git" "HEAD:${BRANCH}"
git remote add origin "https://github.com/${USER}/${REPO}.git"
git branch --set-upstream-to="origin/${BRANCH}" "$BRANCH" 2>/dev/null || true

echo "✅ 푸시 완료 → https://github.com/${USER}/${REPO} (브랜치 ${BRANCH})"
echo "다음: https://share.streamlit.io → Create app → 이 저장소·브랜치 → Main file: streamlit_app.py"
echo "      → Advanced → Secrets 에 ANTHROPIC_API_KEY 붙여넣기 → Deploy"
