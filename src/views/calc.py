"""5단계 — 세무조정 계산·검토 (집계 → 법령 산식 → 별지15호 → 드릴다운)."""
from __future__ import annotations
from datetime import date

import streamlit as st

from src.parsers.smart_a import SmartALoader
from src.rules.aggregator import aggregate_journals, sum_related_party_revenue
from src.rules.depreciation import calc_depreciation_all
from src.rules.entertainment import calc_entertainment
from src.rules.donation import (
    calc_donation, eligible_donation_carryforward, roll_forward,
)
from src.rules.allowances import (
    calc_bad_debt_allowance, calc_retirement_allowance, calc_pension_deduction,
)
from src.rules.income_items import (
    calc_deemed_interest_by_party, calc_deemed_rental, calc_debt_relief_offset,
)
from src.rules.jeoksu import jeoksu_from_deltas, account_jeoksu, fy_days, lines_to_deltas
from src.rules.dividend import calc_dividend_exclusion
from src.rules.legal_basis import ADJUSTMENT_LEGAL_BASIS, fetch_legal_text
import src.rules.legal_basis as legal_basis
from src.rules.data_requests import build_data_requests, assess_risk
from src.rules.yoy_analysis import yoy_table, yoy_flags, bs_opening_check
from src.forms.summary_rows import adjustment_rows, adj_type
from src.forms.reserve_status import build_reserve_status, reserve_totals
from src.rules.disposition import ATTRIBUTION_TYPES
from src.rules.consulting import build_consulting_topics
from src.rules.coverage import run_coverage_check
from src.rules.other_adjustments import (
    calc_penalty, calc_officer_bonus_excess, calc_officer_retirement_excess,
    calc_stock_based_compensation_excess, calc_construction_progress_adjustment,
    calc_treasury_stock_disposal, calc_proper_purpose_reserve,
)
from src.rules.vehicle import calc_vehicle
from src.rules.tax_base import compute_all, eligible_carryforward_total, calc_land_transfer_tax
from src.utils.constants import (
    get_prime_rate, is_prime_rate_published,
    LOSS_CARRYFORWARD_SME_RATE, LOSS_CARRYFORWARD_GENERAL_RATE,
)
from src.utils.safe_export import safe_df
from src.utils.models import TaxAdjustmentResult, TaxCredit
from src.ui.manual_input import _bs_amount, _bs_amount_detail
from src.ui.review_questions import build_results
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
        if st.button("규칙 엔진 계산 실행", width="stretch", disabled=not _ni_ready):
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

                def _add_detail(name, amount, basis, formula, lines=None, reason="",
                                book=None, tax=None, tax_basis="", disposition=""):
                    """reason: '왜' 이 조정이 자동 발생했는지 — 판정 트리거(데이터 출처 + 조건).

                    book/tax: 장부상 금액·세무상 금액 (검토패키지 Book/Tax 표시용).
                    둘 다 None이면 분개 직접집계가 아닌 산식·수기 항목으로 '—' 표시된다.
                    tax_basis: 세무상 금액 산정 근거(요약). disposition: 소득처분 후보(영§106).
                    """
                    if amount:
                        calc_details[name] = {
                            "금액": amount, "법령": basis,
                            "산식": formula, "lines": lines or [],
                            "사유": reason,
                            "book": book, "tax": tax,
                            "tax_basis": tax_basis, "처분": disposition,
                        }

                revenue = (
                    loader.get_account_total("4")
                    or loader.get_amount_by_name(("매출액",))
                    or agg.revenue
                )
                # 수입금액 수기 보정 (영§42① 기업회계기준 매출액) — 파서가 매출을
                # 누락·오분류한 경우만. 입력값(>0)이 있으면 우선. 기업업무추진비 한도 분모.
                if int(getattr(mi, "revenue_manual", 0) or 0) > 0:
                    revenue = int(mi.revenue_manual)
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
                        book=ent.total_expense - ent.no_receipt_disallowed,
                        tax=ent.total_limit,
                        tax_basis=(f"기본한도 {ent.base_limit:,}원 + 수입금액한도 {ent.revenue_limit:,}원"
                                   + ("의 50%(특정법인)" if is_spec else "")
                                   + f" = 손금인정 한도 {ent.total_limit:,}원 (법§25④)"),
                        disposition="기타사외유출",
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
                        book=ent.no_receipt_disallowed, tax=0,
                        tax_basis="건당 3만원 초과 + 적격증빙 미수취 → 손금 불인정 (법§25②, 전액)",
                        disposition="기타사외유출",
                    )

                result.penalty = calc_penalty(agg.penalty.total)
                _add_detail(
                    "벌과금·과태료·가산세", result.penalty, "법§21 3호",
                    [f"벌과금·과태료·가산세는 전액 손금불산입 — 분개장 {len(agg.penalty.lines)}건 합계 {result.penalty:,}원"],
                    agg.penalty.lines,
                    reason="분개장에서 벌과금 계정(8391) 또는 계정명·적요에 벌과금·과태료·가산세·범칙금이 "
                           "있는 분개 발견 → 법§21 3호에 따라 조건 없이 전액 손금불산입",
                    book=result.penalty, tax=0,
                    tax_basis="벌과금·과태료·가산세는 손금 불인정 (법§21 3호, 전액)",
                    disposition="기타사외유출",
                )

                # ── 익금산입: 가지급금 인정이자 — 거래상대방별 적수(積數) 계산 ──
                # (법§52, 영§88①6호·③, 영§89③⑤ — 별지 제19호 구조)
                _rate = mi.related_loan_rate or get_prime_rate(fy_end_val.year)
                _rate_label = (
                    "가중평균차입이자율 (영§89③ 원칙)" if mi.related_loan_rate > 0
                    else "당좌대출이자율 (가중평균이자율 미입력 — 영§89③ 단서)"
                )
                # 미고시 연도 당좌대출이자율 폴백 경고 (고시 변경 모니터링 누락 방지)
                if mi.related_loan_rate == 0 and not is_prime_rate_published(fy_end_val.year):
                    st.warning(
                        f"⚠ {fy_end_val.year}년 당좌대출이자율 고시값이 등록돼 있지 않아 "
                        f"인접 연도값({_rate:.1%})을 적용했습니다 — 국세청 고시(규칙§43②)를 확인해 "
                        "constants.PRIME_RATE_BY_YEAR을 갱신하세요."
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

                # 거래상대방(차주)별 기초이월·약정이자 — 3단계 표(별지19호 1행/차주)
                _lp = {
                    str(p.get("name", "")).strip(): p
                    for p in (mi.related_loan_parties or [])
                    if str(p.get("name", "")).strip()
                }
                _parties: list[tuple[str, int, int]] = [
                    (cp,
                     jeoksu_from_deltas(deltas, fy_start, fy_end_val,
                                        opening=int(_lp.get(cp, {}).get("opening", 0))),
                     _actual_by_cp.get(cp, 0) + int(_lp.get(cp, {}).get("interest", 0)))
                    for cp, deltas in _party_deltas.items()
                ]
                # 표에만 있는 차주(당기 거래 0건·기초이월만 있는 경우)
                for _nm, _p in _lp.items():
                    if _nm not in _party_deltas:
                        _op, _it = int(_p.get("opening", 0)), int(_p.get("interest", 0))
                        if _op or _it:
                            _parties.append((_nm, _op * _fy_d,
                                             _actual_by_cp.get(_nm, 0) + _it))
                # 폴백 — 거래상대방 표가 비었을 때만 (이중계상 방지)
                if not _lp:
                    if mi.related_loan_opening > 0:
                        _parties.append(
                            ("(기초이월분 — 상대방 미지정)", mi.related_loan_opening * _fy_d, 0)
                        )
                    if not _parties and mi.related_loan_balance > 0:
                        _parties = [("전체 (잔액 근사)",
                                     mi.related_loan_balance * _fy_d, mi.related_loan_interest)]

                _loan_jeoksu_total = sum(p[1] for p in _parties)
                if _parties:
                    dip = calc_deemed_interest_by_party(_parties, rate=_rate, days=_fy_d)
                    _incl = dip.inclusion_amount
                    # 단일 수기 약정이자 차감 — 거래상대방 표 미사용 시에만 (표 사용 시 차주별 반영됨)
                    if not _lp and _loan_lines and mi.related_loan_interest > 0:
                        _incl = max(0, _incl - mi.related_loan_interest)
                    result.deemed_interest = _incl
                    # 소득처분 귀속자 입력용 — 익금산입된 상대방별 내역 저장 (영§106)
                    result.deemed_interest_parties = [
                        {"name": p.name, "amount": p.inclusion}
                        for p in dip.parties if p.inclusion > 0
                    ]
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
                    if not _lp and _loan_lines and mi.related_loan_interest > 0:
                        _di_formula.append(
                            f"수기 입력 약정이자 {mi.related_loan_interest:,}원 차감 "
                            f"(상대방 미지정 — 상대방별 귀속 확인 필요)"
                        )
                    _di_formula.append(f"익금산입 합계 = {result.deemed_interest:,}원")
                    _di_actual = sum(p.actual for p in dip.parties) + (
                        mi.related_loan_interest if (not _lp and _loan_lines and mi.related_loan_interest > 0) else 0
                    )
                    _di_deemed = sum(p.deemed for p in dip.parties)
                    _add_detail(
                        "가지급금 인정이자", result.deemed_interest,
                        "법§52, 영§88①6호·③, 영§89③⑤",
                        _di_formula,
                        agg.detail_lines.get("가지급금·대여금"),
                        reason="3단계에서 체크한 가지급금·대여금 분개의 거래 날짜로 거래상대방별 "
                               "일별 적수를 계산 (1단계 특수관계인 목록 기준 추천) — 약정이자는 "
                               "이자수익 분개의 거래처로 자동 매칭. 영§88③ 기준(차액 3억 또는 시가 5%) "
                               "미달 상대방은 제외",
                        book=_di_actual, tax=_di_deemed,
                        tax_basis=f"거래상대방별 가지급금 적수 × {_rate:.2%} ÷ {_fy_d}일 (영§89⑤) "
                                  "— 상대방 간 통산 없음·동일인 가수금 상계, 약정이자 차감 후 익금산입",
                        disposition="상여 등",
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
                    # 임대보증금 적수 — 받은 보증금(부채) 기준, B/S 기초 + 당기 증감 일별 계산
                    _dep_kw = ("임대보증금", "전세보증금")
                    # 기초총액: 임대물건별 명세 합계 우선, 없으면 B/S 기초잔액
                    _dep_open = sum(
                        int(x.get("기초 보증금", 0)) for x in (mi.rental_deposit_items or [])
                    ) or _bs_amount_detail(loader, _dep_kw, column="기초잔액")[0]
                    # 3단계에서 '간주임대료 대상'으로 체크된 받은 임대보증금 분개만 사용
                    _dep_checks = (mi.misc_line_checks or {}).get("rental_deposit_lines", {})
                    if _dep_checks:
                        _dep_lines = [
                            ln for ln in loader.journals
                            if _dep_checks.get(f"{ln.journal_id}|{ln.source_row}")
                        ]
                        _dep_jeoksu = jeoksu_from_deltas(
                            lines_to_deltas(_dep_lines, debit_positive=False),
                            fy_start, fy_end_val, opening=_dep_open, floor_zero=False,
                        )
                        _dep_src = "분개 체크(받은 임대보증금) 일별 계산"
                    else:
                        _dep_jeoksu = account_jeoksu(
                            loader.journals, _dep_kw, fy_start, fy_end_val,
                            opening=_dep_open, debit_positive=False,
                        )
                        _dep_src = "분개장 일별 계산 (기초잔액 + 당기 증감)"
                    if _dep_jeoksu <= 0:
                        _dep_jeoksu = mi.rental_deposit * _fy_d
                        _dep_src = "기말잔액 × 일수 근사"

                    # 건설비상당액 적수 — 건물·구축물 계정(취득가액)의 일별 적수에
                    # 임대용 면적비율을 곱해 산정 (조특령§132⑥, 칙§59 — 면적 기준 안분).
                    # 면적비율 미입력 시 금액비율(입력 건설비 ÷ 기말 건물가액)로 폴백.
                    _con_kw = ("건물", "구축물")
                    _con_close = _bs_amount(loader, _con_kw)
                    _con_open = _bs_amount_detail(loader, _con_kw, column="기초잔액")[0]
                    _bld_jeoksu = account_jeoksu(
                        loader.journals, _con_kw, fy_start, fy_end_val,
                        opening=_con_open, debit_positive=True,
                    )
                    if _bld_jeoksu > 0 and mi.rental_area_ratio > 0:
                        _rent_ratio = min(1.0, mi.rental_area_ratio)
                        _con_jeoksu = int(_bld_jeoksu * _rent_ratio)
                        _con_src = (f"건물·구축물 분개 일별 계산 × 임대 면적비율 {_rent_ratio:.1%} "
                                    f"(조특칙§59 면적 기준)")
                    elif (_bld_jeoksu > 0 and _con_close > 0
                            and 0 < mi.rental_construction_cost):
                        _rent_ratio = min(1.0, mi.rental_construction_cost / _con_close)
                        _con_jeoksu = int(_bld_jeoksu * _rent_ratio)
                        _con_src = (f"건물·구축물 분개 일별 계산 × 금액비율 {_rent_ratio:.1%} "
                                    f"(입력 건설비 ÷ 기말 건물가액 {_con_close:,}원 — 면적비율 미입력 폴백)")
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
                            book=0, tax=dr.inclusion_amount,
                            tax_basis=(f"(보증금 적수 − 건설비 적수) × 정기예금이자율 {dr.bank_rate:.1%} ÷ {_fy_d}일 "
                                       f"− 보증금 운용 금융수익 {dr.financial_income:,}원 (조특령§132⑤)"),
                            disposition="기타사외유출",
                            formula=[f"적용 요건: {dr.reason}",
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
                        book=_divr.dividend_income,
                        tax=_divr.dividend_income - _divr.exclusion_amount,
                        tax_basis=f"수입배당금 × 익금불산입률 {_divr.exclusion_rate:.0%} 차감 (법§18의2①)",
                        disposition="기타",
                    )

                # ── 익금불산입: 자산수증익·채무면제익 이월결손금 보전 (법§18 6호, 영§16) ──
                if mi.asset_gift_revenue or mi.debt_forgiveness_revenue:
                    _dro = calc_debt_relief_offset(
                        asset_gift=mi.asset_gift_revenue,
                        debt_forgiveness=mi.debt_forgiveness_revenue,
                        carryforward_available=mi.debt_relief_carryforward,
                    )
                    result.debt_relief_offset = _dro.offset
                    _add_detail(
                        "자산수증익·채무면제익 (이월결손금 보전)", _dro.offset, "법§18 6호",
                        [f"자산수증익 {_dro.asset_gift:,}원 + 채무면제익 {_dro.debt_forgiveness:,}원 "
                         f"= {_dro.gross:,}원 중 보전 충당 이월결손금({_dro.carryforward_available:,}원) "
                         f"한도까지 익금불산입 = {_dro.offset:,}원",
                         "수익 계상된 자산수증익·채무면제익은 이미 net_income 포함 → 보전충당분만 손금산입(△, 기타)",
                         "근거 자료: 3단계 수기 입력 (자산수증익·채무면제익·보전 이월결손금)"],
                        reason="3단계에서 자산수증익·채무면제익 수익 계상액과 보전에 충당하는 "
                               "이월결손금(영§16 — 공제기한 지난 것 포함)을 입력 → min(이익, 결손금) 익금불산입",
                        book=_dro.gross, tax=_dro.gross - _dro.offset,
                        tax_basis="이월결손금 보전 충당액만큼 익금불산입(손금산입 △) (법§18 6호, 영§16)",
                        disposition="기타",
                    )

                # ── 익금불산입: 국세환급금 이자(법§18 4호)·부가세 매출세액(법§18 5호) ──
                result.refund_interest_excluded = max(0, mi.refund_interest_revenue)
                result.vat_output_excluded = max(0, mi.vat_output_revenue)
                _add_detail(
                    "국세환급금 이자", result.refund_interest_excluded, "법§18 4호",
                    ["국세·지방세 과오납 환급금에 부가되는 이자(국세환급가산금)를 수익 계상한 경우 → 전액 익금불산입",
                     "근거 자료: 3단계 수기 입력 (수익 계상한 국세환급금 이자)"],
                    reason="3단계에서 잡이익·이자수익 중 국세환급가산금 해당분을 입력 → 익금불산입(△, 기타)",
                    book=result.refund_interest_excluded, tax=0,
                    tax_basis="국세·지방세 과오납 환급금 이자는 익금불산입 (법§18 4호)",
                    disposition="기타",
                )
                _add_detail(
                    "부가가치세 매출세액", result.vat_output_excluded, "법§18 5호",
                    ["부가가치세 매출세액을 수익으로 계상한 경우 → 전액 익금불산입 (정상 회계처리 시 미발생)",
                     "근거 자료: 3단계 수기 입력 (수익 계상한 부가세 매출세액)"],
                    reason="3단계에서 수익으로 잘못 계상된 부가세 매출세액을 입력 → 익금불산입(△, 기타)",
                    book=result.vat_output_excluded, tax=0,
                    tax_basis="부가가치세 매출세액은 익금불산입 (법§18 5호)",
                    disposition="기타",
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
                    book=result.corporate_tax_expense, tax=0,
                    tax_basis="법인세·법인지방소득세 비용은 손금 불인정 (법§21 1호, 전액)",
                    disposition="기타사외유출",
                )

                # 외화환산손익 — 평가방법 미신고 시 평가손익 부인 (법§42③, 영§76)
                if not mi.forex_method_reported:
                    result.forex_loss_disallowed = agg.forex_eval_loss
                    result.forex_gain_excluded = agg.forex_eval_gain
                    _fx_note = "마감환율 평가방법 미신고 (3단계 수기 입력) → 평가손익 전액 부인"
                    _fx_why = ("3단계 수기 입력에서 '마감환율 평가방법 신고함'이 체크되지 않음 → "
                               "미신고 법인의 외화 평가손익은 세법상 미실현손익으로 부인 (신고했다면 3단계에서 체크)")
                    _add_detail("외화환산손실 부인", agg.forex_eval_loss, "법§42③, 영§76",
                                [_fx_note], agg.detail_lines.get("외화환산손실"), reason=_fx_why,
                                book=agg.forex_eval_loss, tax=0,
                                tax_basis="평가방법 미신고 → 미실현 평가손익 부인 (법§42③, 영§76)",
                                disposition="유보")
                    _add_detail("외화환산이익 익금불산입", agg.forex_eval_gain, "법§42③, 영§76",
                                [_fx_note], agg.detail_lines.get("외화환산이익"), reason=_fx_why,
                                book=agg.forex_eval_gain, tax=0,
                                tax_basis="평가방법 미신고 → 미실현 평가손익 부인 (법§42③, 영§76)",
                                disposition="△유보")

                # 통화선도 등 파생상품 평가손익 (영§76)
                if not mi.derivative_hedge_reported:
                    result.derivative_loss_disallowed = agg.derivative_eval_loss
                    result.derivative_gain_excluded = agg.derivative_eval_gain
                    _dv_note = "통화선도 등 평가방법 미신고 → 평가손익 전액 부인 (영§76)"
                    _dv_why = ("3단계 수기 입력에서 '파생상품 평가방법 신고함'이 체크되지 않음 → "
                               "평가손익(미실현) 부인. 거래·정산 실현손익은 집계에서 제외되어 있음")
                    _add_detail("파생상품 평가손실 부인", agg.derivative_eval_loss, "영§76",
                                [_dv_note], agg.detail_lines.get("파생상품 평가손실"), reason=_dv_why,
                                book=agg.derivative_eval_loss, tax=0,
                                tax_basis="평가방법 미신고 → 미실현 평가손익 부인 (영§76)",
                                disposition="유보")
                    _add_detail("파생상품 평가이익 익금불산입", agg.derivative_eval_gain, "영§76",
                                [_dv_note], agg.detail_lines.get("파생상품 평가이익"), reason=_dv_why,
                                book=agg.derivative_eval_gain, tax=0,
                                tax_basis="평가방법 미신고 → 미실현 평가손익 부인 (영§76)",
                                disposition="△유보")

                # 유가증권 평가손익 — 일반법인 원가법 강제, 전액 부인 (영§75)
                result.securities_loss_disallowed = agg.securities_eval_loss
                result.securities_gain_excluded = agg.securities_eval_gain
                _sec_note = "일반법인 유가증권은 원가법만 인정 → 평가손익 전액 부인 (영§75①)"
                _sec_why = ("분개장에서 유가증권·금융자산 평가손익 계정 발견 → 일반법인은 원가법이 "
                            "강제되므로 입력과 무관하게 항상 부인 (유보로 처분 후 처분 시 추인)")
                _add_detail("유가증권 평가손실 부인", agg.securities_eval_loss, "영§75",
                            [_sec_note], agg.detail_lines.get("유가증권 평가손실"), reason=_sec_why,
                            book=agg.securities_eval_loss, tax=0,
                            tax_basis="일반법인 원가법 강제 → 평가손익 부인 (영§75①)",
                            disposition="유보")
                _add_detail("유가증권 평가이익 익금불산입", agg.securities_eval_gain, "영§75",
                            [_sec_note], agg.detail_lines.get("유가증권 평가이익"), reason=_sec_why,
                            book=agg.securities_eval_gain, tax=0,
                            tax_basis="일반법인 원가법 강제 → 평가손익 부인 (영§75①)",
                            disposition="△유보")

                # 재고자산 평가 조정 및 기타 손금불산입 (수기 입력)
                _manual_src = "근거 자료: 3단계 수기 입력의 분개 체크 내역"
                _manual_why = "3단계 수기 입력에서 해당 분개를 직접 체크·분류함 (자동 추출 아님 — 사용자 판단 반영)"
                # 재고자산 평가 — 건별 질문형(종류별, 영§74④ 단서). 없으면 레거시 총액.
                from src.ui.review_specs import inventory_spec as _inv_spec
                _inv_results = build_results(
                    _inv_spec(), (mi.review_answers or {}).get("재고자산 평가", []))
                result.inventory_adjustment = (
                    sum(r.amount for r in _inv_results) if _inv_results
                    else mi.inventory_valuation_adjustment)
                _inv_basis_lines = (
                    [f"건별 평가조정 합계 {result.inventory_adjustment:,}원 — {len(_inv_results)}건",
                     "3단계 재고자산 평가조정 건별 질문 입력 기준"]
                    if _inv_results else
                    ["신고 평가방법과 장부 적용방법 불일치 → 세법상 재계산 차액 (무신고 시 선입선출법)", _manual_src]
                )
                _inv_reason = (
                    "3단계에서 재고 종류별 신고상태·장부가액·선입선출/신고방법 평가액 입력 → "
                    "영§74④ 기준으로 조정금액 산정"
                    if _inv_results else
                    "3단계 재고자산 평가방법 입력에서 ①신고방법과 ②장부방법이 불일치 (또는 무신고)"
                )
                # 복리후생비(열거 외) — 건별 질문형(영§45 열거게이트·건별 처분). 없으면 레거시 총액.
                from src.ui.review_specs import welfare_spec
                _welfare_results = build_results(
                    welfare_spec(), (mi.review_answers or {}).get("복리후생비 (열거 외)", []))
                if _welfare_results:
                    result.welfare_disallowed = sum(r.amount for r in _welfare_results)
                    result.welfare_disallowed_lines = [
                        {"amount": r.amount, "disposition": r.disposition,
                         "basis": r.legal_basis, "ref": r.line_ref}
                        for r in _welfare_results]
                else:
                    result.welfare_disallowed = mi.welfare_disallowed
                result.joint_expense_excess = mi.joint_expense_excess
                result.non_business_expense = mi.non_business_expense
                result.punitive_damages = mi.punitive_damages

                # ── 회계사 직접 입력 세무조정 (규칙엔진 미포착 항목 수동 가감) ──
                _ADD_CATS = ("익금산입", "손금불산입")
                _custom_lines = []
                for _ca in (mi.custom_adjustments or []):
                    _amt = int(_ca.get("amount", 0) or 0)
                    _nm = str(_ca.get("name", "")).strip()
                    _cat = str(_ca.get("category", "")).strip()
                    if not _amt or not _nm or _cat not in ("익금산입", "손금불산입", "손금산입", "익금불산입"):
                        continue
                    _disp = str(_ca.get("disposition", "")).strip() or "검토필요"
                    _basis = str(_ca.get("basis", "")).strip() or "회계사 직접 입력 (수기 조정)"
                    _custom_lines.append({
                        "name": _nm, "amount": _amt, "category": _cat,
                        "disposition": _disp, "basis": _basis,
                    })
                    _add_detail(
                        f"[수기조정] {_nm}", _amt, _basis, [],
                        reason="회계사가 3단계 수기입력에서 직접 추가한 세무조정 — 규칙엔진 미포착 항목",
                        tax_basis=f"{_cat} (회계사 직접 입력)", disposition=_disp,
                    )
                result.custom_adjustment_lines = _custom_lines
                _add_detail("재고자산 평가 조정", result.inventory_adjustment, "영§74",
                            _inv_basis_lines,
                            reason=_inv_reason,
                            tax_basis="신고 평가방법으로 재계산한 재고자산가액과 장부가액의 차액 (영§74)",
                            disposition="유보")
                if result.welfare_disallowed_lines:
                    _wf_disp = " · ".join(f"{x['disposition']} {x['amount']:,}"
                                          for x in result.welfare_disallowed_lines)
                    _add_detail("복리후생비 (열거 외)", result.welfare_disallowed, "영§45①",
                                [f"건별 손금불산입 {result.welfare_disallowed:,}원 — "
                                 f"{len(result.welfare_disallowed_lines)}건",
                                 f"건별 소득처분: {_wf_disp}",
                                 "영§45① 열거 8항목(직장체육·경조사 등)은 손금 인정 — '열거 외'만 부인"],
                                reason="3단계에서 복리후생비를 건별로 영§45 열거여부·귀속자 입력 → "
                                       "열거 외 비용만 손금불산입, 귀속자별 소득처분",
                                book=result.welfare_disallowed, tax=0,
                                tax_basis="영§45① 열거 외 복리후생비 손금불산입, 건별 소득처분",
                                disposition="건별 (상여·배당 등)")
                else:
                    _add_detail("복리후생비 (열거 외)", mi.welfare_disallowed, "영§45",
                                ["영§45① 열거 항목 외 복리후생비 → 전액 손금불산입", _manual_src],
                                reason=_manual_why,
                                book=mi.welfare_disallowed, tax=0,
                                tax_basis="영§45① 열거 외 복리후생비 손금 불인정 (전액)",
                                disposition="상여 등")
                _add_detail("공동경비 분담 초과", mi.joint_expense_excess, "영§48",
                            [f"부담액 − (공동경비 총액 {mi.joint_total_pool:,}원 × 분담비율 {mi.joint_share_ratio:.1%}) = 초과분 {mi.joint_expense_excess:,}원", _manual_src],
                            reason="3단계에서 공동경비 분개 체크 + 총액·분담비율 입력 → 분담기준 초과분만 손금불산입",
                            book=int(mi.joint_total_pool * mi.joint_share_ratio) + mi.joint_expense_excess,
                            tax=int(mi.joint_total_pool * mi.joint_share_ratio),
                            tax_basis=f"공동경비 총액 {mi.joint_total_pool:,}원 × 분담비율 {mi.joint_share_ratio:.1%} = 손금인정 한도 (영§48)",
                            disposition="기타사외유출")
                _add_detail("업무무관비용", mi.non_business_expense, "법§27",
                            ["업무와 관련 없는 자산·지출 비용 → 전액 손금불산입", _manual_src],
                            reason=_manual_why,
                            book=mi.non_business_expense, tax=0,
                            tax_basis="업무와 관련 없는 자산·지출 비용 손금 불인정 (법§27, 전액)",
                            disposition="기타사외유출")
                _add_detail("징벌적 손해배상금", mi.punitive_damages, "법§21의2, 영§23",
                            [("실손해액 분명 → 지급액 − 실손해액 " + f"{mi.punitive_actual_amount:,}원" )
                             if mi.punitive_actual_known else "실손해액 불분명 → 지급액 × 2/3 (영§23②)",
                             _manual_src],
                            reason="3단계에서 손해배상 분개 체크 + 실손해액 분명 여부 선택",
                            tax_basis=("지급액 − 실손해액 (영§23)" if mi.punitive_actual_known
                                       else "실손해액 불분명 → 지급액 × 2/3 손금불산입 (영§23②)"),
                            disposition="기타사외유출")

                # 추가 자동계산 항목 — 분개 파싱만으로 확정 불가한 법정 판단값은 3단계 입력 사용
                result.stock_compensation_excess = calc_stock_based_compensation_excess(
                    booked_expense=mi.stock_comp_booked_expense,
                    deductible_amount=mi.stock_comp_deductible_amount,
                )
                _add_detail(
                    "주식매수선택권·주식기준보상 비용", result.stock_compensation_excess,
                    "조특법§13의2, 조특령§19",
                    [f"장부 비용 {mi.stock_comp_booked_expense:,}원 − 법정 손금산입 인정액 "
                     f"{mi.stock_comp_deductible_amount:,}원 = 손금불산입 {result.stock_compensation_excess:,}원",
                     "대상 법인·임직원·부여요건·행사요건 충족 여부는 3단계 입력값의 전제"],
                    reason="3단계에서 장부 비용계상액과 조특법상 손금산입 인정액을 입력 → 초과 비용 손금불산입",
                    book=mi.stock_comp_booked_expense, tax=mi.stock_comp_deductible_amount,
                    tax_basis="조특법§13의2 요건 충족액만 손금 인정",
                    disposition="기타사외유출",
                )

                _progress_diff = calc_construction_progress_adjustment(
                    tax_revenue=mi.construction_tax_revenue,
                    book_revenue=mi.construction_book_revenue,
                )
                result.construction_revenue_add = max(0, _progress_diff)
                result.construction_revenue_excluded = max(0, -_progress_diff)
                _add_detail(
                    "작업진행률 수익인식", abs(_progress_diff), "영§69",
                    [f"세무상 작업진행률 수익 {mi.construction_tax_revenue:,}원 − 장부 수익 "
                     f"{mi.construction_book_revenue:,}원 = {_progress_diff:+,}원",
                     "양수는 익금산입, 음수는 익금불산입으로 반영"],
                    reason="3단계에서 세무상 진행률 수익과 장부 수익을 입력 → 차액을 귀속시기 조정",
                    book=mi.construction_book_revenue, tax=mi.construction_tax_revenue,
                    tax_basis="작업진행률 기준 수익 귀속 (영§69)",
                    disposition="유보/△유보",
                )

                _ts_gain, _ts_loss = calc_treasury_stock_disposal(
                    booked_gain=mi.treasury_stock_disposal_gain,
                    booked_loss=mi.treasury_stock_disposal_loss,
                )
                result.treasury_stock_gain_excluded = _ts_gain
                result.treasury_stock_loss_disallowed = _ts_loss
                _add_detail(
                    "자기주식처분손익", _ts_gain + _ts_loss, "법§15, §17",
                    [f"손익계상 처분이익 {_ts_gain:,}원 → 익금불산입",
                     f"손익계상 처분손실 {_ts_loss:,}원 → 손금불산입"],
                    reason="3단계에서 자기주식 처분손익 계상액을 입력 → 자본거래 성격의 손익을 세무조정",
                    tax_basis="자기주식 처분손익은 자본거래 조정",
                    disposition="기타",
                )

                _pp_deduct, _pp_excess = calc_proper_purpose_reserve(
                    booked_reserve=mi.proper_purpose_reserve_booked,
                    deductible_limit=mi.proper_purpose_reserve_limit,
                )
                result.proper_purpose_reserve_deduction = _pp_deduct
                result.proper_purpose_reserve_excess = _pp_excess
                _add_detail(
                    "고유목적사업준비금", _pp_deduct + _pp_excess, "법§29",
                    [f"설정액 {mi.proper_purpose_reserve_booked:,}원, 법정 한도 "
                     f"{mi.proper_purpose_reserve_limit:,}원",
                     f"손금산입 {_pp_deduct:,}원 · 한도초과 손금불산입 {_pp_excess:,}원"],
                    reason="3단계에서 비영리법인 고유목적사업준비금 설정액과 법정 한도 입력",
                    book=mi.proper_purpose_reserve_booked, tax=_pp_deduct,
                    tax_basis="법§29 한도 내 손금산입",
                    disposition="△유보/유보",
                )

                # 임원 상여 한도초과 (법§26, 영§43②) — 건별 질문형(임원 게이트·지급기준 초과)
                from src.ui.review_specs import officer_bonus_spec
                _bonus_results = build_results(
                    officer_bonus_spec(), (mi.review_answers or {}).get("임원 상여금 한도초과", []))
                if _bonus_results:
                    result.officer_bonus_excess = sum(r.amount for r in _bonus_results)
                    _add_detail("임원 상여금 한도초과", result.officer_bonus_excess, "영§43②",
                                [f"한도초과 합계 {result.officer_bonus_excess:,}원 — {len(_bonus_results)}건",
                                 "정관·주총·이사회 결의 급여지급기준 초과분(기준 없으면 전액). 직원은 미적용"],
                                reason="3단계에서 임원여부·지급기준 한도 입력 → 기준 초과 상여 손금불산입",
                                book=0, tax=result.officer_bonus_excess,
                                tax_basis="정관·주총 결의 급여지급기준 초과 (영§43②)",
                                disposition="상여")
                elif mi.officer_bonus_paid > 0:
                    result.officer_bonus_excess = calc_officer_bonus_excess(
                        paid_bonus=mi.officer_bonus_paid,
                        approved_limit=mi.officer_bonus_limit,
                    )
                    _add_detail("임원 상여금 한도초과", result.officer_bonus_excess, "영§43②",
                                [f"지급액 {mi.officer_bonus_paid:,}원 − 정관·주총 한도 {mi.officer_bonus_limit:,}원 = {result.officer_bonus_excess:,}원",
                                 "근거 자료: 3단계 수기 입력 (임원 명단·한도)"],
                                reason="3단계에서 임원으로 선택한 거래처의 상여 계정 분개를 자동 합산 "
                                       "(출처 계정과목·집계 내역은 3단계 임원 인건비 화면에 표시) — 입력 한도 초과분",
                                book=mi.officer_bonus_paid, tax=mi.officer_bonus_limit,
                                tax_basis=f"정관·주총 결의 상여 한도 {mi.officer_bonus_limit:,}원 (영§43②)",
                                disposition="상여")

                # 임원 퇴직금 한도초과 (법§26, 영§44④⑤) — 건별 질문형(정관규정 우선 분기)
                from src.ui.review_specs import officer_retirement_spec
                _ret_results = build_results(
                    officer_retirement_spec(), (mi.review_answers or {}).get("임원 퇴직금 한도초과", []))
                if _ret_results:
                    result.officer_retirement_excess = sum(r.amount for r in _ret_results)
                    _add_detail("임원 퇴직금 한도초과", result.officer_retirement_excess, "영§44④⑤",
                                [f"한도초과 합계 {result.officer_retirement_excess:,}원 — {len(_ret_results)}건",
                                 "정관 규정 있으면 정관금액 한도(영§44④1호·⑤), 없으면 직전1년 총급여×1/10×근속(2호)"],
                                reason="3단계에서 정관 퇴직급여 규정 유무 → 규정액 또는 법정한도(총급여×1/10×근속) "
                                       "기준으로 초과분 산정 (정관규정 우선)",
                                book=0, tax=result.officer_retirement_excess,
                                tax_basis="정관규정 우선, 없으면 총급여×1/10×근속 한도 (영§44④⑤)",
                                disposition="상여")
                elif mi.officer_retirement_paid > 0 and mi.officer_retirement_last_salary > 0:
                    # 레거시 폴백 (정관 분기 없음)
                    result.officer_retirement_excess = calc_officer_retirement_excess(
                        paid_amount=mi.officer_retirement_paid,
                        tenure_years=mi.officer_retirement_tenure,
                        last_salary=mi.officer_retirement_last_salary,
                    )
                    _add_detail("임원 퇴직금 한도초과", result.officer_retirement_excess, "영§44④",
                                [f"한도 = 직전 1년 총급여 {mi.officer_retirement_last_salary:,}원 × 10% × 근속 {mi.officer_retirement_tenure}년",
                                 f"지급액 {mi.officer_retirement_paid:,}원 − 한도 = {result.officer_retirement_excess:,}원"],
                                reason="3단계에서 임원으로 선택한 거래처의 퇴직급여 계정 분개를 자동 합산 — "
                                       "정관 규정 없을 때의 법정 한도(총급여×10%×근속) 초과분",
                                book=mi.officer_retirement_paid,
                                tax=mi.officer_retirement_paid - result.officer_retirement_excess,
                                tax_basis=f"직전 1년 총급여 {mi.officer_retirement_last_salary:,}원 × 10% × 근속 {mi.officer_retirement_tenure}년 = 손금인정 한도 (영§44④)",
                                disposition="상여")

                # 업무용승용차 (법§27의2, 영§50의2) — 차량별 한도 적용 (800만·1,500만은 차량 단위)
                if agg.vehicle_expense > 0 or mi.vehicle_depreciation > 0:
                    # 3단계에서 '업무용승용차 해당'으로 체크된 차량운반구 자산
                    _veh_assets = [
                        a for a in loader.fixed_assets
                        if mi.vehicle_asset_checks.get(a.asset_code)
                    ]
                    _veh_results = []
                    _veh_matched: dict = {}
                    _veh_common = 0
                    if _veh_assets:
                        # 관련비용(차량유지비)을 차량번호로 차량별 귀속 — 자산명의 차량번호와 일치하는 분개는
                        # 해당 차량에 정확히 귀속하고, 차량번호 식별불가(공통·개인차량·미기재)·등록외 차량분은
                        # 감가상각비율로 안분한다(총액 = agg.vehicle_expense 보존, 세무조정 금액 불변).
                        from src.rules.vehicle_match import attribute_by_vehicle, allocate_other_expense
                        _veh_pool = agg.detail_lines.get("업무용승용차 관련비용") or []
                        _per = attribute_by_vehicle(_veh_assets, _veh_pool)
                        _veh_matched = {
                            a.asset_code: sum(int(l.debit or 0) for l in _per.get(a.asset_code, []))
                            for a in _veh_assets
                        }
                        _veh_common = max(0, agg.vehicle_expense - sum(_veh_matched.values()))
                        _alloc = allocate_other_expense(_veh_assets, _veh_pool, agg.vehicle_expense)
                        for a in _veh_assets:
                            _veh_results.append(calc_vehicle(
                                vehicle_id=a.asset_name or a.asset_code,
                                depreciation=a.company_depr,
                                other_expense=_alloc[a.asset_code],
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
                    # 감가상각 한도초과분은 유보(이월손금, 법§27의2③) — 개인사용분(사외유출)과 처분 분리
                    result.vehicle_depr_excess = sum(v.depreciation_limit_excess for v in _veh_results)

                    _limit_label = "특정법인 400만원, 영§50의2⑮" if is_spec else "800만원"
                    _veh_formula = [
                        f"차량별 한도 적용 (영§50의2 — 감가상각 {_limit_label}·운행기록부 미작성 한도는 차량 단위)",
                    ]
                    if not mi.vehicle_has_insurance:
                        _veh_formula.append(
                            "⚠ 업무전용보험 미가입 → 해당 차량 관련비용 전액 손금불산입 (영§50의2④1호). "
                            "보험 가입 여부는 차량별로 다를 수 있으니 3단계에서 확인하세요"
                        )
                    for _vi, v in enumerate(_veh_results):
                        _rel = v.depreciation + v.other_expense
                        if not v.has_insurance:
                            _line = f"· {v.vehicle_id}: 관련비용 {_rel:,}원 전액 손금불산입 (보험 미가입)"
                        else:
                            _ratio_src = "입력값" if v.has_logbook else f"min(1, 한도 {v.no_logbook_limit:,}÷관련비용)"
                            # 기타비용 = 차량번호 매칭분 + 공통 안분분 (자산별 귀속일 때 분해 표시)
                            if _veh_assets and _vi < len(_veh_assets):
                                _m = _veh_matched.get(_veh_assets[_vi].asset_code, 0)
                                _cs = v.other_expense - _m
                                _other_src = f"기타 {v.other_expense:,} (차량번호매칭 {_m:,} + 공통안분 {_cs:,})"
                            else:
                                _other_src = f"기타 {v.other_expense:,}"
                            _line = (f"· {v.vehicle_id}: 관련비용 {_rel:,}원 "
                                     f"(상각 {v.depreciation:,} + {_other_src}) · "
                                     f"업무사용 {v.business_use_ratio:.0%} [{_ratio_src}] · "
                                     f"개인사용 부인 {v.personal_use_disallowed:,} + 상각한도초과 {v.depreciation_limit_excess:,}")
                        _veh_formula.append(_line)
                    _veh_formula.append(
                        f"합계 손금불산입 {result.vehicle_disallowed:,}원 "
                        "(상각한도초과분은 유보·이월, 개인사용분은 사외유출)"
                    )
                    _veh_formula.append(
                        f"※ 관련비용은 적요·차량번호로 차량별 귀속(매칭 {sum(_veh_matched.values()):,}원) 후, "
                        f"차량번호 식별불가 공통분(개인차량·미기재 포함)·등록외 차량분 {_veh_common:,}원을 "
                        "감가상각비율로 안분합니다 — 총액은 보존됩니다(세무조정 금액 불변). "
                        "차량별 실제 유지비·보험이 다르면 3단계에서 보정"
                    )
                    # 근거분개 표시 — 계산에 포함된 관련비용 풀 전체를 표시한다.
                    # 등록 차량 외 번호가 식별된 분개는 차량별 직접매칭은 하지 않고 공통 안분 대상으로 둔다.
                    from src.rules.vehicle_match import registered_plates, filter_vehicle_lines
                    _veh_pool = agg.detail_lines.get("업무용승용차 관련비용") or []
                    _veh_plates = registered_plates(_veh_assets)
                    _veh_kept, _veh_foreign = filter_vehicle_lines(_veh_pool, _veh_plates)
                    if _veh_foreign:
                        _veh_formula.append(
                            f"※ 근거분개 표시에서 등록 차량({len(_veh_plates)}대) 외 다른 차량번호가 적요·차량번호에 "
                            f"식별된 분개 {len(_veh_foreign):,}건은 특정 차량에 직접 귀속하지 않고 공통 안분에 포함했습니다 — "
                            "해당 분개가 업무용승용차 관련비용인지 별도 확인이 필요할 수 있습니다."
                        )
                    _veh_related = sum(v.depreciation + v.other_expense for v in _veh_results)
                    _add_detail("업무용승용차 관련비용", result.vehicle_disallowed, "법§27의2, 영§50의2",
                                _veh_formula, _veh_pool,
                                reason="3단계에서 업무용승용차로 체크한 차량운반구 자산별로 영§50의2 한도를 "
                                       "각각 적용(한도 풀링 방지). 보험·운행기록부·업무사용비율은 3단계 입력 적용. "
                                       "증빙불비 판정이 아니라 업무사용비율·한도 조정입니다",
                                book=_veh_related,
                                tax=_veh_related - result.vehicle_disallowed,
                                tax_basis="차량별 업무사용비율 적용 + 감가상각 800만원(특정법인 400만원) 한도 (영§50의2)",
                                disposition="상여 등(개인사용분) / 유보(상각한도초과분)")

                # 지급이자 손금불산입 (법§28) — 직접 입력 금액
                result.interest_unknown_creditor = mi.interest_unknown_creditor
                result.interest_nonreal_name = mi.interest_nonreal_name
                result.interest_construction = mi.interest_construction
                _add_detail("채권자불분명 사채이자", mi.interest_unknown_creditor, "법§28①1호",
                            ["채권자가 불분명한 사채의 이자 → 전액 손금불산입 (원천세 상당액 외 대표자 상여 처분)",
                             "근거 자료: 3단계 지급이자 분류 표에서 '채권자불분명'으로 분류된 분개 합계"],
                            reason="3단계에서 이자비용 전체 중 '채권자불분명'으로 분류한 라인 합계 — "
                                   "나머지 일반 이자비용은 조정 없이 손금 인정",
                            book=mi.interest_unknown_creditor, tax=0,
                            tax_basis="채권자 불분명 사채이자 손금 불인정 (법§28①1호, 전액)",
                            disposition="대표자상여 등")
                _add_detail("비실명 채권·증권이자", mi.interest_nonreal_name, "법§28①2호",
                            ["소득세법 §16①1·2·5·8호 채권·증권의 이자·할인액 중 지급받은 자가 불분명한 것 "
                             "→ 전액 손금불산입 (원천세 상당액 외 대표자 상여 처분)",
                             "근거 자료: 3단계 지급이자 분류 표에서 '비실명 채권·증권이자'로 분류된 분개 합계"],
                            reason="채권자불분명 사채이자(1호)와 별개의 독립 손금불산입 항목 (법§28①2호)",
                            book=mi.interest_nonreal_name, tax=0,
                            tax_basis="비실명 채권·증권이자 손금 불인정 (법§28①2호, 전액)",
                            disposition="대표자상여 등")
                _add_detail("건설자금이자", mi.interest_construction, "법§28①3호, 영§52",
                            ["사업용 유형자산 건설에 충당한 차입금 이자 → 손금불산입 (자본화, 유보)",
                             "근거 자료: 3단계 지급이자 분류 표에서 '건설자금이자'로 분류된 분개 합계"],
                            reason="3단계에서 이자비용 전체 중 '건설자금이자'로 분류한 라인 합계 — "
                                   "나머지 일반 이자비용은 조정 없이 손금 인정",
                            book=mi.interest_construction, tax=0,
                            tax_basis="건설중 자산 취득원가에 자본화 → 당기 손금 불인정 (법§28①3호, 영§52)",
                            disposition="유보")

                # 업무무관자산 지급이자 (법§28①4호, 영§53②③ — 적수 기준)
                # 분자 적수 = 업무무관자산 적수(가목, 영§49) + 특수관계인 가지급금 적수(나목, 영§53①)
                # 업무무관자산 적수 — 체크된 계정별로 B/S 기초잔액 + 분개장 당기 증감 일별 계산
                _nonbiz_jeoksu = 0
                _nonbiz_jeoksu_src = []
                for _nba in (mi.non_business_assets or []):
                    _nba_kw = (str(_nba.get("계정명", "")).replace(" ", ""),)
                    if not _nba_kw[0]:
                        continue
                    # 계정 세부명세에서 거래처 일부만 업무무관으로 선택한 경우(전체계정=False)는
                    # 계정 전체 적수가 아니라 선택 금액×일수로 근사한다 (과대계상 방지).
                    if not _nba.get("전체계정", True):
                        _nba_j = 0
                    else:
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
                            - mi.interest_unknown_creditor - mi.interest_nonreal_name
                            - mi.interest_construction
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
                            [f"기준 지급이자 = 이자비용 총액 {agg.interest_expense:,}원 − 채권자불분명 {mi.interest_unknown_creditor:,}원 − 비실명 채권·증권 {mi.interest_nonreal_name:,}원 − 건설자금 {mi.interest_construction:,}원 = {_base_int:,}원",
                             f"분자 적수 = 업무무관자산 적수 {_nonbiz_jeoksu:,} (가목·영§49 — " + ("; ".join(_nonbiz_jeoksu_src[:4]) or f"잔액 × {_fy_d}일") + ") + 가지급금 적수 " + f"{_loan_jeoksu_total:,} (분개장 일별 계산·가수금 상계 후, 나목·영§53①)",
                             f"비율 = min(1, 분자 적수 {_nb_numer_j:,} ÷ 차입금 적수 {_debt_jeoksu:,}) = {_nb_ratio:.1%} ({_debt_jeoksu_src})",
                             f"손금불산입 = {_base_int:,}원 × {_nb_ratio:.1%} = {result.interest_non_business:,}원",
                             f"체크된 업무무관자산: {_nb_names}" if _nb_names else "",
                             "※ 적수는 분개장 거래 날짜 기준 일별 계산 (영§53③ — 동일인 가수금 상계 적용)"],
                            agg.detail_lines.get("이자비용"),
                            reason="3단계에서 업무무관자산 체크(계정별 명세) + 특수관계인 가지급금 체크(분개장)의 "
                                   "적수 비율만큼 지급이자 손금불산입 — 가지급금은 인정이자와 동시 적용됨 (별개 조정)",
                            book=_base_int,
                            tax=_base_int - result.interest_non_business,
                            tax_basis=f"기준 지급이자 {_base_int:,}원 × 업무무관·가지급금 적수 비율 {_nb_ratio:.1%} 손금불산입 (영§53②③)",
                            disposition="기타사외유출",
                        )
                    else:
                        st.info(
                            "업무무관자산·가지급금이 체크되었으나 차입금 적수를 계산하지 못해 "
                            "지급이자 손금불산입(법§28①4호)을 계산하지 못했습니다 — "
                            "계정별명세서·재무상태표 업로드 또는 3단계 간주임대료 차입금 입력 후 재계산하세요."
                        )

                # 부당행위계산 부인 (법§52, 영§88③·89⑤) — 건별 질문형 입력
                # 3단계에서 건별로 거래유형·시가·거래가액·귀속자를 입력 → 영§88③ 게이트 통과분만
                from src.ui.review_specs import unfair_transaction_spec
                _unfair_spec = unfair_transaction_spec()
                _unfair_results = build_results(
                    _unfair_spec, (mi.review_answers or {}).get("부당행위계산 부인", []),
                )
                # 분개 미매칭 시 레거시 총액 폴백(검토필요 처분)
                _unfair_total = sum(r.amount for r in _unfair_results)
                if not _unfair_results and mi.unfair_transaction_amount:
                    _unfair_total = int(mi.unfair_transaction_amount)
                result.unfair_transaction = _unfair_total
                result.unfair_transaction_lines = [
                    {"amount": r.amount, "disposition": r.disposition,
                     "basis": r.legal_basis, "ref": r.line_ref}
                    for r in _unfair_results
                ]
                if _unfair_results:
                    _disp_brief = " · ".join(
                        f"{r.disposition} {r.amount:,}" for r in _unfair_results)
                    _add_detail(
                        "부당행위계산 부인", _unfair_total, "법§52, 영§88③, 영§89⑤",
                        [f"건별 부인액 합계 {_unfair_total:,}원 — {len(_unfair_results)}건",
                         f"건별 소득처분: {_disp_brief}",
                         "영§88③: 차액 ≥ 3억 또는 시가 5%(1·3·6·7·9호) — 미달 건은 자동 제외",
                         "금전 대여(영§88①6호)는 가지급금 인정이자에서 계산 — 중복 아님",
                         "근거 자료: 3단계 '부당행위계산 부인' 건별 질문 입력"],
                        reason="3단계에서 특수관계인 거래를 건별로 검토 — 거래유형·시가·거래가액·"
                               "귀속자 입력으로 부인액·소득처분 결정(영§88③ 게이트 적용)",
                        book=0, tax=_unfair_total,
                        tax_basis="고가매입·저가양도 등 시가차액 익금산입, 건별 소득처분 (영§88③·89⑤)",
                        disposition="건별 (배당·상여·기타사외유출)",
                    )
                elif _unfair_total:
                    _add_detail(
                        "부당행위계산 부인", _unfair_total, "법§52, 영§88, 영§89⑤",
                        ["(총액 폴백) 분개 미매칭 — 3단계 총액 입력분",
                         "적용 기준: 차액 ≥ 3억원 또는 시가의 5% 이상 (영§88③)"],
                        reason="건별 입력이 없어 총액 폴백 사용 — 소득처분 건별 구분 권장",
                        book=0, tax=_unfair_total,
                        tax_basis="시가차액 익금산입 (영§89⑤)",
                        disposition="검토필요",
                    )

                # 의제배당 (법§16①) — 건별 질문형. 사유별 산식·상법§459 게이트.
                from src.ui.review_specs import deemed_dividend_spec
                _dd_results = build_results(
                    deemed_dividend_spec(), (mi.review_answers or {}).get("의제배당", []))
                result.deemed_dividend = sum(r.amount for r in _dd_results)
                result.deemed_dividend_lines = [
                    {"amount": r.amount, "disposition": r.disposition,
                     "basis": r.legal_basis, "ref": r.line_ref}
                    for r in _dd_results]
                if _dd_results:
                    _add_detail(
                        "의제배당", result.deemed_dividend, "법§16①",
                        [f"건별 익금산입 {result.deemed_dividend:,}원 — {len(_dd_results)}건",
                         "사유별: 감자·해산·합병·분할=교부재산−취득가액 / 무상증자=교부주식가액 전부",
                         "상법§459① 자본준비금·재평가적립금 자본전입은 의제배당 제외(자동)"],
                        reason="3단계에서 감자·합병·무상증자 등 사유와 교부재산·취득가액 입력 → "
                               "법§16① 사유별 산식으로 의제배당 익금산입",
                        book=0, tax=result.deemed_dividend,
                        tax_basis="법§16① 사유별 의제배당 익금산입",
                        disposition="-",
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
                    _auto_items.add("부당행위계산 부인")
                if mi.stock_comp_booked_expense or mi.stock_comp_deductible_amount:
                    _auto_items.add("주식매수선택권·주식기준보상 비용")
                if mi.construction_book_revenue or mi.construction_tax_revenue:
                    _auto_items.add("작업진행률 수익인식")
                if mi.treasury_stock_disposal_gain or mi.treasury_stock_disposal_loss:
                    _auto_items.add("자기주식처분손익")
                if mi.proper_purpose_reserve_booked or mi.proper_purpose_reserve_limit:
                    _auto_items.add("고유목적사업준비금")
                if mi.rental_deposit > 0:
                    _auto_items.add("간주임대료")
                if div_income > 0:
                    _auto_items.add("수입배당금 익금불산입")
                if mi.officer_bonus_paid > 0:
                    _auto_items.add("임원 상여금 한도")
                if mi.officer_retirement_paid > 0:
                    _auto_items.add("임원 퇴직급여 한도")
                if (mi.interest_unknown_creditor or mi.interest_nonreal_name
                        or mi.interest_construction or result.interest_non_business):
                    _auto_items.add("지급이자 손금불산입")
                if mi.donation_special or mi.donation_general or mi.donation_nondesignated:
                    _auto_items.add("기부금 한도")
                _auto_items.add("유가증권 평가손익")  # 분개장 집계로 항상 자동
                if result.inventory_adjustment:
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
                                   "현행 영§60 한도가 0%이므로 설정액 전액이 한도초과 (퇴직연금 부담금 손금산입은 아래에서 별도 계산)",
                            book=rall.company_balance, tax=rall.statutory_limit,
                            tax_basis="세법상 퇴직급여충당금 한도 (현행 누적한도 0%, 영§60)",
                            disposition="유보")

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
                                   "확정기여형(DC) 부담금은 영§44의2③ 전액 손금 — 별도 검토",
                            book=0, tax=pdr.deduction,
                            tax_basis=f"min(추계액 한도 {pdr.estimate_limit:,}원, 예치금 {pdr.fund_balance:,}원) − 직전 손금누계 {pdr.prior_deducted:,}원 (영§44의2④)",
                            disposition="△유보")

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
                                   "대손실적률로 한도 계산 — 한도 초과분만 손금불산입",
                            book=bdall.company_balance, tax=bdall.limit,
                            tax_basis=f"채권잔액 {bdall.receivable_balance:,}원 × max(1%, 대손실적률 {bdall.actual_bad_rate:.2%}) = 손금인정 한도 (영§61)",
                            disposition="유보")

                # ── 전기 유보 당기 추인 (회계사 명시 입력 — opt2) ───────────────────
                #    유보 추인 → 손금산입(△유보) / △유보 추인 → 익금산입(유보).
                #    감가상각 부인누계(엔진 자동 추인 = depreciation_approved)·기부금 이월은
                #    제외 (이중계상 방지). 대손충당금 총액법 환입(법§34③) 등은 여기 포함.
                _rev_deduct = int(getattr(mi, "prior_reserve_reversal_deduct", 0) or 0)
                _rev_add = int(getattr(mi, "prior_reserve_reversal_add", 0) or 0)
                result.prior_reserve_reversal_deduct = _rev_deduct
                result.prior_reserve_reversal_add = _rev_add
                _add_detail(
                    "전기 유보 추인 — 손금산입(△유보)", _rev_deduct, "법§34③ 등",
                    ["전기 유보(대손충당금 총액법 한도초과 등)의 당기 추인 — 손금산입",
                     "근거: 3단계 수기 입력 '전기 유보 당기 추인'",
                     "※ 감가상각 부인누계 추인은 엔진 자동 반영 — 여기서 제외"],
                    reason="전기에 손금불산입(유보)된 금액이 당기에 추인되어 손금산입(△유보)되는 회계사 확정분",
                    disposition="△유보")
                _add_detail(
                    "전기 △유보 추인 — 익금산입(유보)", _rev_add, "영§106 등",
                    ["전기 △유보(익금불산입)의 당기 추인 — 익금산입",
                     "근거: 3단계 수기 입력 '전기 유보 당기 추인'"],
                    reason="전기에 익금불산입(△유보)된 금액이 당기에 추인되어 익금산입(유보)되는 회계사 확정분",
                    disposition="유보")

                # ── 기부금 한도 (법§24②2호·③2호) — 모든 조정 후 차가감소득금액 기준 ──
                _carryforward_pairs = [
                    (item["year"], item["amount"])
                    for item in mi.carryforward_losses
                    if item.get("year") and item.get("amount")
                ]
                _don_special, _don_general = mi.donation_special, mi.donation_general
                _don_nondes = mi.donation_nondesignated
                # 전기 이월 기부금 (법§24⑤, 10년 내, 발생연도순) — 우선공제 대상
                _cf_special = eligible_donation_carryforward(
                    mi.donation_carryforwards, fy_end_val.year, "특례")
                _cf_general = eligible_donation_carryforward(
                    mi.donation_carryforwards, fy_end_val.year, "일반")
                _prior_special = sum(x["amount"] for x in _cf_special)
                _prior_general = sum(x["amount"] for x in _cf_general)
                _donation_next_cf: list[dict] = []
                _donation_status: dict | None = None
                if (_don_special + _don_general + _don_nondes
                        + _prior_special + _prior_general) > 0:
                    # 기준소득금액 = 차가감소득금액 + 특례 + 일반기부금 (비지정 제외)
                    #   차가감소득금액 = 당기순이익 + (기부금 외 가산조정) − 차감조정
                    # ── 순서 의존성: 기부금은 다른 모든 조정 후에 계산해야 한다.
                    #    이 시점 donation_excess·donation_carryforward_deduction=0 이어야
                    #    total_add_back/deduct이 기부금 제외분이 된다.
                    #    신규 가산/차감조정을 이 블록 '뒤'에 추가하면 base에서 누락되므로 금지.
                    assert result.donation_excess == 0, "기부금은 다른 조정 후 마지막에 계산"
                    assert result.donation_carryforward_deduction == 0
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
                        prior_special_carryforward=_prior_special,
                        prior_general_carryforward=_prior_general,
                    )
                    result.donation_excess = _don.total_disallowed
                    result.donation_carryforward_deduction = _don.carryforward_deduction
                    # 차기 이월액 (미공제 이월분 선발생분부터 소진 + 당기 한도초과) — .taxproj 승계
                    _donation_next_cf = (
                        roll_forward(_cf_special, _don.special_carryover_used,
                                     _don.special_excess, fy_end_val.year, "특례")
                        + roll_forward(_cf_general, _don.general_carryover_used,
                                       _don.general_excess, fy_end_val.year, "일반")
                    )
                    # 기부금조정명세서(별지 제21호) 빌더 입력 — 영속 저장 (전체 이월: 소멸분 포함)
                    _donation_status = {
                        "base_income": _base_income, "loss_deduction": _cf_loss_ded,
                        "special_donation": _don_special, "general_donation": _don_general,
                        "nondesignated": _don_nondes,
                        "special_limit": _don.special_limit, "general_limit": _don.general_limit,
                        "general_rate": 0.10,
                        "special_carryover_used": _don.special_carryover_used,
                        "general_carryover_used": _don.general_carryover_used,
                        "special_excess": _don.special_excess, "general_excess": _don.general_excess,
                        "carryforward_deduction": _don.carryforward_deduction,
                        "total_disallowed": _don.total_disallowed,
                        "prior_carryforwards": list(mi.donation_carryforwards or []),
                        "fy_end_year": fy_end_val.year,
                    }
                    if _don.total_disallowed:
                        _add_detail("기부금 한도초과·비지정", _don.total_disallowed, "법§24",
                                    [f"기준소득금액 = 차가감소득금액 + 특례·일반기부금 = {_base_income:,}원 "
                                     f"(당기순이익 {_net_income_input:,} + 가산조정 {result.total_add_back:,} "
                                     f"− 차감조정 {result.total_deduct:,} + 기부금 {_don_special + _don_general:,})",
                                     f"이월결손금 공제 {_cf_loss_ded:,}원 차감 → 한도기준 {max(0, _base_income - _cf_loss_ded):,}원",
                                     f"특례기부금 {_don_special:,}원 (한도 50% = {_don.special_limit:,}원, "
                                     f"이월 우선공제 {_don.special_carryover_used:,}원 후 당기 한도초과 {_don.special_excess:,}원) · "
                                     f"일반기부금 {_don_general:,}원 (한도 10% = {_don.general_limit:,}원, "
                                     f"이월 우선공제 {_don.general_carryover_used:,}원 후 당기 한도초과 {_don.general_excess:,}원)",
                                     f"비지정기부금 {_don_nondes:,}원 → 전액 손금불산입",
                                     "근거: 3단계 수기 입력의 기부금 분류 (법§24②2호·③2호·⑥)"],
                                    reason="기부금 한도는 다른 모든 세무조정 후 차가감소득금액에 특례·일반기부금을 "
                                           "가산한 기준소득금액에서 이월결손금을 차감해 계산. 법§24⑥ 이월분 우선공제 후 "
                                           "당기분 한도초과분 + 비지정 전액 = 손금불산입",
                                    book=_don_special + _don_general + _don_nondes,
                                    tax=(_don_special + _don_general + _don_nondes) - _don.total_disallowed,
                                    tax_basis=f"특례 한도 {_don.special_limit:,}원(50%) + 일반 한도 {_don.general_limit:,}원(10%), 비지정 전액부인 (법§24)",
                                    disposition="기타사외유출")
                    if _don.carryforward_deduction:
                        _add_detail(
                            "기부금 이월액 당기 손금산입", _don.carryforward_deduction, "법§24⑤⑥",
                            [f"전기 이월 기부금(특례 {_prior_special:,}원 · 일반 {_prior_general:,}원) 중 "
                             f"당기 한도 내 우선공제 (법§24⑥)",
                             f"특례 이월 공제 {_don.special_carryover_used:,}원 (한도 {_don.special_limit:,}원) · "
                             f"일반 이월 공제 {_don.general_carryover_used:,}원 (한도 {_don.general_limit:,}원)",
                             f"미공제 이월 잔액 → 차기 이월: 특례 {_don.special_carryover_remaining:,}원 · "
                             f"일반 {_don.general_carryover_remaining:,}원 (공제기한 10년 내, 법§24⑤)",
                             "근거: 3단계 수기 입력의 전기 이월 기부금(발생연도별)"],
                            reason="전기 한도초과로 이월된 기부금을 당기 한도 내에서 당기 지출분보다 먼저 손금산입 (법§24⑥)",
                            book=0, tax=-_don.carryforward_deduction,
                            tax_basis="이월 기부금 당기 공제 = 손금산입(차감조정, 처분 기타) (법§24⑤⑥)",
                            disposition="기타")

                st.session_state.calc_details = calc_details
                st.session_state.tax_result = result

            # 이월결손금 쌍은 기부금 한도 계산과 동일 소스 사용 (위 _carryforward_pairs)
            carryforward = _carryforward_pairs
            # 출발값은 사전 확인된 값 사용 (자동 인식 또는 수기 입력 — 0원은 명시적 확인 시만)
            net_income = _net_income_input
            if _auto_ni == 0 and _manual_ni != 0:
                st.info(f"당기순이익 수기 입력값 {_manual_ni:,}원으로 계산했습니다 — 검토조서에 출처를 기록하세요.")
            # 세액공제·감면 (3단계 입력) → TaxCredit 리스트. 최저한세 적용대상 여부 포함.
            _tax_credits = [
                TaxCredit(
                    name=str(_tc.get("name", "")),
                    amount=int(_tc.get("amount", 0) or 0),
                    subject_to_min_tax=bool(_tc.get("subject_to_min_tax", True)),
                    farm_surtax_taxable=bool(_tc.get("farm_surtax_taxable", False)),
                )
                for _tc in (mi.tax_credit_items or [])
                if int(_tc.get("amount", 0) or 0) > 0
            ]
            # 토지등 양도소득에 대한 법인세 (법§55의2) — 일반 법인세에 추가 납부
            _land_tax = calc_land_transfer_tax(
                int(mi.land_transfer_income or 0),
                mi.land_transfer_type,
                unregistered=bool(mi.land_transfer_unregistered),
            )
            compute_all(
                result,
                net_income=net_income,
                carryforward_losses=carryforward,
                fiscal_year_end=fy_end_val,
                tax_credits=_tax_credits,
                surtax=int(mi.surtax_amount or 0),
                prepaid_tax=int(mi.prepaid_tax_amount or 0),
                land_transfer_tax=_land_tax,
                non_taxable=int(mi.non_taxable_income or 0),
                income_deduction=int(mi.income_deduction or 0),
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
            # 회계사 직접 입력 세무조정 중 유보/△유보 — 차기 전기이월 유보로 승계 (을표 코드와 일치)
            _new_reserves += [
                {"code": f"[수기] {str(c.get('name', '')).strip()}",
                 "amount": int(c.get("amount", 0) or 0),
                 "disposition": c.get("disposition")}
                for c in (result.custom_adjustment_lines or [])
                if c.get("disposition") in ("유보", "△유보") and int(c.get("amount", 0) or 0)
            ]
            # 의제배당 무상증자·자본전입형 유보 — 차기 주식 양도 시 추인되므로 전기이월 유보로 승계.
            #   을표 build_reserve_status의 흡수 코드와 동일하게 맞춰 opening 누적이 끊기지 않게 한다.
            _dd_yubo_next = sum(
                int(_d.get("amount", 0) or 0)
                for _d in (getattr(result, "deemed_dividend_lines", None) or [])
                if str(_d.get("disposition", "")).strip() == "유보"
            )
            if _dd_yubo_next:
                _new_reserves.append({
                    "code": "의제배당(자본전입형) 유보",
                    "amount": _dd_yubo_next, "disposition": "유보",
                })
            proj.tax_adjustments = {
                "fiscal_year_end": str(fy_end_val),
                "net_income": result.net_income,
                "business_income": result.business_income,
                "tax_base": result.tax_base,
                "total_add_back": result.total_add_back,
                "total_deduct": result.total_deduct,
                "depreciation_denial_end": sum(d.denial_end for d in _depr_list),
                "reserves": _new_reserves,   # 차기 '전기 유보' 승계 후보 (당기 발생분)
                # 차기 이월 기부금 (미공제 이월분 + 당기 한도초과, 발생연도별 — 법§24⑤)
                "donation_carryforwards": _donation_next_cf,
                # 기부금조정명세서(별지 제21호) 빌더 입력 (None이면 기부금 없음)
                "donation_status": _donation_status,
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
        _ntx = int(proj.manual_input.non_taxable_income or 0)
        _idd = int(proj.manual_input.income_deduction or 0)
        if _ntx or _idd:
            st.caption(
                f"※ 과세표준 산정 시 비과세소득 {_ntx:,}원·소득공제 {_idd:,}원 차감 "
                "(법§13①2호·3호 — 과세표준및세액조정계산서 105·106란). 당기 미공제분은 소멸(법§13②)."
            )
        if r.land_transfer_tax:
            st.caption(
                f"※ 토지등 양도소득에 대한 법인세 **{r.land_transfer_tax:,}원** (법§55의2) — "
                "일반 법인세에 추가하여 위 차감납부세액에 포함됨 (최저한세·세액공제 대상 아님)."
            )
        if r.farm_surtax:
            st.caption(
                f"※ 농어촌특별세 **{r.farm_surtax:,}원** (감면세액 × 20%, 농특세법§5①) — "
                "법인세와 별도로 신고·납부하며 위 차감납부세액에 포함되지 않습니다."
            )

        # ── 중소기업 결손금 소급공제 환급 (법§72, 영§110) — 독립 카드 (별지15호·소득처분과 무관) ──
        _cur_loss = max(0, -int(r.business_income))
        if mi.loss_carryback_enabled and _cur_loss > 0:
            from src.rules.loss_carryback import compute_loss_carryback_from_manual
            _lcb = compute_loss_carryback_from_manual(
                mi, is_sme=is_sme, fy_start=fy_start, current_loss=_cur_loss)
            # 차기 승계용 — 소급공제 적용 결손금(이월공제 제외 대상). carry_forward_from가 사용.
            if proj.tax_adjustments is None:
                proj.tax_adjustments = {}
            proj.tax_adjustments["loss_carryback_applied_loss"] = (
                int(_lcb.applied_loss) if _lcb.eligible else 0)
            st.divider()
            st.markdown(section_title(
                "중소기업 결손금 소급공제 환급 (법§72)",
                "당기 결손금을 직전 사업연도에 소급하여 법인세를 환급받는 별건 — 별지15호와 무관.",
            ), unsafe_allow_html=True)
            if _lcb.eligible:
                st.metric("환급가능세액 (초안)", f"{_lcb.refund:,.0f}원")
            else:
                st.info("현재 입력으로는 환급 요건 미충족 — 아래 사유를 확인하세요.")
            if _lcb.needs_manual_step2:
                st.warning(
                    "직전 사업연도 세율테이블이 엔진에 미수록되어 **2호((직전 과표−결손금)×직전 세율)를 "
                    "회계사가 직접 입력**해야 합니다. 입력 전까지 환급액은 0으로 보수 처리됩니다.")
            with st.expander("계산내역·근거 (법§72①, 영§110①)", expanded=_lcb.eligible):
                st.markdown(
                    f"- **당기 결손금**: {_cur_loss:,}원 (= max(0, −각사업연도소득))\n"
                    f"- **소급공제 적용 결손금**: {_lcb.applied_loss:,}원 "
                    f"(상한 = min(당기결손금, 직전 과표) = {_lcb.max_carryback_loss:,}원, 영§110⑤)\n"
                    f"- **① 직전 산출세액**(§55의2 토지등양도 제외): {_lcb.step1:,}원\n"
                    f"- **② (직전 과표 − 적용결손금) × 직전 세율**: {_lcb.step2:,}원"
                    + (f" (세율테이블 {_lcb.prior_rate_table_from})" if _lcb.prior_rate_table_from else "")
                    + "\n"
                    f"- **한도**(직전 산출세액 − 직전 공제·감면세액, 영§110①): {_lcb.refund_limit:,}원\n"
                    f"- **환급가능세액** = min(① − ②, 한도) = **{_lcb.refund:,}원**"
                )
                for _msg in _lcb.reasons:
                    st.caption("• " + _msg)
                st.caption(
                    "⚠ 추징 주의(법§72⑤·영§110④): 추후 당기 결손금 경정 감소·직전 경정·중소기업 탈락 시 "
                    "환급세액에 이자상당액(1일 10만분의 22)을 더해 징수됩니다. "
                    "소급공제 신청 여부·금액은 회계사·납세자가 확정하며, 잔여 결손금의 이월공제(법§13①1호)와 "
                    "비교 검토가 필요합니다.")
                st.caption("근거: 법§72(001563/007200)·영§110(003608/011000) — 별지 제68호 소급공제법인세액환급신청서.")

        st.divider()
        st.markdown(section_title(
            "소득금액조정합계표 (별지 제15호서식 구조)",
            "가산조정(익금산입·손금불산입)과 차감조정(손금산입·익금불산입)을 모두 표시합니다.",
        ), unsafe_allow_html=True)
        import pandas as pd

        # ── 소득처분 귀속자 확정 (영§106) — 사외유출 항목만, 미선택 시 '검토필요' ──
        _disp_choices = dict((proj.tax_adjustments or {}).get("disposition_choices", {}))
        if (r.deemed_interest or r.unfair_transaction or r.welfare_disallowed
                or r.vehicle_disallowed or r.interest_unknown_creditor
                or r.interest_nonreal_name or r.officer_bonus_excess
                or r.officer_retirement_excess):
            with st.expander("소득처분 귀속자 확정 (영§106) — 사외유출 항목"):
                st.caption("귀속자: 주주→배당 · 임원·직원→상여 · 법인등→기타사외유출 · 기타→기타소득 · 불분명→대표자상여")
                _opts = ["(미선택)"] + ATTRIBUTION_TYPES

                def _disp_sel(label, key):
                    _cur = _disp_choices.get(key)
                    _v = st.selectbox(
                        label, _opts,
                        index=(_opts.index(_cur) if _cur in _opts else 0),
                        key=f"disp_{key}",
                    )
                    if _v != "(미선택)":
                        _disp_choices[key] = _v
                    else:
                        _disp_choices.pop(key, None)

                for _p in (r.deemed_interest_parties or []):
                    _pnm = str(_p.get("name", ""))
                    _disp_sel(f"가지급금 인정이자 — {_pnm} ({int(_p.get('amount', 0)):,}원)",
                              f"인정이자|{_pnm}")
                # 부당행위 — 건별 입력이 있으면 처분은 3단계에서 건별 결정됨(여기 단일 선택기 숨김)
                if r.unfair_transaction and not getattr(r, "unfair_transaction_lines", None):
                    _disp_sel(f"부당행위계산 부인 ({r.unfair_transaction:,}원)", "부당행위계산 부인")
                    st.caption("※ 자본거래(불공정 합병·증자 등 영§88①8호·8호의2)로 귀속자에게 증여세가 과세되는 "
                               "금액은 귀속자 무관 **기타사외유출**(영§106①3호 자목) — 해당 시 '법인등' 선택")
                elif getattr(r, "unfair_transaction_lines", None):
                    st.caption("부당행위계산 부인 — 소득처분은 3단계 건별 입력에서 결정되어 별지15호에 "
                               "건별 표시됩니다(귀속자별 배당·상여·기타사외유출).")
                if r.welfare_disallowed:
                    _disp_sel(f"복리후생비 열거외 ({r.welfare_disallowed:,}원)", "복리후생비 (열거 외)")
                _veh_personal = r.vehicle_disallowed - r.vehicle_depr_excess
                if _veh_personal:
                    _disp_sel(f"업무용승용차 개인사용분 ({_veh_personal:,}원 · 감가상각 한도초과는 유보 별도)",
                              "업무용승용차 개인사용분")
                # 임원 상여·퇴직 한도초과 — 기본 상여(귀속 임원), 주주임원·이익처분 성격이면 배당 선택
                if r.officer_bonus_excess:
                    _disp_sel(f"임원 상여금 한도초과 ({r.officer_bonus_excess:,}원) — 기본 상여",
                              "임원 상여금 한도초과")
                if r.officer_retirement_excess:
                    _disp_sel(f"임원 퇴직금 한도초과 ({r.officer_retirement_excess:,}원) — 기본 상여",
                              "임원 퇴직금 한도초과")
                if r.interest_unknown_creditor:
                    _wh = st.number_input(
                        f"채권자불분명 사채이자 원천세 상당액 (총 {r.interest_unknown_creditor:,}원 중)",
                        min_value=0, max_value=int(r.interest_unknown_creditor),
                        value=int(_disp_choices.get("채권자불분명 사채이자|원천세", 0)),
                        step=100_000,
                        help="원천세 상당액=기타사외유출, 잔액=대표자상여 (영§106)",
                    )
                    _disp_choices["채권자불분명 사채이자|원천세"] = int(_wh)
                    if _wh == 0:
                        st.caption("⚠ 원천세 상당액 0 → **전액 대표자상여**로 처분됩니다(대표자 종소세 영향). "
                                   "채권자불분명 사채이자는 통상 원천징수세액 상당액이 기타사외유출이니 확인하세요.")
                if r.interest_nonreal_name:
                    _wh2 = st.number_input(
                        f"비실명 채권·증권이자 원천세 상당액 (총 {r.interest_nonreal_name:,}원 중)",
                        min_value=0, max_value=int(r.interest_nonreal_name),
                        value=int(_disp_choices.get("비실명 채권·증권이자|원천세", 0)),
                        step=100_000,
                        help="원천세 상당액=기타사외유출, 잔액=대표자상여 (영§106, 법§28①2호)",
                    )
                    _disp_choices["비실명 채권·증권이자|원천세"] = int(_wh2)
            if proj.tax_adjustments is None:
                proj.tax_adjustments = {}
            proj.tax_adjustments["disposition_choices"] = _disp_choices

        add_items, deduct_items = adjustment_rows(r, _disp_choices)
        _adj_type = adj_type
        col_add, col_ded = st.columns(2, gap="medium")
        with col_add:
            st.markdown(f"**가산조정 — 합계 {r.total_add_back:,}원**")
            st.dataframe(pd.DataFrame(
                [(t, k, f"{v:,}", b, d, _adj_type(k)) for t, k, v, b, d in add_items],
                columns=["구분", "항목", "금액 (원)", "근거", "소득처분", "조정구분"],
            ), width="stretch", hide_index=True)
        with col_ded:
            st.markdown(f"**차감조정 — 합계 {r.total_deduct:,}원**")
            st.dataframe(pd.DataFrame(
                [(t, k, f"{v:,}", b, d, _adj_type(k)) for t, k, v, b, d in deduct_items],
                columns=["구분", "항목", "금액 (원)", "근거", "소득처분", "조정구분"],
            ), width="stretch", hide_index=True)
            st.caption(
                "소득처분은 **후보**입니다 — 귀속자(대표자·주주·임원)에 따라 상여·배당·기타사외유출이 "
                "달라지므로 최종 확인 필요. 결산조정 항목은 장부 계상 여부가 손금 인정의 전제입니다."
            )

        # ── 자본금과적립금조정명세서(을) — 편집 가능 유보 잔액표 (별지 제50호서식(을)) ──
        _depr_end = sum(
            d.denial_end for d in (st.session_state.get("depr_results") or [])
        ) or int((proj.tax_adjustments or {}).get("depreciation_denial_end", 0))
        # 자동 산출 기준선 (감소 보정·수기행 적용 전) — 변경분만 override로 저장하기 위함
        _auto_base = build_reserve_status(
            proj.manual_input.prior_reserves, r, depr_denial_end=_depr_end,
            bad_debt_method=proj.manual_input.bad_debt_method,
        )
        _base_dec = {x["과목"]: x["감소"] for x in _auto_base}
        if _auto_base:
            if proj.tax_adjustments is None:
                proj.tax_adjustments = {}
            _saved = proj.tax_adjustments
            _dec_ov = dict(_saved.get("reserve_decrease_overrides", {}))
            _manual = list(_saved.get("reserve_manual_rows", []))

            st.markdown(section_title(
                "자본금과적립금조정명세서(을) — 유보 잔액 명세 (편집 가능)",
                "전기이월 유보 + 당기 증감 = 기말 유보. ⚠ 검토 항목은 '당기감소(추인)'를 직접 입력해 보정하세요.",
            ), unsafe_allow_html=True)

            # (1) 자동 산출 행 — '당기감소(추인)'만 편집
            _adf = pd.DataFrame([
                {"과목": x["과목"], "기초": x["기초"], "증가": x["증가"],
                 "당기감소(추인)": _dec_ov.get(x["과목"], x["감소"]),
                 "처분": x["처분"], "검토": "⚠" if x["검토"] else ""}
                for x in _auto_base
            ])
            _aedit = st.data_editor(
                _adf,
                column_config={"당기감소(추인)": st.column_config.NumberColumn(
                    "당기감소(추인)", format="%d", help="환입·추인액 — 입력 시 기말이 재계산됩니다")},
                disabled=["과목", "기초", "증가", "처분", "검토"],
                width="stretch", hide_index=True, key="reserve_auto_editor",
            )
            # 자동 기준선과 다른 감소만 override로 저장 (같으면 제거 → 검토 플래그 유지)
            _new_ov = {}
            for _, row in _aedit.iterrows():
                _code = row["과목"]
                _dec = int(row["당기감소(추인)"] or 0)
                if _dec != int(_base_dec.get(_code, 0)):
                    _new_ov[_code] = _dec
            _saved["reserve_decrease_overrides"] = _new_ov

            # (2) 수기 유보 항목 추가 (일시상각·압축기장충당금·준비금 등 — 자동 범위 밖)
            with st.expander("수기 유보 항목 추가 (일시상각·압축기장충당금·준비금 등)"):
                _mdf = pd.DataFrame(
                    _manual or [],
                    columns=["과목", "기초", "증가", "감소", "처분"],
                )
                _medit = st.data_editor(
                    _mdf, num_rows="dynamic",
                    column_config={
                        "기초": st.column_config.NumberColumn("기초", format="%d"),
                        "증가": st.column_config.NumberColumn("당기증가", format="%d"),
                        "감소": st.column_config.NumberColumn("당기감소", format="%d"),
                        "처분": st.column_config.SelectboxColumn("처분", options=["유보", "△유보"]),
                    },
                    width="stretch", hide_index=True, key="reserve_manual_editor",
                )
                _manual = [
                    {"과목": str(row["과목"]).strip(),
                     "기초": int(row["기초"] or 0), "증가": int(row["증가"] or 0),
                     "감소": int(row["감소"] or 0), "처분": str(row["처분"] or "유보")}
                    for _, row in _medit.iterrows() if str(row.get("과목", "")).strip()
                ]
                _saved["reserve_manual_rows"] = _manual

            # (3) 보정·수기행 반영한 최종 표 + 합계
            _reserve_rows = build_reserve_status(
                proj.manual_input.prior_reserves, r, depr_denial_end=_depr_end,
                bad_debt_method=proj.manual_input.bad_debt_method,
                decrease_overrides=_new_ov, manual_rows=_manual,
            )
            _rt = reserve_totals(_reserve_rows)
            _fdf = pd.DataFrame([
                {"과목": x["과목"], "기초잔액": f"{x['기초']:,}", "당기 증가": f"{x['증가']:,}",
                 "당기 감소": f"{x['감소']:,}", "기말잔액": f"{x['기말']:,}", "처분": x["처분"],
                 "검토": "⚠ 추인확인" if x["검토"] else "✓"}
                for x in _reserve_rows
            ])
            st.dataframe(_fdf, width="stretch", hide_index=True)
            rc1, rc2, rc3 = st.columns(3)
            rc1.metric("유보 기말 합계", f"{_rt['유보_기말']:,}원")
            rc2.metric("△유보 기말 합계", f"{_rt['△유보_기말']:,}원")
            rc3.metric("순유보 기말", f"{_rt['순유보_기말']:,}원")
            if any(x["검토"] for x in _reserve_rows):
                st.caption(
                    "⚠ '추인확인' 항목은 당기 추인(감소)이 자동 반영되지 않았습니다 — 위 표에서 직접 입력해 보정하세요."
                )
            # 을표 추인(감소) 합계 ↔ 3단계 '전기 유보 당기 추인' 소득금액 입력 대조
            #   (감가상각 부인누계 추인은 엔진 자동 반영이므로 소득금액 입력에서 제외)
            _ov_sum = sum(
                int(v) for k, v in (_new_ov or {}).items()
                if k != "감가상각 부인누계"
            )
            _mi_rev = (int(proj.manual_input.prior_reserve_reversal_deduct or 0)
                       + int(proj.manual_input.prior_reserve_reversal_add or 0))
            if _ov_sum or _mi_rev:
                if _ov_sum != _mi_rev:
                    st.warning(
                        f"⚠ 정합성 확인 — 을표 추인(감소) 합계 {_ov_sum:,}원(감가상각 제외) ≠ "
                        f"3단계 '전기 유보 당기 추인' 소득금액 입력 {_mi_rev:,}원. "
                        "표 보정과 소득금액 반영이 일치하는지 확인하세요."
                    )
                else:
                    st.caption(f"✓ 을표 추인 합계 {_ov_sum:,}원 = 소득금액 추인 입력 {_mi_rev:,}원 (정합)")

        # ── 기부금조정명세서 (별지 제21호) — 발생연도별 이월·소멸·차기이월 ──
        from src.forms.donation_status import build_donation_status
        _dstat = build_donation_status((proj.tax_adjustments or {}).get("donation_status"))
        if _dstat:
            st.markdown(section_title(
                "기부금조정명세서 (별지 제21호서식)",
                f"한도기준 {_dstat['limit_base']:,}원 — 법§24②③(한도)·⑤⑥(이월 우선공제)",
            ), unsafe_allow_html=True)
            st.dataframe(pd.DataFrame([
                {"구분": c["구분"], "지출액": f"{c['지출액']:,}", "이월 우선공제": f"{c['이월 우선공제']:,}",
                 "손금산입한도": f"{c['손금산입한도']:,}", "한도율": c["한도율"],
                 "당기 한도초과": f"{c['당기 한도초과']:,}"}
                for c in _dstat["limit_calc"]
            ]), width="stretch", hide_index=True)
            if _dstat["carryforward_schedule"]:
                st.caption("발생연도별 이월명세 (당기 소멸 명시 — 법§24⑤ 10년)")
                st.dataframe(pd.DataFrame([
                    {"발생연도": x["year"], "구분": x["type"], "전기말 이월": f"{x['opening']:,}",
                     "당기 공제": f"{x['used']:,}", "당기 소멸": f"{x['expired']:,}",
                     "차기 이월": f"{x['carryover']:,}", "발생구분": x["발생구분"]}
                    for x in _dstat["carryforward_schedule"]
                ]), width="stretch", hide_index=True)
                _bn = _dstat["balance_note"]
                (st.caption if _dstat["balance_ok"] else st.warning)(
                    f"이월 당기공제 {_dstat['carryforward_deduction']:,}원 · "
                    f"당기소멸 {_dstat['expired_total']:,}원 · 차기이월 {_dstat['next_carryforward_total']:,}원 — {_bn}"
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
                    width="stretch", hide_index=True,
                    key="review_memo_editor",
                )
                if proj.tax_adjustments is None:
                    proj.tax_adjustments = {}
                proj.tax_adjustments["review_memos"] = {
                    row["항목"]: row["검토메모"]
                    for _, row in _memo_edit.iterrows() if str(row["검토메모"]).strip()
                }

        # ── 세무 컨설팅 코멘트 (규칙엔진 발굴 — 회계사 채택 후 확정, ADR-002) ──
        from src.rag import enrich_topics_with_references
        _topics = enrich_topics_with_references(build_consulting_topics(
            company=proj.company, manual_input=proj.manual_input,
            result=r, fiscal_year_end=fy_end_val,
        ))
        if _topics:
            st.markdown(section_title(
                "세무 컨설팅 코멘트 (검토 후보)",
                "재무자료·세무조정 결과에서 규칙엔진이 발굴한 자문 후보입니다. "
                "모두 미확정 — 회계사가 요건 검토 후 채택·확정하세요 (AI가 적용을 확정하지 않습니다).",
            ), unsafe_allow_html=True)
            from src.rules.consulting import SCENARIO_DISCLAIMER
            from src.rag.reference_retriever import format_reference
            from src.llm.consultant import _scenario_key
            _narr = st.session_state.get("consulting_narration") or {}
            if st.button("LLM으로 고객용 문장 다듬기 (선택)"):
                from src.llm.consultant import narrate_topics
                with st.spinner("로컬 LLM이 시나리오 문장을 다듬는 중..."):
                    try:
                        _narr = narrate_topics(_topics)
                        st.session_state["consulting_narration"] = _narr
                    except Exception as _e:
                        st.warning(f"LLM 문장화 실패 — 규칙엔진 문장 사용 ({type(_e).__name__})")
            if _narr:
                st.caption("LLM이 다듬은 문장입니다 — 숫자·법령·요건은 규칙엔진 값 그대로, 시나리오 행동의 톤만 변경.")
            _cat_icon = {"리스크": "🔴", "특례·감면": "🟢", "정책": "🔵"}
            for _t in _topics:
                with st.expander(f"{_cat_icon.get(_t.category, '·')} [{_t.category}] {_t.title} · {_t.severity}"):
                    st.markdown(f"**현재상황:** {_t.situation}")
                    st.markdown(f"**근거:** {_t.basis}")
                    st.markdown(f"**결론 — 시나리오** ({SCENARIO_DISCLAIMER})")
                    for _sc in (_t.scenarios or []):
                        _act = _narr.get(_scenario_key(_t.title, _sc.name), _sc.action)
                        _chk = " ⚖ 회계사 확인 필요" if _sc.needs_law_check else ""
                        st.markdown(f"- **{_sc.name}{_chk}**")
                        st.markdown(f"    - 행동: {_act}")
                        st.markdown(f"    - 효과: {_sc.effect}")
                        if _sc.requirement:
                            st.markdown(f"    - 요건: {_sc.requirement}")
                        if _sc.risk:
                            st.markdown(f"    - 리스크: {_sc.risk}")
                    st.caption(f"법령 근거: {_t.legal_basis} · 상태: {_t.status}")
                    _refs = getattr(_t, "references", None) or []
                    if _refs:
                        st.markdown("**참고자료 (국세청 참고파일):**")
                        for _ref in _refs:
                            st.caption(format_reference(_ref))

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
            # Book / Tax / 세무상 금액 계산근거 / T·A · 소득처분 (검토패키지와 동일 형식)
            _bk = _d.get("book")
            _tx = _d.get("tax")
            bc1, bc2, bc3 = st.columns(3)
            bc1.metric("Book (장부상 금액)", f"{_bk:,}원" if _bk is not None else "—")
            bc2.metric("Tax (세무상 금액)", f"{_tx:,}원" if _tx is not None else "—")
            bc3.metric("T/A (세무조정)", f"{_d['금액']:,}원")
            if _d.get("tax_basis"):
                st.markdown(f"**세무상 금액 계산근거** — {_d['tax_basis']}")
            st.markdown(f"**소득처분** — {_d.get('처분') or '검토필요 (귀속자 미정)'}")
            st.caption("세무상 금액 산정 상세")
            for _f in _d["산식"]:
                st.markdown(f"- {_f}")
            _dlines = _d.get("lines") or []
            if _dlines:
                st.caption(f"근거분개 {len(_dlines):,}건")
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
                    striped_by_group(_ddf), width="stretch",
                    hide_index=True, height=320,
                )
                _dcsv = safe_df(pd.DataFrame([
                    {
                        "날짜": str(ln.date), "전표번호": ln.journal_id,
                        "계정코드": ln.account_code, "계정과목": ln.account_name,
                        "적요": ln.description, "거래처": ln.counterparty_name,
                        "차변": ln.debit, "대변": ln.credit,
                        "원본위치": f"{ln.source_sheet}!행{ln.source_row}",
                    }
                    for ln in _dlines
                ])).to_csv(index=False).encode("utf-8-sig")
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
            _n_bibang = sum(1 for d in depr_results if d.bibang_applied)
            _n_bibang_review = sum(1 for d in depr_results if d.bibang_partial_review)
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
                if _n_bibang:
                    st.caption(
                        f"※ {_n_bibang}건은 정률법 비망가액 특례(영§26⑥⑦) 적용 — 미상각잔액이 취득가액의 "
                        f"5% 이하가 되어 비망가액 min(취득가액×5%, 1,000원)만 남기고 상각범위액에 가산했습니다."
                    )
                if _n_bibang_review:
                    st.warning(
                        f"⚠ {_n_bibang_review}건은 월할(상각월수<12) 자산이면서 미상각잔액이 취득가액 5% 임계 "
                        "근처입니다 — 기중 처분 자산이면 잔여 미상각잔액은 상각이 아닌 처분손익으로 귀속되고"
                        "(영§26⑨는 취득연도 월할만 규정), 단기 사업연도면 별도 처리가 필요하니 회계사 확인 바랍니다."
                    )
                st.dataframe(pd.DataFrame([
                    {
                        "자산코드": d.asset_code,
                        "자산명": d.asset_name,
                        "방법": d.method + ("·비망가액특례" if d.bibang_applied else ""),
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
                ]), width="stretch", hide_index=True, height=320)
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
            st.dataframe(cov_df, width="stretch", hide_index=True, height=560)
            st.caption(
                "'관련 금액'은 해당 계정의 거래 규모이며 세무조정액이 아닙니다. "
                "검토필요 항목은 법령 근거 조문을 확인 후 수동 조정하세요."
            )

            # 검토필요 항목 근거법령·검토포인트 (결정론적 — 네트워크 없음) + 원문 on-demand 조회
            _law_cov = [c for c in coverage if c.status == "검토필요" and c.interpretation]
            if _law_cov:
                _law_cov.sort(key=lambda x: -x.amount_hint)
                with st.expander(f"검토필요 항목 근거법령·검토포인트 ({len(_law_cov)}건)"):
                    for c in _law_cov:
                        st.markdown(f"**{c.item}**  ·  {c.legal_basis}")
                        st.caption(f"검토포인트: {c.interpretation}")
                    _opts = [c for c in _law_cov if c.law_id and c.jo]
                    if _opts:
                        st.divider()
                        st.caption("조문 원문은 필요 시 선택 조회하세요 (PDF는 재현성 위해 검토포인트만 고정 수록).")
                        _names = [c.item for c in _opts]
                        _sel = st.selectbox("조문 원문 조회", range(len(_names)),
                                            format_func=lambda i: _names[i], key="cov_law_sel")
                        if st.button("원문 조회", key="cov_law_btn"):
                            from src.rules.legal_basis import _fetch_article_cached
                            _c = _opts[_sel]
                            _txt = _fetch_article_cached(_c.law_id, _c.jo, str(fy_end_val))
                            if _txt:
                                st.markdown(f"**{_c.item}** — {_c.legal_basis}")
                                st.text(_txt)
                                st.caption(f"출처: 국가법령정보센터 law.go.kr · 기준일 {fy_end_val} 시행 원문")
                            else:
                                st.warning("조문 조회 실패 — 네트워크/LAW_API_KEY 확인 (자료 없음과 구분).")

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
                    striped_by_group(_lines_df), width="stretch",
                    hide_index=True, height=400,
                )
                _csv = safe_df(_lines_df).to_csv(index=False).encode("utf-8-sig")
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
                    ]), width="stretch", hide_index=True)

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
        st.dataframe(_req_df, width="stretch", hide_index=True)
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
        "전기 값은 당기 손익계산서의 전기 열에서 자동 추출합니다. 급증 항목이 검토 우선순위입니다.",
    ), unsafe_allow_html=True)
    _prev_loader = st.session_state.get("prev_loader")
    _prev_is = getattr(_prev_loader, "income_statement", None)
    _yoy = yoy_table(loader.income_statement, prev_income_df=_prev_is)
    if _yoy is None:
        st.caption(
            "전기 비교 데이터가 없습니다 — 당기 손익계산서가 당기/전기 2개 열이 있는 "
            "양식이면 자동 분석됩니다."
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
            st.dataframe(_yoy_show, width="stretch", hide_index=True, height=400)
            st.download_button(
                "증감분석 CSV 다운로드",
                data=safe_df(_yoy).to_csv(index=False).encode("utf-8-sig"),
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
                    st.dataframe(_bs_show, width="stretch", hide_index=True,
                                 height=min(400, 60 + 36 * len(_bs_show)))
                    st.download_button(
                        "기초잔액 대사 CSV 다운로드",
                        data=safe_df(_bs_chk).to_csv(index=False).encode("utf-8-sig"),
                        file_name=f"기초잔액대사_{proj.company.name}_{fy_end_val}.csv",
                        mime="text/csv", key="bs_check_dl",
                    )

    # ── ②-3 제조원가 증감분석 — 전기 제조원가명세서 업로드 시 (제조업) ────────
    # 원가명세서는 노무비·외주가공비·제조경비 등 P&L에 없는 계정을 담아, 제조업
    # 세무조정(외주가공비 증빙·복리후생비 등)의 검토 우선순위 판단에 목적적합하다.
    _prev_cost = getattr(_prev_loader, "cost_statement", None)
    _cost_yoy = yoy_table(loader.cost_statement, prev_income_df=_prev_cost)
    if _cost_yoy is not None:
        st.divider()
        st.markdown(section_title(
            "제조원가명세서 증감분석 (분석적 검토)",
            "전기 값 출처: ① 2단계에 업로드한 전기 제조원가명세서 (우선) "
            "② 당기 원가명세서의 전기 열. 원가 항목 급증이 검토 우선순위입니다.",
        ), unsafe_allow_html=True)
        st.caption(f"전기 값 출처: **{_cost_yoy.attrs.get('prev_source', '')}**")
        for _f in yoy_flags(_cost_yoy):
            st.warning(_f)
        with st.expander(f"원가 계정별 증감 전체 보기 ({len(_cost_yoy)}개 계정)"):
            _cost_show = _cost_yoy.copy()
            for c in ("당기", "전기", "증감"):
                _cost_show[c] = _cost_show[c].map("{:,}".format)
            st.dataframe(_cost_show, width="stretch", hide_index=True, height=400)
            st.download_button(
                "원가 증감분석 CSV 다운로드",
                data=safe_df(_cost_yoy).to_csv(index=False).encode("utf-8-sig"),
                file_name=f"원가증감분석_{proj.company.name}_{fy_end_val}.csv",
                mime="text/csv", key="cost_yoy_dl",
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
