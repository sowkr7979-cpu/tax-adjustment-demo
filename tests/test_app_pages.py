# -*- coding: utf-8 -*-
"""앱 페이지 렌더 스모크 테스트 — views 분리 후 NameError·import 누락 탐지."""
import pytest

from streamlit.testing.v1 import AppTest

APP = "src/app.py"
PAGES = [
    "1. 기본정보", "2. 파일 업로드", "3. 수기 입력",
    "4. AI 검토 보조", "5. 계산·검토", "6. 출력",
]


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_without_exception(page):
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    # 사이드바 radio로 페이지 전환
    at.sidebar.radio[0].set_value(page).run()
    assert not at.exception, f"{page} 렌더 중 예외: {at.exception}"
