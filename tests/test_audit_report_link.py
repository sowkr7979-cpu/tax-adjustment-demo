"""DartApiClient.find_audit_report — 네트워크 없이 list.json 응답을 스텁해 검증.

비상장·최대주주현황 미제출 법인의 특수관계인 확인용 '감사보고서 바로가기'를
만드는 로직(우선순위·자료없음·뷰어 URL)을 회귀 보호한다.
"""
from src.apis.dart_api import DartApiClient, DART_DOC_VIEWER, DartApiError


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _client_with(responses):
    """pblntf_ty -> payload 매핑으로 session.get을 스텁한 클라이언트."""
    dart = DartApiClient(api_key="TESTKEY")

    def _fake_get(url, params=None, timeout=None):
        ty = (params or {}).get("pblntf_ty")
        return _FakeResp(responses[ty])

    dart.session.get = _fake_get  # type: ignore[assignment]
    return dart


def test_audit_report_found_prefers_standalone_over_consolidated():
    """같은 접수일이면 단독 감사보고서를 연결감사보고서보다 우선한다."""
    resp_f = {
        "status": "000",
        "list": [
            {"report_nm": "연결감사보고서 (2024.12)", "rcept_no": "20250320000111", "rcept_dt": "20250320"},
            {"report_nm": "감사보고서 (2024.12)", "rcept_no": "20250320000999", "rcept_dt": "20250320"},
        ],
    }
    dart = _client_with({"F": resp_f, "A": {"status": "013", "list": []}})
    rpt = dart.find_audit_report("00126380")
    assert rpt is not None
    assert rpt["rcept_no"] == "20250320000999"          # 단독 감사보고서
    assert rpt["url"] == DART_DOC_VIEWER.format(rcept_no="20250320000999")
    assert "감사보고서" in rpt["report_nm"]


def test_audit_report_falls_back_to_periodic_when_no_external_audit():
    """외부감사(F) 공시가 없으면 정기공시(A, 사업보고서)로 폴백한다."""
    resp_a = {
        "status": "000",
        "list": [
            {"report_nm": "사업보고서 (2024.12)", "rcept_no": "20250401000222", "rcept_dt": "20250401"},
        ],
    }
    dart = _client_with({"F": {"status": "013", "list": []}, "A": resp_a})
    rpt = dart.find_audit_report("00126380")
    assert rpt is not None
    assert rpt["rcept_no"] == "20250401000222"
    assert rpt["url"].endswith("rcpNo=20250401000222")


def test_audit_report_none_when_no_disclosure():
    """F·A 모두 자료 없음(013)이면 None — 외부감사 비대상 추정."""
    empty = {"status": "013", "list": []}
    dart = _client_with({"F": empty, "A": empty})
    assert dart.find_audit_report("00126380") is None


def test_audit_report_api_error_raises():
    """키 오류 등(≠013)은 예외로 던져 '자료 없음'과 구분한다."""
    err = {"status": "010", "message": "등록되지 않은 키"}
    empty = {"status": "013", "list": []}
    dart = _client_with({"F": err, "A": empty})
    try:
        dart.find_audit_report("00126380")
    except DartApiError:
        pass
    else:
        raise AssertionError("DartApiError가 발생해야 한다")
