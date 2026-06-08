"""Apple 스타일 UI 구현 검증."""
import sys, os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# 1. styles.py 핵심 값 확인
with open("src/ui/styles.py", encoding="utf-8") as f:
    css = f.read()

style_checks = {
    "Apple 파란색 primaryColor": "#0071e3",
    "Apple 배경색 fbfbfd": "#fbfbfd",
    "Apple 텍스트색 1d1d1f": "#1d1d1f",
    "Apple 서브텍스트 86868b": "#86868b",
    "Apple 필 버튼 border-radius": "980px",
    "Apple 카드 border-radius": "16px",
    "page_header 함수": "def page_header",
    "section_title 함수": "def section_title",
    "status_badge 함수": "def status_badge",
    "info_card 함수": "def info_card",
    "SF Pro 폰트": "SF Pro Display",
    "시스템 폰트 스택": "-apple-system",
    "메트릭 카드 스타일": "stMetric",
    "파일업로더 스타일": "stFileUploader",
    "라디오 스타일": "stRadio",
    "스크롤바 스타일": "webkit-scrollbar",
}
for desc, val in style_checks.items():
    assert val in css, f"MISSING: {desc} ({val})"
    print(f"  [OK] styles.py — {desc}")

# 2. app.py Apple 통합 확인
with open("src/app.py", encoding="utf-8") as f:
    app = f.read()

app_checks = {
    "CSS 주입": "APPLE_CSS",
    "page_header 사용": "page_header(",
    "section_title 사용": "section_title(",
    "info_card 사용": "info_card(",
    "사이드바 브랜드 HTML": "gradient",
    "Ollama 상태 HTML": "llm_color",
    "unsafe_allow_html": "unsafe_allow_html=True",
    "6개 페이지 — 기본정보": "기본 정보 입력",
    "6개 페이지 — 파일업로드": "Smart A Excel",
    "6개 페이지 — 수기입력": "수기 입력 항목",
    "6개 페이지 — LLM분석": "LLM 2차 정밀",
    "6개 페이지 — 계산검토": "세무조정 계산 및 검토",
    "6개 페이지 — 출력": "출력 파일 생성",
}
for desc, val in app_checks.items():
    assert val in app, f"MISSING in app.py: {desc} ({val})"
    print(f"  [OK] app.py — {desc}")

# 3. config.toml Apple 테마
with open(".streamlit/config.toml", encoding="utf-8") as f:
    cfg = f.read()

cfg_checks = {
    "primaryColor Apple 파란": "#0071e3",
    "backgroundColor": "#fbfbfd",
    "textColor": "#1d1d1f",
    "secondaryBg": "#f5f5f7",
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
print("Apple 스타일 UI 구현 검증 전체 통과")
