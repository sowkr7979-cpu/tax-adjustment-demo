"""5단계 — 세무조정 계산·검토 (집계 → 법령 산식 → 별지15호 → 드릴다운)."""
from __future__ import annotations
from datetime import date

import streamlit as st

from src.parsers.smart_a import SmartALoader
from src.rules.aggregator import aggregate_journals, sum_related_party_revenue
from src.rules.depreciation import calc_depreciation_all
from src.rules.entertainment import calc_entertainment
from src.rules.donation import calc_donation
from src.rules.allowances import (
    calc_bad_debt_allowance, calc_retirement_allowance, calc_pension_deduction,
)
from src.rules.income_items import calc_deemed_interest_by_party, calc_deemed_rental
from src.rules.jeoksu import jeoksu_from_deltas, account_jeoksu, fy_days
from src.rules.dividend import calc_dividend_exclusion
from src.rules.legal_basis import ADJUSTMENT_LEGAL_BASIS, fetch_legal_text
import src.rules.legal_basis as legal_basis
from src.rules.data_requests import build_data_requests, assess_risk
from src.rules.yoy_analysis import yoy_table, yoy_flags, bs_opening_check
from src.forms.summary_rows import adjustment_rows, adj_type
from src.rules.coverage import run_coverage_check
from src.rules.other_adjustments import (
    calc_penalty, calc_officer_bonus_excess, calc_officer_retirement_excess,
)
from src.rules.vehicle import calc_vehicle
from src.rules.tax_base import compute_all, eligible_carryforward_total
from src.utils.constants import (
    get_prime_rate, LOSS_CARRYFORWARD_SME_RATE, LOSS_CARRYFORWARD_GENERAL_RATE,
)
from src.utils.models import TaxAdjustmentResult
from src.ui.manual_input import _bs_amount, _bs_amount_detail
from src.ui.styles import page_header, section_title, striped_by_group
from src.views.common import _parse_stored_date


def render(proj) -> None:
    st.markdown(page_header(
        "세무조정 계산 및 검토",
        "규칙 엔진이 세무조정 항목을 자동 계산합니다. 회계사가 수치를 최종 확인하세요.",
    ), unsafe_allow_html=True)

    loader: SmartALoader = st.session_state.loader
    fy_start = _parse_stored_date(proj.company.fiscal_year_start, date.today())
    fy_end_val = _parse_stored_date(proj.company.fiscal_year_end, date.today())
    is_sme = proj.company.is_sme
    is_spec = proj.company.is_specified_corp
    # 사업연도 월수 (1개월 미만 일수는 1개월 — 영§50의2⑯)
    fy_months = max(
        1, (fy_end_val.year - fy_start.year) * 12 + fy_end_val.month - fy_start.month + 1
    )

    st.caption(
        "가지급금·수입배당금·간주임대료 등 필요자료는 3단계 수기 입력의 "
        "'세무조정 필요자료'에서 입력합니다."
    )
    _corp_flags = []
    _corp_flags.append("중소기업" if is_sme else "일반법인")
    if is_spec:
        _corp_flags.append("특정법인 (기업업무추진비 한도 50%·승용차 한도 축소)")
    if proj.company.is_rental_main:
        _corp_flags.append("부동산임대업 주업 (간주임대료 검토 대상)")
    st.caption(f"1단계 기본정보 반영: **{' · '.join(_corp_flags)}** · 사업연도 {fy_months}개월")
    # 법령 기준일 관리 — 어느 시점 법령으로 계산하는지 명시 (실무 필수)
    st.caption(
        f"⚖ 적용 사업연도 **{fy_start} ~ {fy_end_val}** · 법령 기준일 **{fy_end_val}** "
        f"(사업연도 종료일 시행, efYd) · 출처 국가법령정보센터 law.go.kr"
        + (f" · 마지막 법령 확인 {legal_basis.LAST_LAW_FETCH_OK}"
           if legal_basis.LAST_LAW_FETCH_OK else " · 법령 조회 실패 항목은 수기검토 필요")
    )

    # ── 당기순이익 사전 확인 — 세액 계산의 출발값. 못 읽으면 계산을 차단한다 ──
    # (자동 추정 폴백 없음 — 손익계산서 '당기순이익' 행만 신뢰, 그 외는 수기 확인)
    _auto_ni = loader.get_net_income()
    _manual_ni = 0
    _ni_zero_ok = False
    if _auto_ni != 0:
        st.caption(f"당기순이익 (손익계산서 자동 인식): **{_auto_ni:,}원**")
    else:
        st.error(
            "손익계산서에서 '당기순이익(또는 당기순손실)' 행을 찾지 못했습니다 — "
            "출발값이 없으면 소득금액·세액이 모두 틀어지므로 **자동 계산을 진행하지 않습니다**. "
            "손익계산서를 다시 업로드하거나 아래에 직접 입력하세요."
        )
        _manual_ni = int(st.number_input(
            "당기순이익 직접 입력 (원 — 순손실은 음수)",
            value=0, step=1_000_000, format="%d", key="manual_net_income",
        ))
        _ni_zero_ok = st.checkbox(
            "당기순이익이 실제로 0원임을 확인했습니다 (계산 진행)", key="ni_zero_confirm",
        )
    _ni_ready = (_auto_ni != 0) or (_manual_ni != 0) or _ni_zero_ok
    _net_income_input = _auto_ni if _auto_ni != 0 else _manual_ni

    col_btn, _ = st.columns([1, 4])
    with col_btn:
        if st.button("규칙 엔진 계산 실행", use_container_width=True, disabled=not _ni_ready):
            with st.spinner("세무조정 계산 중..."):
                result = TaxAdjustmentResult(
                    fiscal_year_start=fy_start,
                    fiscal_year_end=fy_end_val,
                    is_sme=is_sme,
                )

                depr_results = calc_depreciation_all(loader.fixed_assets)
                result.depreciation_excess  = sum(r.excess for r in depr_results)
                result.depreciation_approved = sum(r.approved for r in depr_results)

                # ── 분개장 집계 → 산식 (더존식: LLM 없이 계정·증빙 기준) ──
                agg = aggregate_journals(loader.journals)
                mi = proj.manual_input
                # 사업연도 일수 — 적수(積數) 계산용
                _fy_d = fy_days(fy_start, fy_end_val)

                # 계산 내역 (산식·분개장 근거) — 항목 선택 드릴다운용
                calc_details: dict[str, dict] = {}

                def _add_detail(name, amount, basis, formula, lines=None, reason=""):
                    """reason: '왜' 이 조정이 자동 발생했는지 — 판정 트리거(데이터 출처 + 조건)."""
                    if amount:
                        calc_details[name] = {
                            "금액": amount, "법령": basis,
                            "산식": formula, "lines": lines or [],
                            "사유": reason,
                        }

                revenue = (
                    loader.get_account_total("4")
                    or loader.get_amount_by_name(("매출액",))
                    or agg.revenue
                )
                # 특수관계인 거래 수입금액 — 매출 분개의 거래처를 특수관계인 목록과 대조
                _rp_kw = [
                    str(rp).split("(")[0].strip()
                    for rp in (mi.related_parties or []) if str(rp).strip()
                ]
                rp_revenue, rp_rev_lines = sum_related_party_revenue(loader.journals, _rp_kw)
                if agg.entertainment.total_expense > 0:
                    ent = calc_entertainment(
                        total_expense=agg.entertainment.total_expense,
                        card_expense=agg.entertainment.card_expense,
                        culture_expense=agg.entertainment.culture_expense,
                        traditional_expense=agg.entertainment.traditional_expense,
                        no_receipt_expense=agg.entertainment.no_receipt_expense,
                        revenue=revenue,
                        is_sme=is_sme,
                        is_specified_corp=is_spec,
                        months=fy_months,
                        related_revenue=rp_revenue,
                    )
                    result.entertainment_excess = ent.excess
                    result.entertainment_no_receipt = ent.no_receipt_disallowed
                    _ent_formula = [
                        f"기본한도 = {'3,600만' if is_sme else '1,200만'}원 × {fy_months}/12 = {ent.base_limit:,}원 (법§25④1호)",
                    ]
                    if ent.related_revenue > 0:
                        _ent_formula += [
                            f"일반 수입금액 {revenue - ent.related_revenue:,}원 × 적용률 = {ent.general_revenue_limit:,}원 (법§25④2호)",
                            f"특수관계인 수입금액 {ent.related_revenue:,}원 × 적용률 × 10% = {ent.related_revenue_limit:,}원 (법§25④2호 단서)",
                            f"수입금액한도 합계 = {ent.revenue_limit:,}원",
                        ]
                    else:
                        _ent_formula.append(
                            f"수입금액한도 = 수입금액 {revenue:,}원 × 적용률 = {ent.revenue_limit:,}원 (법§25④2호)"
                        )
                    if is_spec:
                        _ent_formula.append(
                            f"특정법인 → 한도 합계 × 50% = {(ent.base_limit + ent.revenue_limit) // 2:,}원 (법§25⑤)"
                        )
                    if ent.culture_limit or ent.traditional_limit:
                        _ent_formula.append(
                            f"문화비 한도 {ent.culture_limit:,}원 · 전통시장 한도 {ent.traditional_limit:,}원 추가"
                        )
                    _ent_formula += [
                        f"총한도 = {ent.total_limit:,}원",
                        f"지출액(증빙불비 제외) {ent.total_expense - ent.no_receipt_disallowed:,}원 − 총한도 = 한도초과 {ent.excess:,}원",
                    ]
                    _add_detail(
                        "기업업무추진비 한도초과", ent.excess, "법§25④·⑤",
                        _ent_formula, agg.detail_lines.get("기업업무추진비"),
                        reason="분개장에서 기업업무추진비 계정(8132·계정명 매칭)을 자동 집계한 결과, "
                               "지출 합계가 법§25④ 한도를 초과 → 초과분만 손금불산입"
                               + (f". 특수관계인 매출 {ent.related_revenue:,}원은 1단계 특수관계인 "
                                  f"목록과 매출 분개 거래처 대조로 자동 집계되어 한도 축소에 반영됨"
                                  if ent.related_revenue > 0 else ""),
                    )
                    if rp_revenue > 0:
                        _add_detail(
                            "(참고) 특수관계인 매출 집계", rp_revenue, "법§25④2호 단서",
                            ["세무조정 금액이 아닌 참고 집계 — 기업업무추진비 수입금액 한도에서 "
                             "이 금액의 적용률 산출액은 10%만 인정됩니다",
                             f"매출 분개 중 거래처가 특수관계인 목록({len(_rp_kw)}명)과 일치하는 "
                             f"{len(rp_rev_lines)}건 합계"],
                            rp_rev_lines,
                            reason="1단계 특수관계인 목록과 매출 분개의 거래처명을 자동 대조 — "
                                   "명단이 불완전하면 한도가 과대계산되므로 목록을 확인하세요",
                        )
                    _add_detail(
                        "기업업무추진비 증빙불비", ent.no_receipt_disallowed, "법§25②",
                        [f"건당 3만원 초과 + 적격증빙(카드·세금계산서 등) 미수취 → 전액 손금불산입",
                         f"해당 {len(agg.entertainment.no_receipt_lines)}건 합계 {ent.no_receipt_disallowed:,}원"],
                        agg.entertainment.no_receipt_lines,
                        reason="분개장의 증빙구분·카드번호 칸 기준으로 건당 3만원 초과인데 적격증빙이 "
                               "확인되지 않는 건만 추출 (카드번호가 있으면 증빙불비로 보지 않음)",
                    )

                result.penalty = calc_penalty(agg.penalty.total)
                _add_detail(
                    "벌과금·과태료·가산세", result.penalty, "법§21 3호",
                    [f"벌과금·과태료·가산세는 전액 손금불산입 — 분개장 {len(agg.penalty.lines)}건 합계 {result.penalty:,}원"],
                    agg.penalty.lines,
                    reason="분개장에서 벌과금 계정(8391) 또는 계정명·적요에 벌과금·과태료·가산세·범칙금이 "
                           "있는 분개 발견 → 법§21 3호에 따라 조건 없이 전액 손금불산입",
                )

                # ── 익금산입: 가지급금 인정이자 — 거래상대방별 적수(積數) 계산 ──
                # (법§52, 영§88①6호·③, 영§89③⑤ — 별지 제19호 구조)
                _rate = mi.related_loan_rate or get_prime_rate(fy_end_val.year)
                _rate_label = (
                    "가중평균차입이자율 (영§89③ 원칙)" if mi.related_loan_rate > 0
                    else "당좌대출이자율 (가중평균이자율 미입력 — 영§89③ 단서)"
                )
                _loan_checks = (mi.misc_line_checks or {}).get("related_loan_lines", {})
                _loan_lines = [
                    ln for ln in loader.journals
                    if _loan_checks.get(f"{ln.journal_id}|{ln.source_row}")
                ]
                _party_deltas: dict[str, list] = {}
                for ln in _loan_lines:
                    cp = (ln.counterparty_name or "").strip() or "(거래처 미기재)"
                    _party_deltas.setdefault(cp, []).append((ln.date, ln.debit - ln.credit))
                # 동일인 가수금 상계 — 적수 단계에서 일별 반영 (영§53③)
                for ln in loader.journals:
                    if not any(k in ln.account_name.replace(" ", "")
                               for k in ("가수금", "주임종단기차입")):
                        continue
                    cp = (ln.counterparty_name or "").strip()
                    if cp in _party_deltas:
                        _party_deltas[cp].append((ln.date, -(ln.credit - ln.debit)))
                # 약정이자 — 이자수익 분개에서 상대방별 자동 매칭
                _actual_by_cp: dict[str, int] = {}
                for ln in loader.journals:
                    nm = ln.account_name.replace(" ", "")
                    if "이자수익" not in nm and "이자수입" not in nm:
                        continue
                    cp = (ln.counterparty_name or "").strip()
                    if cp in _party_deltas:
                        _actual_by_cp[cp] = _actual_by_cp.get(cp, 0) + ln.credit

                _parties: list[tuple[str, int, int]] = [
                    (cp, jeoksu_from_deltas(deltas, fy_start, fy_end_val),
                     _actual_by_cp.get(cp, 0))
                    for cp, deltas in _party_deltas.items()
                ]
                if mi.related_loan_opening > 0:
                    _parties.append(
                        ("(기초이월분 — 상대방 미지정)", mi.related_loan_opening * _fy_d, 0)
                    )
                if not _parties and mi.related_loan_balance > 0:
                    # 분개 체크 없음 — 잔액 × 일수로 적수 근사 (단일 상대방 취급)
                    _parties = [("전체 (잔액 근사)",
                                 mi.related_loan_balance * _fy_d, mi.related_loan_interest)]

                _loan_jeoksu_total = sum(p[1] for p in _parties)
                if _parties:
                    dip = calc_deemed_interest_by_party(_parties, rate=_rate, days=_fy_d)
                    _incl = dip.inclusion_amount
                    # 수기 입력 약정이자 (상대방 미지정) — 합계에서 차감 (검토 표시)
                    if _loan_lines and mi.related_loan_interest > 0:
                        _incl = max(0, _incl - mi.related_loan_interest)
                    result.deemed_interest = _incl
                    _di_formula = [
                        f"적용 이자율 {_rate:.2%} ({_rate_label}) · 사업연도 {_fy_d}일",
                        "거래상대방별: 인정이자 = 가지급금 적수 × 이자율 ÷ 365 (영§89⑤) — "
                        "상대방 간 통산 없음, 동일인 가수금은 일별 적수에서 상계 (영§53③)",
                    ]
                    for p in dip.parties[:8]:
                        _di_formula.append(
                            f"· {p.name}: 적수 {p.jeoksu:,} → 인정이자 {p.deemed:,}원 − "
                            f"약정이자 {p.actual:,}원 = 차액 {p.diff:,}원 → "
                            + (f"익금산입 {p.inclusion:,}원"
                               if p.applied else "적용 제외 (영§88③: 차액 3억 미만이고 시가의 5% 미만)")
                        )
                    if len(dip.parties) > 8:
                        _di_formula.append(f"· 외 {len(dip.parties) - 8}명")
                    if _loan_lines and mi.related_loan_interest > 0:
                        _di_formula.append(
                            f"수기 입력 약정이자 {mi.related_loan_interest:,}원 차감 "
                            f"(상대방 미지정 — 상대방별 귀속 확인 필요)"
                        )
                    _di_formula.append(f"익금산입 합계 = {result.deemed_interest:,}원")
                    _add_detail(
                        "가지급금 인정이자", result.deemed_interest,
                        "법§52, 영§88①6호·③, 영§89③⑤",
                        _di_formula,
                        agg.detail_lines.get("가지급금·대여금"),
                        reason="3단계에서 체크한 가지급금·대여금 분개의 거래 날짜로 거래상대방별 "
                               "일별 적수를 계산 (1단계 특수관계인 목록 기준 추천) — 약정이자는 "
                               "이자수익 분개의 거래처로 자동 매칭. 영§88③ 기준(차액 3억 또는 시가 5%) "
                               "미달 상대방은 제외",
                    )

                # ── 차입금 적수 — 분개장 일별 계산 (4호 지급이자·간주임대료 공용) ──
                _debt_kw = ("단기차입금", "장기차입금", "유동성장기부채")
                _debt_open = _bs_amount_detail(loader, _debt_kw, column="기초잔액")[0]
                _debt_jeoksu = account_jeoksu(
                    loader.journals, _debt_kw, fy_start, fy_end_val,
                    opening=_debt_open, debit_positive=False,
                )
                _debt_jeoksu_src = "분개장 일별 계산 (기초잔액 + 당기 증감)"
                if _debt_jeoksu <= 0:
                    _debt_jeoksu = (mi.rental_debt or _bs_amount(loader, _debt_kw)) * _fy_d
                    _debt_jeoksu_src = "기말잔액 × 일수 근사 (분개장에 차입금 변동 없음)"

                # ── 익금산입: 간주임대료 (조특법§138, 조특령§132 — 전 항목 적수 기준) ──
                if mi.rental_deposit > 0:
                    # 임대보증금 적수 — B/S 기초잔액 + 분개장 당기 증감 일별 계산
                    _dep_kw = ("임대보증금", "전세보증금")
                    _dep_open = _bs_amount_detail(loader, _dep_kw, column="기초잔액")[0]
                    _dep_jeoksu = account_jeoksu(
                        loader.journals, _dep_kw, fy_start, fy_end_val,
                        opening=_dep_open, debit_positive=False,
                    )
                    _dep_src = "분개장 일별 계산 (기초잔액 + 당기 증감)"
                    if _dep_jeoksu <= 0:
                        _dep_jeoksu = mi.rental_deposit * _fy_d
                        _dep_src = "기말잔액 × 일수 근사"

                    # 건설비상당액 적수 — 건물·구축물 계정(취득가액)의 일별 적수에
                    # 임대용 비율(입력 건설비 ÷ 기말 건물가액)을 곱해 산정 (조특령§132⑥, 칙§59)
                    _con_kw = ("건물", "구축물")
                    _con_close = _bs_amount(loader, _con_kw)
                    _con_open = _bs_amount_detail(loader, _con_kw, column="기초잔액")[0]
                    _bld_jeoksu = account_jeoksu(
                        loader.journals, _con_kw, fy_start, fy_end_val,
                        opening=_con_open, debit_positive=True,
                    )
                    if (_bld_jeoksu > 0 and _con_close > 0
                            and 0 < mi.rental_construction_cost):
                        _rent_ratio = min(1.0, mi.rental_construction_cost / _con_close)
                        _con_jeoksu = int(_bld_jeoksu * _rent_ratio)
                        _con_src = (f"건물·구축물 분개 일별 계산 × 임대용 비율 {_rent_ratio:.1%} "
                                    f"(입력 건설비 ÷ 기말 건물가액 {_con_close:,}원)")
                    else:
                        _con_jeoksu = mi.rental_construction_cost * _fy_d
                        _con_src = "입력 잔액 × 일수 근사"

                    dr = calc_deemed_rental(
                        deposit=mi.rental_deposit,
                        debt=mi.rental_debt,
                        equity=mi.rental_equity,
                        bank_rate=mi.rental_bank_rate,
                        is_rental_main=proj.company.is_rental_main,
                        construction_cost=mi.rental_construction_cost,
                        financial_income=mi.rental_financial_income,
                        deposit_jeoksu=_dep_jeoksu,
                        debt_jeoksu=_debt_jeoksu,
                        construction_jeoksu=_con_jeoksu,
                        days=_fy_d,
                    )
                    result.deemed_rental = dr.inclusion_amount
                    if dr.applicable:
                        _add_detail(
                            "간주임대료", dr.inclusion_amount, "조특법§138, 조특령§132⑤",
                            [f"적용 요건: {dr.reason}",
                             f"임대보증금 적수 {_dep_jeoksu:,} ← {_dep_src}",
                             f"건설비상당액 적수 {_con_jeoksu:,} ← {_con_src}",
                             f"(보증금 적수 − 건설비 적수) × 1/{_fy_d} × 정기예금이자율 {dr.bank_rate:.1%} = {int(max(0, _dep_jeoksu - _con_jeoksu) * dr.bank_rate / _fy_d):,}원",
                             f"− 보증금 운용 금융수익 {dr.financial_income:,}원 = 익금가산 {dr.inclusion_amount:,}원 (음수면 0)",
                             f"적용 요건 검토: 차입금 적수 {_debt_jeoksu:,} ({_debt_jeoksu_src}) > 자기자본 적수 {mi.rental_equity * _fy_d:,} (기말 × 일수 근사) × 2"],
                            reason="1단계 기본정보에서 부동산임대업 주업으로 판정 + 차입금 적수가 자기자본 적수의 "
                                   "2배 초과 (조특령§132①) — 보증금·건설비·차입금 적수 모두 업로드 재무제표"
                                   "(분개장 거래 날짜 + B/S 기초잔액)로 일별 계산",
                        )
                    else:
                        st.info(f"간주임대료 미적용 — {dr.reason}")

                # ── 익금불산입: 수입배당금 (법인세법 §18의2) ──
                div_income = agg.dividend_income or loader.get_account_total("711")
                if div_income > 0:
                    _divr = calc_dividend_exclusion(
                        dividend_income=div_income,
                        ownership_ratio=mi.dividend_ownership_ratio,
                    )
                    result.dividend_exclusion = _divr.exclusion_amount
                    _add_detail(
                        "수입배당금 익금불산입", _divr.exclusion_amount, "법§18의2①",
                        [f"수입배당금 {_divr.dividend_income:,}원 × 익금불산입률 {_divr.exclusion_rate:.0%} (출자비율 {_divr.ownership_ratio:.1%}) = {_divr.exclusion_amount:,}원"],
                        agg.detail_lines.get("수입배당금"),
                        reason="분개장에서 배당금수익 계정(711) 대변 발견 + 3단계 입력 출자비율로 "
                               "익금불산입률 구간 결정",
                    )

                # ── 수기 입력 필요자료 기반 자동 조정 ──────────────────────

                # 법인세비용 — 전액 손금불산입 (법§21 1호, 입력 불필요·자동)
                result.corporate_tax_expense = max(0, agg.corporate_tax)
                _add_detail(
                    "법인세비용", result.corporate_tax_expense, "법§21 1호",
                    ["법인세·법인지방소득세 비용은 전액 손금불산입 — 분개장 차변 집계 (결산 마감분개 제외)"],
                    agg.detail_lines.get("법인세비용"),
                    reason="분개장에서 법인세비용 계정(998·계정명 매칭) 차변 발생 → "
                           "법§21 1호에 따라 조건 없이 항상 전액 손금불산입 (입력 불필요 자동 항목)",
                )

                # 외화환산손익 — 평가방법 미신고 시 평가손익 부인 (법§42③, 영§76)
                if not mi.forex_method_reported:
                    result.forex_loss_disallowed = agg.forex_eval_loss
                    result.forex_gain_excluded = agg.forex_eval_gain
                    _fx_note = "마감환율 평가방법 미신고 (3단계 수기 입력) → 평가손익 전액 부인"
                    _fx_why = ("3단계 수기 입력에서 '마감환율 평가방법 신고함'이 체크되지 않음 → "
                               "미신고 법인의 외화 평가손익은 세법상 미실현손익으로 부인 (신고했다면 3단계에서 체크)")
                    _add_detail("외화환산손실 부인", agg.forex_eval_loss, "법§42③, 영§76",
                                [_fx_note], agg.detail_lines.get("외화환산손실"), reason=_fx_why)
                    _add_detail("외화환산이익 익금불산입", agg.forex_eval_gain, "법§42③, 영§76",
                                [_fx_note], agg.detail_lines.get("외화환산이익"), reason=_fx_why)

                # 통화선도 등 파생상품 평가손익 (영§76)
                if not mi.derivative_hedge_reported:
                    result.derivative_loss_disallowed = agg.derivative_eval_loss
                    result.derivative_gain_excluded = agg.derivative_eval_gain
                    _dv_note = "통화선도 등 평가방법 미신고 → 평가손익 전액 부인 (영§76)"
                    _dv_why = ("3단계 수기 입력에서 '파생상품 평가방법 신고함'이 체크되지 않음 → "
                               "평가손익(미실현) 부인. 거래·정산 실현손익은 집계에서 제외되어 있음")
                    _add_detail("파생상품 평가손실 부인", agg.derivative_eval_loss, "영§76",
                                [_dv_note], agg.detail_lines.get("파생상품 평가손실"), reason=_dv_why)
                    _add_detail("파생상품 평가이익 익금불산입", agg.derivative_eval_gain, "영§76",
                                [_dv_note], agg.detail_lines.get("파생상품 평가이익"), reason=_dv_why)

                # 유가증권 평가손익 — 일반법인 원가법 강제, 전액 부인 (영§75)
                result.securities_loss_disallowed = agg.securities_eval_loss
                result.securities_gain_excluded = agg.securities_eval_gain
                _sec_note = "일반법인 유가증권은 원가법만 인정 → 평가손익 전액 부인 (영§75①)"
                _sec_why = ("분개장에서 유가증권·금융자산 평가손익 계정 발견 → 일반법인은 원가법이 "
                            "강제되므로 입력과 무관하게 항상 부인 (유보로 처분 후 처분 시 추인)")
                _add_detail("유가증권 평가손실 부인", agg.securities_eval_loss, "영§75",
                            [_sec_note], agg.detail_lines.get("유가증권 평가손실"), reason=_sec_why)
                _add_detail("유가증권 평가이익 익금불산입", agg.securities_eval_gain, "영§75",
                            [_sec_note], agg.detail_lines.get("유가증권 평가이익"), reason=_sec_why)

                # 재고자산 평가 조정 및 기타 손금불산입 (수기 입력)
                result.inventory_adjustment = mi.inventory_valuation_adjustment
                result.welfare_disallowed = mi.welfare_disallowed
                result.joint_expense_excess = mi.joint_expense_excess
                result.non_business_expense = mi.non_business_expense
                result.punitive_damages = mi.punitive_damages
                _manual_src = "근거 자료: 3단계 수기 입력의 분개 체크 내역"
                _manual_why = "3단계 수기 입력에서 해당 분개를 직접 체크·분류함 (자동 추출 아님 — 사용자 판단 반영)"
                _add_detail("재고자산 평가 조정", mi.inventory_valuation_adjustment, "영§74",
                            ["신고 평가방법과 장부 적용방법 불일치 → 세법상 재계산 차액 (무신고 시 선입선출법)", _manual_src],
                            reason="3단계 재고자산 평가방법 입력에서 ①신고방법과 ②장부방법이 불일치 (또는 무신고)")
                _add_detail("복리후생비 (열거 외)", mi.welfare_disallowed, "영§45",
                            ["영§45① 열거 항목 외 복리후생비 → 전액 손금불산입", _manual_src],
                            reason=_manual_why)
                _add_detail("공동경비 분담 초과", mi.joint_expense_excess, "영§48",
                            [f"부담액 − (공동경비 총액 {mi.joint_total_pool:,}원 × 분담비율 {mi.joint_share_ratio:.1%}) = 초과분 {mi.joint_expense_excess:,}원", _manual_src],
                            reason="3단계에서 공동경비 분개 체크 + 총액·분담비율 입력 → 분담기준 초과분만 손금불산입")
                _add_detail("업무무관비용", mi.non_business_expense, "법§27",
                            ["업무와 관련 없는 자산·지출 비용 → 전액 손금불산입", _manual_src],
                            reason=_manual_why)
                _add_detail("징벌적 손해배상금", mi.punitive_damages, "법§21의2, 영§23",
                            [("실손해액 분명 → 지급액 − 실손해액 " + f"{mi.punitive_actual_amount:,}원" )
                             if mi.punitive_actual_known else "실손해액 불분명 → 지급액 × 2/3 (영§23②)",
                             _manual_src],
                            reason="3단계에서 손해배상 분개 체크 + 실손해액 분명 여부 선택")

                # 임원 상여 한도초과 (법§26, 영§43)
                if mi.officer_bonus_paid > 0:
                    result.officer_bonus_excess = calc_officer_bonus_excess(
                        paid_bonus=mi.officer_bonus_paid,
                        approved_limit=mi.officer_bonus_limit,
                    )
                    _add_detail("임원 상여금 한도초과", result.officer_bonus_excess, "영§43②",
                                [f"지급액 {mi.officer_bonus_paid:,}원 − 정관·주총 한도 {mi.officer_bonus_limit:,}원 = {result.officer_bonus_excess:,}원",
                                 "근거 자료: 3단계 수기 입력 (임원 명단·한도)"],
                                reason="3단계에서 임원으로 선택한 거래처의 상여 계정 분개를 자동 합산 "
                                       "(출처 계정과목·집계 내역은 3단계 임원 인건비 화면에 표시) — 입력 한도 초과분")

                # 임원 퇴직금 한도초과 (법§26, 영§44)
                if mi.officer_retirement_paid > 0 and mi.officer_retirement_last_salary > 0:
                    result.officer_retirement_excess = calc_officer_retirement_excess(
                        paid_amount=mi.officer_retirement_paid,
                        tenure_years=mi.officer_retirement_tenure,
                        last_salary=mi.officer_retirement_last_salary,
                    )
                    _add_detail("임원 퇴직금 한도초과", result.officer_retirement_excess, "영§44④",
                                [f"한도 = 직전 1년 총급여 {mi.officer_retirement_last_salary:,}원 × 10% × 근속 {mi.officer_retirement_tenure}년",
                                 f"지급액 {mi.officer_retirement_paid:,}원 − 한도 = {result.officer_retirement_excess:,}원"],
                                reason="3단계에서 임원으로 선택한 거래처의 퇴직급여 계정 분개를 자동 합산 — "
                                       "정관 규정 없을 때의 법정 한도(총급여×10%×근속) 초과분")

                # 업무용승용차 (법§27의2, 영§50의2) — 차량별 한도 적용 (800만·1,500만은 차량 단위)
                if agg.vehicle_expense > 0 or mi.vehicle_depreciation > 0:
                    # 3단계에서 '업무용승용차 해당'으로 체크된 차량운반구 자산
                    _veh_assets = [
                        a for a in loader.fixed_assets
                        if mi.vehicle_asset_checks.get(a.asset_code)
                    ]
                    _veh_results = []
                    if _veh_assets:
                        # 차량유지비(기타비용)는 분개장에 차량별 미구분 → 감가상각비 비율로 안분(근사).
                        # (감가상각비 합계가 0이면 균등 안분)
                        _depr_sum = sum(a.company_depr for a in _veh_assets)
                        _n = len(_veh_assets)
                        for a in _veh_assets:
                            if _depr_sum > 0:
                                _alloc_other = int(agg.vehicle_expense * a.company_depr / _depr_sum)
                            else:
                                _alloc_other = int(agg.vehicle_expense / _n)
                            _veh_results.append(calc_vehicle(
                                vehicle_id=a.asset_name or a.asset_code,
                                depreciation=a.company_depr,
                                other_expense=_alloc_other,
                                business_use_ratio=mi.vehicle_business_ratio,
                                has_insurance=mi.vehicle_has_insurance,
                                has_logbook=mi.vehicle_has_logbook,
                                is_specified_corp=is_spec,
                                months=fy_months,
                            ))
                    else:
                        # 고정자산대장 미업로드 → 단일 합산(차량 1대로 간주, 한도 풀링 주의)
                        _veh_results.append(calc_vehicle(
                            vehicle_id="전체(자산대장 없음)",
                            depreciation=mi.vehicle_depreciation,
                            other_expense=agg.vehicle_expense,
                            business_use_ratio=mi.vehicle_business_ratio,
                            has_insurance=mi.vehicle_has_insurance,
                            has_logbook=mi.vehicle_has_logbook,
                            is_specified_corp=is_spec,
                            months=fy_months,
                        ))
                    result.vehicle_disallowed = sum(v.total_disallowed for v in _veh_results)

                    _limit_label = "특정법인 400만원, 영§50의2⑮" if is_spec else "800만원"
                    _veh_formula = [
                        f"차량별 한도 적용 (영§50의2 — 감가상각 {_limit_label}·운행기록부 미작성 한도는 차량 단위)",
                    ]
                    if not mi.vehicle_has_insurance:
                        _veh_formula.append(
                            "⚠ 업무전용보험 미가입 → 해당 차량 관련비용 전액 손금불산입 (영§50의2④1호). "
                            "보험 가입 여부는 차량별로 다를 수 있으니 3단계에서 확인하세요"
                        )
                    for v in _veh_results:
                        _rel = v.depreciation + v.other_expense
                        if not v.has_insurance:
                            _line = f"· {v.vehicle_id}: 관련비용 {_rel:,}원 전액 손금불산입 (보험 미가입)"
                        else:
                            _ratio_src = "입력값" if v.has_logbook else f"min(1, 한도 {v.no_logbook_limit:,}÷관련비용)"
                            _line = (f"· {v.vehicle_id}: 관련비용 {_rel:,}원 "
                                     f"(상각 {v.depreciation:,} + 기타 {v.other_expense:,}, 기타는 상각비율 안분) · "
                                     f"업무사용 {v.business_use_ratio:.0%} [{_ratio_src}] · "
                                     f"개인사용 부인 {v.personal_use_disallowed:,} + 상각한도초과 {v.depreciation_limit_excess:,}")
                        _veh_formula.append(_line)
                    _veh_formula.append(
                        f"합계 손금불산입 {result.vehicle_disallowed:,}원 "
                        "(상각한도초과분은 유보·이월, 개인사용분은 사외유출)"
                    )
                    _veh_formula.append(
                        "※ 차량유지비는 분개장에 차량별로 구분되지 않아 감가상각비 비율로 안분함 — "
                        "차량별 실제 유지비·보험 가입이 다르면 3단계에서 보정"
                    )
                    _add_detail("업무용승용차 관련비용", result.vehicle_disallowed, "법§27의2, 영§50의2",
                                _veh_formula, agg.detail_lines.get("업무용승용차 관련비용"),
                                reason="3단계에서 업무용승용차로 체크한 차량운반구 자산별로 영§50의2 한도를 "
                                       "각각 적용(한도 풀링 방지). 보험·운행기록부·업무사용비율은 3단계 입력 적용. "
                                       "증빙불비 판정이 아니라 업무사용비율·한도 조정입니다")

                # 지급이자 손금불산입 (법§28) — 직접 입력 금액
                result.interest_unknown_creditor = mi.interest_unknown_creditor
                result.interest_construction = mi.interest_construction
                _add_detail("채권자불분명 사채이자", mi.interest_unknown_creditor, "법§28①1호",
                            ["채권자가 불분명한 사채의 이자 → 전액 손금불산입 (원천세 상당액 외 대표자 상여 처분)",
                             "근거 자료: 3단계 지급이자 분류 표에서 '채권자불분명'으로 분류된 분개 합계"],
                            reason="3단계에서 이자비용 전체 중 '채권자불분명'으로 분류한 라인 합계 — "
                                   "나머지 일반 이자비용은 조정 없이 손금 인정")
                _add_detail("건설자금이자", mi.interest_construction, "법§28①3호, 영§52",
                            ["사업용 유형자산 건설에 충당한 차입금 이자 → 손금불산입 (자본화, 유보)",
                             "근거 자료: 3단계 지급이자 분류 표에서 '건설자금이자'로 분류된 분개 합계"],
                            reason="3단계에서 이자비용 전체 중 '건설자금이자'로 분류한 라인 합계 — "
                                   "나머지 일반 이자비용은 조정 없이 손금 인정")

                # 업무무관자산 지급이자 (법§28①4호, 영§53②③ — 적수 기준)
                # 분자 적수 = 업무무관자산 적수(가목, 영§49) + 특수관계인 가지급금 적수(나목, 영§53①)
                # 업무무관자산 적수 — 체크된 계정별로 B/S 기초잔액 + 분개장 당기 증감 일별 계산
                _nonbiz_jeoksu = 0
                _nonbiz_jeoksu_src = []
                for _nba in (mi.non_business_assets or []):
                    _nba_kw = (str(_nba.get("계정명", "")).replace(" ", ""),)
                    if not _nba_kw[0]:
                        continue
                    _nba_open = _bs_amount_detail(loader, _nba_kw, column="기초잔액")[0]
                    _nba_j = account_jeoksu(
                        loader.journals, _nba_kw, fy_start, fy_end_val,
                        opening=_nba_open, debit_positive=True,
                    )
                    if _nba_j > 0:
                        _nonbiz_jeoksu += _nba_j
                        _nonbiz_jeoksu_src.append(f"{_nba_kw[0]}: 일별 계산 {_nba_j:,}")
                    else:
                        _nba_fallback = int(_nba.get("금액", 0)) * _fy_d
                        _nonbiz_jeoksu += _nba_fallback
                        _nonbiz_jeoksu_src.append(f"{_nba_kw[0]}: 기말×일수 근사 {_nba_fallback:,}")
                if _nonbiz_jeoksu == 0:
                    _nonbiz_jeoksu = mi.non_business_asset_balance * _fy_d
                _nb_numer_j = _nonbiz_jeoksu + _loan_jeoksu_total
                if _nb_numer_j > 0 and agg.interest_expense > 0:
                    if _debt_jeoksu > 0:
                        _base_int = max(
                            0, agg.interest_expense
                            - mi.interest_unknown_creditor - mi.interest_construction
                        )
                        _nb_ratio = min(1.0, _nb_numer_j / _debt_jeoksu)
                        result.interest_non_business = int(_base_int * _nb_ratio)
                        _nb_names = ", ".join(
                            f"{d.get('계정명')}({d.get('금액', 0):,})"
                            for d in (mi.non_business_assets or [])[:5]
                        )
                        _add_detail(
                            "업무무관자산 지급이자", result.interest_non_business,
                            "법§28①4호, 영§53②③",
                            [f"기준 지급이자 = 이자비용 총액 {agg.interest_expense:,}원 − 채권자불분명 {mi.interest_unknown_creditor:,}원 − 건설자금 {mi.interest_construction:,}원 = {_base_int:,}원",
                             f"분자 적수 = 업무무관자산 적수 {_nonbiz_jeoksu:,} (가목·영§49 — " + ("; ".join(_nonbiz_jeoksu_src[:4]) or f"잔액 × {_fy_d}일") + ") + 가지급금 적수 " + f"{_loan_jeoksu_total:,} (분개장 일별 계산·가수금 상계 후, 나목·영§53①)",
                             f"비율 = min(1, 분자 적수 {_nb_numer_j:,} ÷ 차입금 적수 {_debt_jeoksu:,}) = {_nb_ratio:.1%} ({_debt_jeoksu_src})",
                             f"손금불산입 = {_base_int:,}원 × {_nb_ratio:.1%} = {result.interest_non_business:,}원",
                             f"체크된 업무무관자산: {_nb_names}" if _nb_names else "",
                             "※ 적수는 분개장 거래 날짜 기준 일별 계산 (영§53③ — 동일인 가수금 상계 적용)"],
                            agg.detail_lines.get("이자비용"),
                            reason="3단계에서 업무무관자산 체크(계정별 명세) + 특수관계인 가지급금 체크(분개장)의 "
                                   "적수 비율만큼 지급이자 손금불산입 — 가지급금은 인정이자와 동시 적용됨 (별개 조정)",
                        )
                    else:
                        st.info(
                            "업무무관자산·가지급금이 체크되었으나 차입금 적수를 계산하지 못해 "
                            "지급이자 손금불산입(법§28①4호)을 계산하지 못했습니다 — "
                            "계정별명세서·재무상태표 업로드 또는 3단계 간주임대료 차입금 입력 후 재계산하세요."
                        )

                # 부당행위계산 부인 (법§52, 영§88·89⑤) — 시가 차액은 수기 산정
                result.unfair_transaction = mi.unfair_transaction_amount
                _add_detail(
                    "부당행위계산 부인", mi.unfair_transaction_amount, "법§52, 영§88, 영§89⑤",
                    ["고가매입·저가양도 등 시가와의 차액 익금산입 (영§89⑤)",
                     "적용 기준: 차액 ≥ 3억원 또는 시가의 5% 이상 (영§88③ — 상장주식 거래 제외)",
                     "금전 대여(영§88①6호)는 가지급금 인정이자에서 자동 계산 — 중복 아님",
                     "근거 자료: 3단계 '부당행위계산 부인' 입력 (특수관계인 거래 분개 참고 표 제공)"],
                    reason="3단계에서 특수관계인 거래 검토 후 시가 차액을 직접 입력함 — "
                           "시가(감정가액·상증법 평가)는 자동 산정 불가",
                )

                # 기부금 한도(법§24)는 다른 모든 세무조정 후 차가감소득금액 기준으로
                # 계산해야 하므로 충당금 계산 뒤로 이동했다 (아래 참조).

                st.session_state.journal_aggregates = agg
                st.session_state.depr_results = depr_results

                # ── 세무조정 전수 검토 체크리스트 (완전성 확보) ──
                _auto_items = {
                    "감가상각비 시부인", "기업업무추진비 한도·증빙",
                    "퇴직급여충당금·퇴직연금", "대손충당금·대손금",
                    "벌과금·과태료·가산세",
                    "법인세비용 손금불산입",      # 분개장 집계로 항상 자동
                    "외화자산·부채 평가손익",     # 신고 여부 입력에 따라 자동 반영
                    "통화선도 등 파생상품 평가손익",
                    "업무용승용차 관련비용",      # 분개장 집계 + 수기 입력으로 계산
                }
                if result.deemed_interest > 0:
                    _auto_items.add("가지급금 인정이자")
                if result.unfair_transaction > 0:
                    _auto_items.add("부당행위계산 부인 검토")
                if mi.rental_deposit > 0:
                    _auto_items.add("간주임대료")
                if div_income > 0:
                    _auto_items.add("수입배당금 익금불산입")
                if mi.officer_bonus_paid > 0:
                    _auto_items.add("임원 상여금 한도")
                if mi.officer_retirement_paid > 0:
                    _auto_items.add("임원 퇴직급여 한도")
                if (mi.interest_unknown_creditor or mi.interest_construction
                        or result.interest_non_business):
                    _auto_items.add("지급이자 손금불산입")
                if mi.donation_special or mi.donation_general or mi.donation_nondesignated:
                    _auto_items.add("기부금 한도")
                _auto_items.add("유가증권 평가손익")  # 분개장 집계로 항상 자동
                if mi.inventory_valuation_adjustment:
                    _auto_items.add("재고자산 평가")
                if mi.welfare_disallowed:
                    _auto_items.add("복리후생비 (열거 외 항목)")
                if mi.joint_expense_excess:
                    _auto_items.add("공동경비 분담 초과")
                if mi.non_business_expense:
                    _auto_items.add("업무무관비용")
                if mi.punitive_damages:
                    _auto_items.add("징벌적 손해배상금")
                st.session_state.coverage_results = run_coverage_check(
                    loader.journals, _auto_items,
                )

                # 충당금 회사계상액은 분개장에서 자동 집계 (당기 설정 대변 합계)
                rall = calc_retirement_allowance(
                    company_balance=agg.pension_provision,
                    pension_asset=proj.manual_input.pension_db_asset,
                )
                result.pension_excess = rall.excess
                _add_detail("퇴직급여충당금 한도초과", rall.excess, "법§33, 영§60",
                            [f"회사계상액(당기 전입) {rall.company_balance:,}원 − 세법 한도 {rall.statutory_limit:,}원 (현행 누적한도 0%) = {rall.excess:,}원"],
                            agg.detail_lines.get("퇴직급여충당금 설정"),
                            reason="분개장에서 퇴직급여충당부채 대변(당기 전입) 자동 집계 — "
                                   "현행 영§60 한도가 0%이므로 설정액 전액이 한도초과 (퇴직연금 부담금 손금산입은 아래에서 별도 계산)")

                # 확정급여형(DB) 퇴직연금 부담금 손금산입 — 영§44의2④ (추계액 한도 방식)
                pdr = calc_pension_deduction(
                    estimate=mi.retirement_estimate,
                    fund_balance=mi.pension_db_asset,
                    prior_deducted=mi.prior_pension_deducted,
                )
                result.pension_deduction = pdr.deduction
                _add_detail("퇴직연금 부담금 손금산입", pdr.deduction, "영§44의2④",
                            [f"추계액 기준 한도 = 추계액 {pdr.estimate:,}원 − 세무상 퇴직급여충당금 {pdr.tax_provision_balance:,}원 = {pdr.estimate_limit:,}원 (영§44의2④1호)",
                             f"예치금 기준 한도 = 퇴직연금 운용자산 {pdr.fund_balance:,}원",
                             f"손금산입 한도 = min(추계액 한도, 예치금) = {pdr.ceiling:,}원",
                             f"당기 손금산입 = 한도 {pdr.ceiling:,}원 − 직전까지 손금산입 누계 {pdr.prior_deducted:,}원 (영§44의2④2호) = {pdr.deduction:,}원"],
                            reason="3단계 입력(퇴직급여추계액·DB 운용자산·직전 손금누계) 기준으로 "
                                   "확정급여형 퇴직연금 부담금을 영§44의2④ 한도 내에서 손금산입(△유보). "
                                   "확정기여형(DC) 부담금은 영§44의2③ 전액 손금 — 별도 검토")

                bdall = calc_bad_debt_allowance(
                    receivable_balance=proj.manual_input.receivable_balance,
                    actual_bad_rate=proj.manual_input.actual_bad_debt_rate,
                    company_balance=agg.bad_debt_provision,
                )
                result.bad_debt_excess = bdall.excess
                _add_detail("대손충당금 한도초과", bdall.excess, "법§34, 영§61",
                            [f"한도 = 채권잔액 {bdall.receivable_balance:,}원 × max(1%, 대손실적률 {bdall.actual_bad_rate:.2%}) = {bdall.limit:,}원",
                             f"회사계상액 {bdall.company_balance:,}원 − 한도 = {bdall.excess:,}원"],
                            agg.detail_lines.get("대손충당금 설정"),
                            reason="분개장에서 대손충당금 대변(당기 설정) 자동 집계 + 3단계 입력 채권잔액·"
                                   "대손실적률로 한도 계산 — 한도 초과분만 손금불산입")

                # ── 기부금 한도 (법§24②2호·③2호) — 모든 조정 후 차가감소득금액 기준 ──
                _carryforward_pairs = [
                    (item["year"], item["amount"])
                    for item in mi.carryforward_losses
                    if item.get("year") and item.get("amount")
                ]
                _don_special, _don_general = mi.donation_special, mi.donation_general
                _don_nondes = mi.donation_nondesignated
                if (_don_special + _don_general + _don_nondes) > 0:
                    # 기준소득금액 = 차가감소득금액 + 특례 + 일반기부금 (비지정 제외)
                    #   차가감소득금액 = 당기순이익 + (기부금 외 가산조정) − 차감조정
                    # ── 순서 의존성: 기부금은 다른 모든 조정 후에 계산해야 한다.
                    #    이 시점 donation_excess=0 이어야 total_add_back이 기부금 제외분이 됨.
                    #    신규 가산/차감조정을 이 블록 '뒤'에 추가하면 base에서 누락되므로 금지.
                    assert result.donation_excess == 0, "기부금은 다른 조정 후 마지막에 계산"
                    _base_income = max(
                        0,
                        _net_income_input + result.total_add_back - result.total_deduct
                        + _don_special + _don_general,
                    )
                    # 법§13①1호 이월결손금 공제액 (한도 base에서 차감) — 공제율은 과세표준과 단일 상수 공유
                    _loss_rate = LOSS_CARRYFORWARD_SME_RATE if is_sme else LOSS_CARRYFORWARD_GENERAL_RATE
                    _cf_loss_ded = min(
                        eligible_carryforward_total(_carryforward_pairs, fy_end_val),
                        int(_base_income * _loss_rate),
                    )
                    _don = calc_donation(
                        special_donation=_don_special,
                        general_donation=_don_general,
                        nondesignated_donation=_don_nondes,
                        adjusted_income=_base_income,
                        carryforward_loss_deduction=_cf_loss_ded,
                    )
                    result.donation_excess = _don.total_disallowed
                    _add_detail("기부금 한도초과·비지정", _don.total_disallowed, "법§24",
                                [f"기준소득금액 = 차가감소득금액 + 특례·일반기부금 = {_base_income:,}원 "
                                 f"(당기순이익 {_net_income_input:,} + 가산조정 {result.total_add_back:,} "
                                 f"− 차감조정 {result.total_deduct:,} + 기부금 {_don_special + _don_general:,})",
                                 f"이월결손금 공제 {_cf_loss_ded:,}원 차감 → 한도기준 {max(0, _base_income - _cf_loss_ded):,}원",
                                 f"특례기부금 {_don_special:,}원 (한도 50% = {_don.special_limit:,}원) · "
                                 f"일반기부금 {_don_general:,}원 (한도 10% = {_don.general_limit:,}원)",
                                 f"비지정기부금 {_don_nondes:,}원 → 전액 손금불산입",
                                 "근거: 3단계 수기 입력의 기부금 분류 (법§24②2호·③2호)"],
                                reason="기부금 한도는 다른 모든 세무조정 후 차가감소득금액에 특례·일반기부금을 "
                                       "가산한 기준소득금액에서 이월결손금을 차감해 계산 — 분류별 한도초과분 + 비지정 전액")

                st.session_state.calc_details = calc_details
                st.session_state.tax_result = result

            # 이월결손금 쌍은 기부금 한도 계산과 동일 소스 사용 (위 _carryforward_pairs)
            carryforward = _carryforward_pairs
            # 출발값은 사전 확인된 값 사용 (자동 인식 또는 수기 입력 — 0원은 명시적 확인 시만)
            net_income = _net_income_input
            if _auto_ni == 0 and _manual_ni != 0:
                st.info(f"당기순이익 수기 입력값 {_manual_ni:,}원으로 계산했습니다 — 검토조서에 출처를 기록하세요.")
            compute_all(
                result,
                net_income=net_income,
                carryforward_losses=carryforward,
                fiscal_year_end=fy_end_val,
                tax_credits=[],
            )

            # ── 차기 승계용 결과 저장 (.taxproj에 포함 → 내년 '전년도 자료 불러오기') ──
            _depr_list = st.session_state.get("depr_results") or []
            _new_reserves = [
                {"code": nm, "amount": amt, "disposition": disp}
                for nm, amt, disp in [
                    ("감가상각 부인누계", sum(d.denial_end for d in _depr_list), "유보"),
                    ("퇴직급여충당금 한도초과", result.pension_excess, "유보"),
                    ("대손충당금 한도초과", result.bad_debt_excess, "유보"),
                    ("외화환산손실 부인", result.forex_loss_disallowed, "유보"),
                    ("외화환산이익 익금불산입", result.forex_gain_excluded, "△유보"),
                    ("파생상품 평가손실 부인", result.derivative_loss_disallowed, "유보"),
                    ("파생상품 평가이익 익금불산입", result.derivative_gain_excluded, "△유보"),
                    ("유가증권 평가손실 부인", result.securities_loss_disallowed, "유보"),
                    ("유가증권 평가이익 익금불산입", result.securities_gain_excluded, "△유보"),
                    ("재고자산 평가 조정", result.inventory_adjustment, "유보"),
                    ("건설자금이자 자본화", result.interest_construction, "유보"),
                ] if amt
            ]
            proj.tax_adjustments = {
                "fiscal_year_end": str(fy_end_val),
                "net_income": result.net_income,
                "business_income": result.business_income,
                "tax_base": result.tax_base,
                "total_add_back": result.total_add_back,
                "total_deduct": result.total_deduct,
                "depreciation_denial_end": sum(d.denial_end for d in _depr_list),
                "reserves": _new_reserves,   # 차기 '전기 유보' 승계 후보 (당기 발생분)
            }
            st.success("계산 완료 — 결과가 프로젝트에 저장되어 6단계 .taxproj로 내보내면 내년에 승계됩니다")

    if st.session_state.tax_result:
        r = st.session_state.tax_result
        st.divider()
        st.markdown(section_title("핵심 세액 지표"), unsafe_allow_html=True)
        m1, m2, m3, m4 = st.columns(4, gap="medium")
        m1.metric("당기순이익",       f"{r.net_income:,.0f}원")
        m2.metric("각사업연도소득",   f"{r.business_income:,.0f}원")
        m3.metric("과세표준",         f"{r.tax_base:,.0f}원")
        m4.metric("차감납부세액",     f"{r.final_tax_due:,.0f}원")

        st.divider()
        st.markdown(section_title(
            "소득금액조정합계표 (별지 제15호서식 구조)",
            "가산조정(익금산입·손금불산입)과 차감조정(손금산입·익금불산입)을 모두 표시합니다.",
        ), unsafe_allow_html=True)
        import pandas as pd
        add_items, deduct_items = adjustment_rows(r)
        _adj_type = adj_type
        col_add, col_ded = st.columns(2, gap="medium")
        with col_add:
            st.markdown(f"**가산조정 — 합계 {r.total_add_back:,}원**")
            st.dataframe(pd.DataFrame(
                [(t, k, f"{v:,}", b, d, _adj_type(k)) for t, k, v, b, d in add_items],
                columns=["구분", "항목", "금액 (원)", "근거", "소득처분", "조정구분"],
            ), use_container_width=True, hide_index=True)
        with col_ded:
            st.markdown(f"**차감조정 — 합계 {r.total_deduct:,}원**")
            st.dataframe(pd.DataFrame(
                [(t, k, f"{v:,}", b, d, _adj_type(k)) for t, k, v, b, d in deduct_items],
                columns=["구분", "항목", "금액 (원)", "근거", "소득처분", "조정구분"],
            ), use_container_width=True, hide_index=True)
            st.caption(
                "소득처분은 **후보**입니다 — 귀속자(대표자·주주·임원)에 따라 상여·배당·기타사외유출이 "
                "달라지므로 최종 확인 필요. 결산조정 항목은 장부 계상 여부가 손금 인정의 전제입니다."
            )

        # ── 검토메모 — 발생 항목별 회계사 메모 (.taxproj에 저장되어 차기 참조) ──
        _nonzero_items = [
            (t, k, v, d, _adj_type(k))
            for t, k, v, b, d in (add_items + deduct_items) if v
        ]
        if _nonzero_items:
            with st.expander(f"검토메모 입력 — 발생 항목 {len(_nonzero_items)}개"):
                _saved_memos = (proj.tax_adjustments or {}).get("review_memos", {})
                _memo_df = pd.DataFrame([
                    {
                        "항목": k, "구분": t, "조정구분": adj,
                        "금액": f"{v:,}", "소득처분(후보)": d,
                        "검토메모": _saved_memos.get(k, ""),
                    }
                    for t, k, v, d, adj in _nonzero_items
                ])
                _memo_edit = st.data_editor(
                    _memo_df,
                    column_config={
                        "검토메모": st.column_config.TextColumn(
                            "검토메모", help="검토 결과·후속 조치 — .taxproj에 저장됩니다", width="large",
                        ),
                    },
                    disabled=["항목", "구분", "조정구분", "금액", "소득처분(후보)"],
                    use_container_width=True, hide_index=True,
                    key="review_memo_editor",
                )
                if proj.tax_adjustments is None:
                    proj.tax_adjustments = {}
                proj.tax_adjustments["review_memos"] = {
                    row["항목"]: row["검토메모"]
                    for _, row in _memo_edit.iterrows() if str(row["검토메모"]).strip()
                }

        # ── 자동 세무조정 계산 내역 (산식 + 분개장 근거 드릴다운) ──────────
        _details: dict = st.session_state.get("calc_details") or {}
        if _details:
            st.markdown(section_title(
                "자동 세무조정 계산 내역",
                "항목을 선택하면 적용 산식(법령 근거)과 집계에 사용된 분개장 내역을 확인할 수 있습니다.",
            ), unsafe_allow_html=True)
            _dnames = list(_details.keys())
            _dsel = st.selectbox(
                "조정 항목 선택",
                range(len(_dnames)),
                format_func=lambda i: f"{_dnames[i]} — {_details[_dnames[i]]['금액']:,}원",
                key="calc_detail_select",
            )
            _d = _details[_dnames[_dsel]]
            st.markdown(f"**법령 근거: {_d['법령']}**")
            if _d.get("사유"):
                st.info(f"**왜 자동조정 되었나** — {_d['사유']}")
            for _f in _d["산식"]:
                st.markdown(f"- {_f}")
            _dlines = _d.get("lines") or []
            if _dlines:
                st.caption(f"집계에 사용된 분개 {len(_dlines):,}건")
                _ddf = pd.DataFrame([
                    {
                        "날짜":     str(ln.date),
                        "전표번호": ln.journal_id,
                        "계정코드": ln.account_code,
                        "계정과목": ln.account_name,
                        "적요":     ln.description,
                        "거래처":   ln.counterparty_name,
                        "차변":     f"{ln.debit:,}" if ln.debit else "",
                        "대변":     f"{ln.credit:,}" if ln.credit else "",
                        "원본위치": f"{ln.source_sheet}!행{ln.source_row}",
                    }
                    for ln in _dlines[:1000]
                ])
                if len(_dlines) > 1000:
                    st.caption(f"⚠ {len(_dlines):,}건 중 1,000건만 표시 — 전체는 CSV로 다운로드하세요.")
                st.dataframe(
                    striped_by_group(_ddf), use_container_width=True,
                    hide_index=True, height=320,
                )
                _dcsv = pd.DataFrame([
                    {
                        "날짜": str(ln.date), "전표번호": ln.journal_id,
                        "계정코드": ln.account_code, "계정과목": ln.account_name,
                        "적요": ln.description, "거래처": ln.counterparty_name,
                        "차변": ln.debit, "대변": ln.credit,
                        "원본위치": f"{ln.source_sheet}!행{ln.source_row}",
                    }
                    for ln in _dlines
                ]).to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "이 항목 분개 내역 CSV 다운로드 (검토조서 첨부용)",
                    data=_dcsv,
                    file_name=f"계산내역_{_dnames[_dsel]}.csv",
                    mime="text/csv",
                    key="calc_detail_csv",
                )
            else:
                st.caption(
                    "이 항목은 분개장 직접 집계가 아닌 수기 입력·산식 기반입니다 — "
                    "근거 분개는 3단계 수기 입력 화면에서 확인하세요."
                )

        # 감가상각 자산별 계산 근거
        depr_results = st.session_state.get("depr_results") or []
        if depr_results:
            _n_mismatch = sum(1 for d in depr_results if d.limit_mismatch)
            _n_rate_missing = sum(1 for d in depr_results if d.rate_missing)
            with st.expander(
                "감가상각 시부인 계산 근거 (자산별)"
                + (f" — ⚠ 대장 기재 한도와 산식 불일치 {_n_mismatch}건" if _n_mismatch else "")
            ):
                if _n_mismatch:
                    st.warning(
                        f"⚠ {_n_mismatch}건은 고정자산대장의 '세무상한도' 기재값이 법령 산식 "
                        f"계산값과 1% 이상 차이납니다 — 대장 컬럼에 당기 상각비가 들어 있을 가능성이 "
                        f"있습니다. **계산은 산식값(영§26②) 기준으로 수행되었으며**, 아래 표에서 대사하세요."
                    )
                if _n_rate_missing:
                    st.caption(
                        f"※ {_n_rate_missing}건은 상각률·내용연수 정보가 없어 대장 기재값으로 폴백했습니다."
                    )
                st.dataframe(pd.DataFrame([
                    {
                        "자산코드": d.asset_code,
                        "자산명": d.asset_name,
                        "방법": d.method,
                        "상각기초가액": f"{d.base_amount:,}",
                        "상각률": f"{d.applied_rate:.3f}" if d.applied_rate else "—",
                        "월수": d.months,
                        "상각범위액(산식)": f"{d.tax_limit:,}",
                        "대장 기재 한도": f"{d.ledger_limit:,}" if d.ledger_limit else "",
                        "대사": ("⚠ 불일치" if d.limit_mismatch
                                 else ("폴백" if d.rate_missing else ("일치" if d.ledger_limit else ""))),
                        "회사계상액": f"{d.company_depr:,}",
                        "한도초과(손不)": f"{d.excess:,}",
                        "전기부인액 추인(손入)": f"{d.approved:,}",
                        "당기말 부인누계": f"{d.denial_end:,}",
                    }
                    for d in depr_results
                ]), use_container_width=True, hide_index=True, height=320)
                st.caption(
                    "상각범위액 = 상각기초가액 × 상각률 × 월수/12 (영§26② — law.go.kr 원문 확인). "
                    "정액법: 기초가액 = 취득가액(장부가+상각누계+신규취득) / "
                    "정률법: 기초가액 = 세무상 미상각잔액(장부가+전기부인누계−의제상각+신규취득). "
                    "고정자산대장의 '세무상한도' 컬럼은 계산에 사용하지 않고 대사용으로만 표시합니다."
                )

        # 법령 근거 원문 — 국가법령정보센터 (프로젝트 원칙: 모든 조정은 법령정보 기반)
        with st.expander("법령 근거 원문 (국가법령정보센터 · 사업연도 종료일 시행 기준)"):
            nonzero = [
                (name, field)
                for field, (name, _, _) in ADJUSTMENT_LEGAL_BASIS.items()
                if getattr(r, field, 0) > 0
            ]
            if not nonzero:
                st.caption("금액이 발생한 조정 항목이 없습니다.")
            else:
                sel_name = st.selectbox(
                    "조정 항목 선택", [n for n, _ in nonzero], key="legal_basis_select",
                )
                sel_field = dict(nonzero)[sel_name]
                law_text = fetch_legal_text(sel_field, str(fy_end_val))
                if law_text:
                    st.markdown(f"**{sel_name}** — 조정액 {getattr(r, sel_field):,}원")
                    st.text(law_text)
                    st.caption(
                        f"출처: 국가법령정보센터 law.go.kr · 기준일 {fy_end_val} 시행 법령 원문"
                    )
                else:
                    st.warning(
                        "조문 조회 실패 — 네트워크 연결 또는 .env의 LAW_API_KEY를 확인하세요."
                    )

        # ── 세무조정 전수 검토 체크리스트 ──────────────────────────────────
        coverage = st.session_state.get("coverage_results") or []
        if coverage:
            st.divider()
            n_auto = sum(1 for c in coverage if c.status == "자동계산")
            n_review = sum(1 for c in coverage if c.status == "검토필요")
            n_na = sum(1 for c in coverage if c.status == "해당없음")
            st.markdown(section_title(
                "세무조정 전수 검토 체크리스트",
                f"법인세법 주요 조정 항목 {len(coverage)}개 전체를 분개장과 대조한 결과입니다 — "
                f"자동계산 {n_auto} · 검토필요 {n_review} · 해당없음 {n_na}",
            ), unsafe_allow_html=True)

            if n_review:
                st.warning(
                    f"⚠ **검토필요 {n_review}건** — 관련 계정·거래가 분개장에서 발견되었으나 "
                    f"자동계산 범위 밖입니다. 추가 자료를 확보해 수동 세무조정하세요."
                )

            _icon = {"자동계산": "✅", "검토필요": "⚠", "해당없음": "—"}
            _risk_icon = {"High": "🔴 High", "Medium": "🟡 Medium", "Low": "⚪ Low"}
            cov_df = pd.DataFrame([
                {
                    "상태": f"{_icon[c.status]} {c.status}",
                    "위험도": (_risk_icon[assess_risk(c.item, c.amount_hint, c.status)]
                               if c.status != "해당없음" else ""),
                    "조정 항목": c.item,
                    "법령 근거": c.legal_basis,
                    "관련 금액(참고)": f"{c.amount_hint:,}" if c.amount_hint else "",
                    "발견 내역 / 필요 자료": c.detail,
                }
                # 검토필요 → 자동계산 → 해당없음 순 정렬, 같은 상태 안에서는 금액 큰 순
                for c in sorted(
                    coverage,
                    key=lambda x: ({"검토필요": 0, "자동계산": 1, "해당없음": 2}[x.status],
                                   -x.amount_hint),
                )
            ])
            st.dataframe(cov_df, use_container_width=True, hide_index=True, height=560)
            st.caption(
                "'관련 금액'은 해당 계정의 거래 규모이며 세무조정액이 아닙니다. "
                "검토필요 항목은 법령 근거 조문을 확인 후 수동 조정하세요."
            )

            # ── 분개장 내역 드릴다운 ──
            drillable = [c for c in coverage if c.lines]
            if drillable:
                st.markdown(section_title(
                    "분개장 내역 보기",
                    "체크리스트 항목을 선택하면 매칭된 분개 전체를 확인할 수 있습니다.",
                ), unsafe_allow_html=True)
                _dr_names = [
                    f"{c.item} — {len(c.lines):,}건 / {c.amount_hint:,}원"
                    for c in drillable
                ]
                _dr_idx = st.selectbox(
                    "조정 항목 선택",
                    range(len(_dr_names)),
                    format_func=lambda i: _dr_names[i],
                    key="coverage_drill_select",
                )
                _sel_cov = drillable[_dr_idx]
                _lines_df = pd.DataFrame([
                    {
                        "날짜":     str(ln.date),
                        "전표번호": ln.journal_id,
                        "계정코드": ln.account_code,
                        "계정과목": ln.account_name,
                        "적요":     ln.description,
                        "거래처":   ln.counterparty_name,
                        "차변":     f"{ln.debit:,}" if ln.debit else "",
                        "대변":     f"{ln.credit:,}" if ln.credit else "",
                        "원본위치": f"{ln.source_sheet}!행{ln.source_row}",
                    }
                    for ln in _sel_cov.lines
                ])
                st.dataframe(
                    striped_by_group(_lines_df), use_container_width=True,
                    hide_index=True, height=400,
                )
                _csv = _lines_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "이 내역 CSV 다운로드 (검토조서 첨부용)",
                    data=_csv,
                    file_name=f"검토내역_{_sel_cov.item}.csv",
                    mime="text/csv",
                    key="coverage_drill_csv",
                )

        # 집계 근거 (감사추적용)
        agg = st.session_state.get("journal_aggregates")
        if agg:
            with st.expander("분개장 집계 근거 보기"):
                _ev_note = (
                    "⚠ **판정 불가 — 분개장에 증빙 정보(증빙구분·카드번호)가 없습니다. "
                    "법인카드 사용내역 등으로 별도 확인 필요**"
                    if agg.entertainment.evidence_unknown
                    else f"**{agg.entertainment.no_receipt_expense:,}원** "
                         f"({len(agg.entertainment.no_receipt_lines)}건)"
                )
                st.markdown(
                    f"- 기업업무추진비 총액: **{agg.entertainment.total_expense:,}원** "
                    f"(카드 {agg.entertainment.card_expense:,}원 / "
                    f"문화비 {agg.entertainment.culture_expense:,}원 / "
                    f"전통시장 {agg.entertainment.traditional_expense:,}원)\n"
                    f"- 증빙불비 (건당 3만원 초과·적격증빙 미수취): {_ev_note}\n"
                    f"- 벌과금·과태료: **{agg.penalty.total:,}원** "
                    f"({len(agg.penalty.lines)}건)"
                )
                if agg.entertainment.no_receipt_lines:
                    st.caption("증빙불비 상세 (상위 50건)")
                    st.dataframe(pd.DataFrame([
                        {
                            "전표": ln.journal_id, "날짜": str(ln.date),
                            "적요": ln.description[:30],
                            "거래처": ln.counterparty_name,
                            "금액": f"{ln.debit:,}", "증빙": ln.evidence_type,
                        }
                        for ln in agg.entertainment.no_receipt_lines[:50]
                    ]), use_container_width=True, hide_index=True)

    # ════════ 리뷰 흐름 도구 — 계산 결과와 무관하게 현재 상태 기준 표시 ════════
    import pandas as pd

    # ── ① 자료요청 리스트 — "계산 불가"가 아니라 "무엇을 받아야 하는지" ──────
    st.divider()
    st.markdown(section_title(
        "고객 자료요청 리스트",
        "현재 업로드·입력 상태에서 세무조정 진행에 부족한 자료를 자동 점검합니다 — "
        "용역 초기에 이 목록을 고객에게 먼저 보내세요.",
    ), unsafe_allow_html=True)
    _agg_for_req = st.session_state.get("journal_aggregates")
    if _agg_for_req is None and loader.journals:
        _agg_for_req = aggregate_journals(loader.journals)
    _requests = build_data_requests(
        loader, proj.manual_input, proj.company, _agg_for_req,
        has_prev_proj=bool(st.session_state.get("prev_proj_loaded")),
        # 자동 인식 성공 또는 수기 입력·'0원 확인' 상태 — 손익계산서 재요청 방지
        net_income_confirmed=_ni_ready,
    )
    if not _requests:
        st.success("✓ 현재 상태에서 추가로 요청할 자료가 없습니다.")
    else:
        _risk_icon2 = {"High": "🔴", "Medium": "🟡", "Low": "⚪"}
        _req_df = pd.DataFrame([
            {
                "위험도": f"{_risk_icon2[q.risk]} {q.risk}",
                "요청 자료": q.item,
                "왜 필요한가": q.reason,
                "관련 세무조정": q.related,
            }
            for q in sorted(_requests, key=lambda x: {"High": 0, "Medium": 1, "Low": 2}[x.risk])
        ])
        st.dataframe(_req_df, use_container_width=True, hide_index=True)
        _req_txt = f"[{proj.company.name or '회사'}] 세무조정 진행을 위한 자료요청 목록\n" + \
            f"(사업연도 {fy_start} ~ {fy_end_val})\n\n" + "\n".join(
                f"{i+1}. {q.item}\n   - 사유: {q.reason}\n   - 관련: {q.related}"
                for i, q in enumerate(_requests)
            )
        st.download_button(
            "자료요청 목록 다운로드 (고객 발송용 .txt)",
            data=_req_txt.encode("utf-8-sig"),
            file_name=f"자료요청_{proj.company.name}_{fy_end_val}.txt",
            mime="text/plain", key="data_request_dl",
        )

    # ── ② 전년 대비 증감분석 — 검토 우선순위 (규칙 기반) ─────────────────────
    st.divider()
    st.markdown(section_title(
        "전년 대비 증감분석 (분석적 검토)",
        "전기 값 출처: ① 2단계에 업로드한 전기 손익계산서 (우선) ② 당기 손익계산서의 전기 열. "
        "급증 항목이 검토 우선순위입니다.",
    ), unsafe_allow_html=True)
    _prev_loader = st.session_state.get("prev_loader")
    _prev_is = getattr(_prev_loader, "income_statement", None)
    _yoy = yoy_table(loader.income_statement, prev_income_df=_prev_is)
    if _yoy is None:
        st.caption(
            "전기 비교 데이터가 없습니다 — 2단계에서 **전기 손익계산서**를 업로드하거나, "
            "당기 손익계산서가 당기/전기 2개 열이 있는 양식이면 자동 분석됩니다."
        )
    else:
        st.caption(f"전기 값 출처: **{_yoy.attrs.get('prev_source', '')}**")
        _rev_cur = loader.get_amount_by_name(("매출액",))
        _rev_row = _yoy[_yoy["계정명"].str.replace(" ", "").str.contains("매출액", regex=False)]
        _rev_prev = int(_rev_row["전기"].iloc[0]) if not _rev_row.empty else 0
        for _f in yoy_flags(_yoy, _rev_cur, _rev_prev):
            st.warning(_f)
        with st.expander(f"계정별 증감 전체 보기 ({len(_yoy)}개 계정)"):
            _yoy_show = _yoy.copy()
            for c in ("당기", "전기", "증감"):
                _yoy_show[c] = _yoy_show[c].map("{:,}".format)
            st.dataframe(_yoy_show, use_container_width=True, hide_index=True, height=400)
            st.download_button(
                "증감분석 CSV 다운로드",
                data=_yoy.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"증감분석_{proj.company.name}_{fy_end_val}.csv",
                mime="text/csv", key="yoy_dl",
            )

    # ── ②-2 기초잔액 대사 — 당기 B/S 기초 ↔ 전기 B/S 기말 (분석적 검토) ──────
    _prev_bs = getattr(_prev_loader, "balance_sheet", None)
    if _prev_bs is not None and loader.balance_sheet is not None:
        _bs_chk = bs_opening_check(loader.balance_sheet, _prev_bs)
        if _bs_chk is not None:
            if len(_bs_chk) == 0:
                st.success(
                    "✓ 기초잔액 대사 일치 — 당기 B/S 기초잔액과 전기 B/S 기말잔액이 "
                    "모든 계정에서 일치합니다 (적수 계산의 기초잔액 신뢰 가능)."
                )
            else:
                with st.expander(
                    f"⚠ 기초잔액 대사 불일치 {len(_bs_chk)}계정 — "
                    f"당기 기초 ≠ 전기 기말 (클릭하여 확인)", expanded=True,
                ):
                    st.warning(
                        "불일치는 ① 파싱 오류 ② 전기 재무제표 수정 ③ 계정 재분류 신호입니다 — "
                        "적수 계산(가지급금·차입금·보증금)의 기초잔액에 영향하므로 원인을 확인하세요."
                    )
                    _bs_show = _bs_chk.copy()
                    for c in ("당기 기초잔액", "전기 기말잔액", "차이"):
                        _bs_show[c] = _bs_show[c].map("{:,}".format)
                    st.dataframe(_bs_show, use_container_width=True, hide_index=True,
                                 height=min(400, 60 + 36 * len(_bs_show)))
                    st.download_button(
                        "기초잔액 대사 CSV 다운로드",
                        data=_bs_chk.to_csv(index=False).encode("utf-8-sig"),
                        file_name=f"기초잔액대사_{proj.company.name}_{fy_end_val}.csv",
                        mime="text/csv", key="bs_check_dl",
                    )

    # ── ③ 고객 설명용 메모 — 조정 결과를 고객 언어로 (규칙 기반 템플릿) ───────
    if st.session_state.tax_result and st.session_state.get("calc_details"):
        st.divider()
        st.markdown(section_title(
            "고객 설명용 메모 (자동 생성)",
            "발생한 조정 항목을 고객에게 설명하는 문구 초안입니다 — 수정 후 사용하세요.",
        ), unsafe_allow_html=True)
        # 결정론적 템플릿 (화면·PDF 공용 — forms/review_pdf.build_client_memo)
        from src.forms.review_pdf import build_client_memo
        _memo_text = build_client_memo(
            st.session_state.calc_details, proj.company.name, fy_end_val.year,
        )
        st.text_area("고객 발송용 초안", value=_memo_text, height=280, key="client_memo_text")
        st.download_button(
            "고객 설명 메모 다운로드 (.txt)",
            data=_memo_text.encode("utf-8-sig"),
            file_name=f"세무조정안내_{proj.company.name}_{fy_end_val}.txt",
            mime="text/plain", key="client_memo_dl",
        )

