"""더존 XLS 파일 포맷 진단 스크립트.
사용법: python tests/diagnose_xls.py "F:\...\재무상태표_2512_비티진.xls"
"""
import sys, os

if len(sys.argv) < 2:
    print("사용법: python tests/diagnose_xls.py <파일경로>")
    sys.exit(1)

path = sys.argv[1]
print(f"파일: {path}")
print(f"크기: {os.path.getsize(path):,} bytes")
print()

with open(path, "rb") as f:
    raw = f.read(256)

# 시그니처 출력
print(f"헥스(첫 16바이트): {raw[:16].hex(' ')}")
print(f"텍스트(첫 100바이트): {raw[:100]}")
print()

# 포맷 판별
OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP  = b"PK\x03\x04"

stripped = raw.lstrip(b"\xef\xbb\xbf\xff\xfe\xfe\xff")  # BOM 제거

if raw[:8] == OLE2:
    print("→ 포맷: OLE2 복합문서 (BIFF XLS 바이너리) — xlrd로 읽어야 함")
elif raw[:4] == ZIP:
    print("→ 포맷: ZIP (XLSX / OpenXML) — openpyxl로 읽어야 함")
elif b"<?xml" in stripped[:50] or b"<Workbook" in stripped[:100]:
    print("→ 포맷: Excel 2003 XML (SpreadsheetML) — XML 파서로 읽어야 함")
elif b"<html" in stripped[:100].lower() or b"<!doctype" in stripped[:100].lower():
    print("→ 포맷: HTML 테이블 (.xls 위장) — pd.read_html 로 읽어야 함")
elif b"MIME-Version" in raw[:100] or b"multipart" in raw[:100]:
    print("→ 포맷: MHTML (웹 아카이브) — MIME 파싱 후 HTML 추출 필요")
else:
    print("→ 포맷: 알 수 없음")

print()
print("--- 전체 256바이트 ---")
try:
    print(raw[:256].decode("cp949", errors="replace"))
except Exception as e:
    print(f"디코딩 오류: {e}")
    print(raw[:256])
