"""DART 재무요약 + 주주현황 API 통합 테스트 — 네트워크 필요. 수동 실행 전용: python tests/test_dart_sme.py

pytest 수집 시에는 아무 코드도 실행되지 않는다 (모든 로직이 __main__ 가드 안).
"""


def main() -> None:
    import sys, os
    sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from dotenv import load_dotenv
    load_dotenv()

    from src.apis.dart_api import DartApiClient
    from src.ui.sme_checker import ksic_to_industry

    dart = DartApiClient()

    # 삼성전자로 전체 흐름 테스트
    results = dart.search_by_name("삼성전자", limit=1)
    assert results, "검색 실패"
    code = results[0]["corp_code"]

    info = dart.get_company_info(code)
    assert info, "기본정보 조회 실패"
    print(f"[1] 법인명: {info.corp_name}")
    print(f"    업종코드: {info.industry_code} -> {ksic_to_industry(info.industry_code)}")

    fin = dart.get_financial_summary(code, "2024")
    rev = fin.get("revenue")
    ast = fin.get("total_assets")
    print(f"[2] 매출액: {rev:,}원" if rev else "[2] 매출액: 조회 실패(비상장 또는 API 제한)")
    print(f"[3] 자산총계: {ast:,}원" if ast else "[3] 자산총계: 조회 실패")

    shs = dart.get_major_shareholders(code, "2024")
    print(f"[4] 주주·특수관계인: {len(shs)}명")
    for s in shs[:5]:
        print(f"    {s['nm']} / {s['relate']} / {s['ownership_pct']}%")

    # 지배관계 추정
    has_ctrl = any(
        float(s["ownership_pct"].replace(",", "") or 0) > 30
        for s in shs
        if s["ownership_pct"].replace(",", "").replace(".", "").isdigit() or
           s["ownership_pct"].replace(",", "").replace(".", "").lstrip("-").isdigit()
    )
    print(f"[5] 지배기업 존재 추정: {has_ctrl}")

    # 특수관계인 목록 생성
    related = [f"{s['nm']} ({s['relate']})" for s in shs if s["nm"]]
    print(f"[6] 특수관계인 목록 ({len(related)}명):")
    for r in related[:5]:
        print(f"    {r}")

    print()
    print("DART SME 자동입력 데이터 조회 완료")


if __name__ == "__main__":
    main()
