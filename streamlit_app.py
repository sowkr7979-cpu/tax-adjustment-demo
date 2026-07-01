"""Streamlit Cloud 진입점 (배포 데모).

Streamlit Cloud는 리포지토리 루트의 이 파일을 메인으로 실행한다.
저장소 루트를 sys.path에 넣어 `from src....` 절대 임포트가 동작하게 한 뒤
실제 앱(src/app.py)을 불러온다. app.py의 모듈 최상위 코드가 화면을 렌더한다.

로컬 실행은 기존대로 `세무조정앱_실행.bat`(streamlit run src/app.py)을 써도 되고,
이 파일(streamlit run streamlit_app.py)로 실행해도 동일하게 동작한다.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.resolve()))

import src.app  # noqa: F401,E402  (임포트 시 페이지가 렌더된다)
