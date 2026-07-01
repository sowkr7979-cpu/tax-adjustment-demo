"""자본금과적립금조정명세서(을) — 유보 잔액 명세 (기초 + 증가 − 감소 = 기말).

화면·PDF·Excel 공용 단일 소스. 당기 세무조정 결과(유보/△유보)와 전기이월 유보를
결합해 기말 유보 잔액을 산출한다. 자동 추인이 불확실한 항목은 '검토' 플래그로 표시 —
환입·추인 확정은 회계사 판단(별지 제50호서식(을) 작성 기준).
"""
from __future__ import annotations

from src.utils.models import TaxAdjustmentResult


def build_reserve_status(
    prior_reserves: list[dict],
    tax_result: TaxAdjustmentResult,
    depr_denial_end: int = 0,
    bad_debt_method: str = "총액법",
    decrease_overrides: dict[str, int] | None = None,
    manual_rows: list[dict] | None = None,
) -> list[dict]:
    """반환: [{과목, 기초, 증가, 감소, 기말, 처분, 검토}].

    prior_reserves: [{code, amount, disposition}] 전기이월 유보 (기초잔액)
    tax_result: 당기 세무조정 결과
    depr_denial_end: 당기말 감가상각 부인누계 (감가상각 엔진 산출, 기말 정합용)
    bad_debt_method: 대손충당금 처리방식 "총액법"(법§34③ 기본) | "보충법"
    decrease_overrides: {과목: 당기 감소(추인)} — 회계사가 보정 입력한 감소액 (검토 플래그 해제)
    manual_rows: [{과목, 기초, 증가, 감소, 처분}] — 수기 추가 유보 항목(일시상각·압축기장충당금·준비금 등)
    검토=True: 추인(감소)이 자동 반영되지 않아 수기 확인 필요.
    """
    r = tax_result
    opening: dict[str, tuple[int, str]] = {}
    for it in prior_reserves or []:
        code = str(it.get("code", "")).strip()
        if code:
            opening[code] = (int(it.get("amount", 0)), str(it.get("disposition", "유보")))

    rows: list[dict] = []
    used: set[str] = set()

    def _add(code, base, inc, dec, disp, dec_known, force_review=False):
        used.add(code)
        if base == 0 and inc == 0 and dec == 0:
            return
        rows.append({
            "과목": code, "기초": base, "증가": inc, "감소": dec,
            "기말": base + inc - dec, "처분": disp,
            "검토": bool(force_review or (base > 0 and dec == 0 and not dec_known)),
        })

    # 감가상각 부인누계 — 기말은 엔진 부인누계(denial_end)에 정합, 기초는 역산
    _dep_prior = opening.get("감가상각 부인누계", (0, "유보"))[0]
    _dep_base = _dep_prior
    if depr_denial_end or r.depreciation_excess or r.depreciation_approved or _dep_base:
        _inc, _dec = r.depreciation_excess, r.depreciation_approved
        _dep_mismatch = False
        if depr_denial_end:
            # 기초 = 기말 − 증가 + 감소 (엔진 기말과 정합)
            _dep_base = depr_denial_end - _inc + _dec
            # 전기 을표 기재 기초와 역산 기초가 다르면 경고 (전기 부인누계 입력오류·의제상각 누락 탐지)
            _dep_mismatch = _dep_prior != 0 and _dep_prior != _dep_base
        _add("감가상각 부인누계", _dep_base, _inc, _dec, "유보", True,
             force_review=_dep_mismatch)

    # 대손충당금 — 총액법(법§34③): 전기 유보 전액 환입(감소) + 당기 설정(증가)
    #             보충법: 전기 유보 이월, 당기 추인(감소)은 수기 확인(검토 플래그 ON)
    _bd_base = opening.get("대손충당금 한도초과", (0, "유보"))[0]
    if bad_debt_method == "보충법":
        _add("대손충당금 한도초과", _bd_base, r.bad_debt_excess, 0, "유보", False)
    else:
        _add("대손충당금 한도초과", _bd_base, r.bad_debt_excess, _bd_base, "유보", True)

    # 추인이 자동 확정되지 않는 유보(환입은 차기 수기) — 검토 플래그 대상
    _manual_reversal = [
        ("퇴직급여충당금 한도초과", r.pension_excess, "유보"),
        ("업무용승용차 감가상각 한도초과", r.vehicle_depr_excess, "유보"),
        ("외화환산손실 부인", r.forex_loss_disallowed, "유보"),
        ("파생상품 평가손실 부인", r.derivative_loss_disallowed, "유보"),
        ("유가증권 평가손실 부인", r.securities_loss_disallowed, "유보"),
        ("재고자산 평가 조정", r.inventory_adjustment, "유보"),
        ("건설자금이자 자본화", r.interest_construction, "유보"),
    ]
    for code, inc, disp in _manual_reversal:
        base = opening.get(code, (0, disp))[0]
        _add(code, base, inc, 0, disp, False)

    # △유보 (손금산입·익금불산입) — 음(−)의 유보 누적
    _minus = [
        ("퇴직연금 부담금(손금산입)", r.pension_deduction, "△유보"),
        ("외화환산이익 익금불산입", r.forex_gain_excluded, "△유보"),
        ("파생상품 평가이익 익금불산입", r.derivative_gain_excluded, "△유보"),
        ("유가증권 평가이익 익금불산입", r.securities_gain_excluded, "△유보"),
    ]
    # △유보는 차기 추인(익금산입)이 엔진에서 자동 산출되지 않으므로 검토 유도
    for code, amt, disp in _minus:
        base = opening.get(code, (0, disp))[0]
        _add(code, base, amt, 0, disp, False)

    # 회계사 직접 입력 세무조정 중 유보/△유보 — 을표 증가행으로 자동 반영 (차기 추인 추적)
    #   tax_result에 custom_adjustment_lines가 실려 오므로 별도 인자 없이 흡수한다.
    for _c in (getattr(r, "custom_adjustment_lines", None) or []):
        _cdisp = str(_c.get("disposition", "")).strip()
        if _cdisp not in ("유보", "△유보"):
            continue
        _ccode = f"[수기] {str(_c.get('name', '')).strip()}"
        _camt = int(_c.get("amount", 0) or 0)
        if not _camt:
            continue
        _cbase = opening.get(_ccode, (0, _cdisp))[0]
        _add(_ccode, _cbase, _camt, 0, _cdisp, False)

    # 의제배당 무상증자·자본전입형(법§16①2호·3호) — 교부주식 세무상 취득가액 증가분은 유보.
    #   차기 주식 양도 시 추인되므로 을표 증가행으로 반영(차기 추적). 기타 처분분(감자·합병 등)은 제외.
    #   과목명은 2호(무상증자)·3호(자기주식 재배정)를 함께 담으므로 '자본전입형'으로 일반화.
    _dd_yubo = sum(
        int(_d.get("amount", 0) or 0)
        for _d in (getattr(r, "deemed_dividend_lines", None) or [])
        if str(_d.get("disposition", "")).strip() == "유보"
    )
    if _dd_yubo:
        _ddcode = "의제배당(자본전입형) 유보"
        _ddbase = opening.get(_ddcode, (0, "유보"))[0]
        _add(_ddcode, _ddbase, _dd_yubo, 0, "유보", False)

    # 스펙에 없는 전기 유보(수동 입력 등) — 기초만 이월, 추인 검토 필요
    for code, (base, disp) in opening.items():
        if code not in used and base:
            rows.append({
                "과목": code, "기초": base, "증가": 0, "감소": 0,
                "기말": base, "처분": disp, "검토": True,
            })

    # 회계사 보정: 당기 감소(추인) 직접 입력 반영 → 기말 재계산, 검토 해제
    _ov = decrease_overrides or {}
    for row in rows:
        if row["과목"] in _ov:
            row["감소"] = int(_ov[row["과목"]])
            row["기말"] = row["기초"] + row["증가"] - row["감소"]
            row["검토"] = False

    # 수기 추가 유보 항목 (일시상각·압축기장충당금·준비금 등 — 자동 계산 범위 밖)
    for m in (manual_rows or []):
        code = str(m.get("과목", "")).strip()
        if not code:
            continue
        base = int(m.get("기초", 0)); inc = int(m.get("증가", 0)); dec = int(m.get("감소", 0))
        if base == 0 and inc == 0 and dec == 0:
            continue
        rows.append({
            "과목": code, "기초": base, "증가": inc, "감소": dec,
            "기말": base + inc - dec, "처분": str(m.get("처분", "유보")) or "유보",
            "검토": False,
        })

    return rows


def reserve_totals(rows: list[dict]) -> dict:
    """유보/△유보 기말 합계."""
    yubo = sum(x["기말"] for x in rows if x["처분"] == "유보")
    minus = sum(x["기말"] for x in rows if x["처분"] == "△유보")
    return {"유보_기말": yubo, "△유보_기말": minus, "순유보_기말": yubo - minus}
