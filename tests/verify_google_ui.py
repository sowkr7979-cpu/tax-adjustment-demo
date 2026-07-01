"""about.google 스타일 UI 구현 검증."""
import sys, os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# 1. styles.py 핵심 값 확인
with open("src/ui/styles.py", encoding="utf-8") as f:
    css = f.read()

style_checks = {
    "Google 파란색 primaryColor": "#1a73e8",
    "Google 배경색 ffffff": "#ffffff",
    "Google 텍스트색 202124": "#202124",
    "Google 서브텍스트 5f6368": "#5f6368",
    "Google pill 버튼 border-radius": "100px",
    "Google 카드 border-radius": "16px",
    "page_header 함수": "def page_header",
    "section_title 함수": "def section_title",
    "status_badge 함수": "def status_badge",
    "info_card 함수": "def info_card",
    "Google Sans 폰트": "Google Sans",
    "시스템 폰트 스택": "system-ui",
    "메트릭 카드 스타일": "stMetric",
    "파일업로더 스타일": "stFileUploader",
    "라디오 스타일": "stRadio",
    "스크롤바 스타일": "webkit-scrollbar",
}
for desc, val in style_checks.items():
    assert val in css, f"MISSING: {desc} ({val})"
    print(f"  [OK] styles.py — {desc}")

# 2. app.py Google 통합 확인 (라우팅·사이드바)
with open("src/app.py", encoding="utf-8") as f:
    app = f.read()

app_checks = {
    "CSS 주입": "GOOGLE_CSS",
    "사이드바 브랜드 HTML": "세무조정 자동화",
    "Ollama 상태 HTML": "llm_color",
    "unsafe_allow_html": "unsafe_allow_html=True",
}
for desc, val in app_checks.items():
    assert val in app, f"MISSING in app.py: {desc} ({val})"
    print(f"  [OK] app.py — {desc}")

# 2b. views/ 페이지 모듈 확인 (본문은 src/views/로 분리됨)
import glob
views = ""
for path in sorted(glob.glob("src/views/*.py")):
    with open(path, encoding="utf-8") as f:
        views += f.read()

view_checks = {
    "page_header 사용": "page_header(",
    "section_title 사용": "section_title(",
    "info_card 사용": "info_card(",
    "6개 페이지 — 기본정보": "기본 정보 입력",
    "6개 페이지 — 파일업로드": "재무제표 업로드",
    "6개 페이지 — 수기입력": "수기 입력 항목",
    "6개 페이지 — AI검토보조": "AI 검토 보조",
    "6개 페이지 — 계산검토": "세무조정 계산 및 검토",
    "6개 페이지 — 출력": "출력 파일 생성",
}
for desc, val in view_checks.items():
    assert val in views, f"MISSING in views/: {desc} ({val})"
    print(f"  [OK] views/ — {desc}")

# 3. config.toml Google 테마
with open(".streamlit/config.toml", encoding="utf-8") as f:
    cfg = f.read()

cfg_checks = {
    "primaryColor Google 파란": "#1a73e8",
    "backgroundColor": "#ffffff",
    "textColor": "#202124",
    "secondaryBg": "#f8f9fa",
}
for desc, val in cfg_checks.items():
    assert val in cfg, f"MISSING in config.toml: {desc} ({val})"
    print(f"  [OK] config.toml — {desc}")

# 4. 서버 응답
import urllib.request
resp = urllib.request.urlopen("http://localhost:8501/", timeout=5)
assert resp.status == 200
print(f"  [OK] HTTP 200 (Streamlit 서버 응답 정상)")

print()
print("=" * 52)
print("about.google 스타일 UI 구현 검증 전체 통과")
