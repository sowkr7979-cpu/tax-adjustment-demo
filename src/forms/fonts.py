"""한글 폰트 경로 해석 — Windows(로컬)·Linux(배포) 양쪽 지원.

로컬 실무는 Windows 맑은고딕, Streamlit Cloud 배포는 나눔고딕(packages.txt: fonts-nanum).
PDF(fpdf2)와 도식(matplotlib) 모두 이 해석기를 통해 폰트를 얻는다.
"""
from __future__ import annotations

from pathlib import Path

# (정규체, 볼드체) 후보 — 앞에서부터 존재하는 것을 사용
_REGULAR_BOLD_CANDIDATES = [
    (r"C:\Windows\Fonts\malgun.ttf", r"C:\Windows\Fonts\malgunbd.ttf"),
    ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
     "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
    ("/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
     "/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf"),
]


def korean_fonts() -> tuple[str, str]:
    """(정규체 경로, 볼드체 경로) 반환. 볼드가 없으면 정규체로 대체."""
    for reg, bold in _REGULAR_BOLD_CANDIDATES:
        if Path(reg).exists():
            bold_path = bold if Path(bold).exists() else reg
            return reg, bold_path
    # 최후 폴백 — 어느 후보도 없으면 첫 후보 경로를 그대로 반환(생성 시 오류로 드러남)
    return _REGULAR_BOLD_CANDIDATES[0]


def korean_font_regular() -> str:
    return korean_fonts()[0]
