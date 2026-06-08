"""DART API 키 동작 확인 — 네트워크 필요. 수동 실행 전용: python tests/test_dart_key.py

pytest 수집 시에는 아무 코드도 실행되지 않는다 (모든 로직이 __main__ 가드 안).
"""


def main() -> None:
    import sys, os
    sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

    from dotenv import load_dotenv
    load_dotenv()

    from src.apis.dart_api import DartApiClient

    dart = DartApiClient()
    # 보안: 키 값은 출력하지 않는다 — 설정 여부만 표시
    print(f"API Key: {'설정됨' if dart.api_key else '미설정'} ({len(dart.api_key)}자)")

    print("\n[1] 삼성전자 검색 중 (corp code 목록 최초 다운로드시 시간 소요)...")
    results = dart.search_by_name("삼성전자", limit=5)
    print(f"  검색 결과: {len(results)}개")
    for r in results[:3]:
        print(f"  - {r['corp_name']} / 주식코드:{r['stock_code']}")

    assert results, "검색 결과 없음"

    print("\n[2] 상세 정보 조회...")
    info = dart.get_company_info(results[0]["corp_code"])
    assert info, "상세 조회 실패"
    print(f"  법인명: {info.corp_name}")
    print(f"  사업자번호: {info.bizr_no}")
    print(f"  대표자: {info.ceo_nm}")
    print(f"  주소: {info.adres[:50]}")
    print(f"  결산월: {info.acc_mt}월")
    print(f"  설립일: {info.est_dt}")

    print("\nDART API 정상 동작 확인 완료")


if __name__ == "__main__":
    main()
