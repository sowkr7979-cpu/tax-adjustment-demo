"""1단계 — 기본정보 (DART 검색·중소기업·특정법인·특수관계인)."""
from __future__ import annotations
from datetime import date

import streamlit as st

from src.apis.dart_api import DartApiClient
from src.ui.sme_checker import render_sme_checker, ksic_to_industry
from src.ui.styles import page_header, section_title, info_card
from src.views.common import (
    _parse_stored_date, _fmt_bizr, _set_fiscal_year_from_acc_mt, _dart_preview,
)


def render(proj) -> None:
    st.markdown(page_header(
        "기본 정보 입력",
        "법인 정보와 사업연도를 설정합니다.",
    ), unsafe_allow_html=True)

    dart = DartApiClient()
    has_dart_key = bool(dart.api_key)

    # ── ① DART 회사 검색 ────────────────────────────────────────────────────

    st.markdown(section_title(
        "회사 검색",
        "회사명을 입력하면 DART에서 사업자번호·주소·대표자 등을 자동으로 가져옵니다.",
    ), unsafe_allow_html=True)

    if not has_dart_key:
        st.markdown(info_card(
            "<b style='color:#ff9500;'>DART_API_KEY 미설정</b> &nbsp; "
            "<code>.env</code> 파일에 <code>DART_API_KEY=...</code>를 추가하면 "
            "자동 검색을 사용할 수 있습니다. 아래에서 직접 입력도 가능합니다."
        ), unsafe_allow_html=True)

    col_q, col_btn = st.columns([4, 1], gap="medium")
    with col_q:
        search_query = st.text_input(
            "회사명 검색",
            value=st.session_state.get("_dart_query", proj.company.name),
            placeholder="삼성전자, (주)홍길동상사 ...",
            label_visibility="collapsed",
        )
    with col_btn:
        btn_label = "DART 검색" if has_dart_key else "API키 없음"
        search_clicked = st.button(
            btn_label,
            use_container_width=True,
            disabled=not has_dart_key,
        )

    # 목록에 업종·대표자를 표시하기 위해 상세조회하는 최대 건수
    _DETAIL_LIMIT = 30

    if search_clicked and search_query.strip():
        st.session_state["_dart_query"] = search_query
        with st.spinner("DART 법인 목록에서 검색 중..."):
            try:
                results = dart.search_by_name(search_query)
                if not results:
                    st.warning("검색 결과가 없습니다. 아래에서 직접 입력하세요.")
            except Exception as e:
                st.error(f"DART 검색 오류: {e}")
                results = []
                st.session_state.pop("_dart_results", None)
        if results:
            # 동일 상호 구분용 — 상위 N곳 업종·대표자 일괄 조회 (캐시되어 재검색 시 즉시)
            n_detail = min(len(results), _DETAIL_LIMIT)
            prog = st.progress(0, text=f"업종·대표자 조회 중... 0/{n_detail}곳")
            for i, r in enumerate(results[:n_detail]):
                r["_preview"] = _dart_preview(r["corp_code"])
                prog.progress((i + 1) / n_detail, text=f"업종·대표자 조회 중... {i + 1}/{n_detail}곳")
            prog.empty()
            st.session_state["_dart_results"] = results

    # 검색 결과 선택
    if st.session_state.get("_dart_results"):
        results = st.session_state["_dart_results"]

        def _fmt_option(r: dict) -> str:
            base = f"{r['corp_name']} ({'상장' if r['stock_code'].strip() else '비상장'})"
            p = r.get("_preview") or {}
            if not p:
                return base
            ind = ksic_to_industry(p.get("industry_code", "")) or p.get("industry_code", "") or "업종미상"
            ceo = p.get("ceo", "") or "대표자미상"
            return f"{base} · {ind} · 대표 {ceo}"

        options = [_fmt_option(r) for r in results]
        label = f"검색 결과 {len(results)}개"
        if len(results) > _DETAIL_LIMIT:
            label += f" (업종·대표자는 상위 {_DETAIL_LIMIT}곳까지 표시 — 더 정확한 회사명으로 좁혀보세요)"
        sel_idx = st.selectbox(
            label,
            range(len(options)),
            format_func=lambda i: options[i],
            key="_dart_sel_idx",
        )

        # 선택 법인 미리보기 — 동일 상호·다른 업종 구분용 (자동 입력 확정 전 확인)
        _prev = _dart_preview(results[sel_idx]["corp_code"])
        if _prev:
            _ind = ksic_to_industry(_prev.get("industry_code", "")) or _prev.get("industry_code", "") or "업종정보 없음"
            _est = _prev.get("est_dt", "")
            _est_fmt = f"{_est[:4]}.{_est[4:6]}.{_est[6:]}" if len(_est) == 8 else _est
            st.markdown(info_card(
                f"<b>업종</b> {_ind} &nbsp;·&nbsp; "
                f"<b>대표자</b> {_prev.get('ceo', '')} &nbsp;·&nbsp; "
                f"<b>설립</b> {_est_fmt} &nbsp;·&nbsp; "
                f"<b>결산월</b> {_prev.get('acc_mt', '')}월<br>"
                f"<b>주소</b> {_prev.get('adres', '')}"
            ), unsafe_allow_html=True)
        else:
            st.caption("상세 미리보기 조회 실패 — 자동 입력 시 다시 시도됩니다.")

        col_apply, col_clear = st.columns([1, 5], gap="medium")
        with col_apply:
            if st.button("자동 입력", use_container_width=True):
                selected = results[sel_idx]
                corp_code = selected["corp_code"]

                with st.spinner("DART에서 법인정보·재무·주주현황 조회 중..."):
                    info        = None
                    financial   = {}
                    shareholders = []
                    try:
                        info = dart.get_company_info(corp_code)
                    except Exception as e:
                        st.error(f"기본정보 조회 오류: {e}")
                    fy_year = _parse_stored_date(
                        proj.company.fiscal_year_end, date.today()
                    ).year
                    bsns_year = str(fy_year)
                    try:
                        # 가장 최신 공시 재무 — 당기 사업보고서가 미공시면
                        # 직전·전전기 순으로 폴백 (최신 매출액·자산총액 확보)
                        for _try_year in (fy_year, fy_year - 1, fy_year - 2):
                            financial = dart.get_financial_summary(corp_code, str(_try_year))
                            if financial.get("revenue") is not None or \
                               financial.get("total_assets") is not None:
                                bsns_year = str(_try_year)
                                break
                    except Exception:
                        financial = {}
                    _sh_failed = False
                    try:
                        shareholders = dart.get_major_shareholders(corp_code, bsns_year)
                    except Exception as e:
                        # 조회 '실패'는 '자료 없음'과 다르다 — 특수관계인 판단은 세무상 중요
                        shareholders = []
                        _sh_failed = True
                        st.warning(
                            f"⚠ 주주현황 **조회 실패** (DART API 오류: {e}) — "
                            f"'특수관계인 없음'이 아닙니다. 주주명부 등으로 수기 확인 후 "
                            f"1단계 특수관계인 목록에 직접 입력하세요."
                        )
                    if not shareholders and not _sh_failed:
                        st.info(
                            "DART에 최대주주 현황 공시가 없습니다 (비상장·소규모 법인 등) — "
                            "특수관계인은 주주명부 기준으로 직접 입력하세요."
                        )

                if info:
                    proj.company.name          = info.corp_name
                    proj.company.business_no   = _fmt_bizr(info.bizr_no)
                    proj.company.address       = info.adres
                    proj.company.representative = info.ceo_nm
                    proj.company.corp_code     = info.corp_code
                    proj.company.industry_code = info.industry_code
                    proj.company.acc_mt        = info.acc_mt
                    if info.acc_mt:
                        _set_fiscal_year_from_acc_mt(proj, info.acc_mt)

                    # ── 지배관계 추정 ──────────────────────────────────────
                    # 법인 주주 중 지분율 30% 초과인 경우 지배기업 있음으로 추정
                    has_ctrl = False
                    for sh in shareholders:
                        try:
                            pct = float(sh["ownership_pct"].replace(",", ""))
                            if pct > 30:
                                has_ctrl = True
                                break
                        except (ValueError, AttributeError):
                            pass

                    # 독립성: 상장 대기업 주주 30% 초과 → 미충족 추정
                    # DART만으로 대기업 여부 확정 불가 → 충족으로 초기값, 주의 표시
                    is_independent = True

                    # DART 재무요약 실패 시 사유를 명확히 표시 (자동입력 실패 → 수기 확인)
                    if financial.get("fail_reason"):
                        st.warning(
                            f"재무요약 자동입력 실패 — {financial['fail_reason']} "
                            f"매출액·자산총계는 수기로 입력하세요."
                        )

                    # ── SME prefill 저장 ───────────────────────────────────
                    st.session_state["_sme_prefill"] = {
                        "industry":               ksic_to_industry(info.industry_code),
                        "revenue":                financial.get("revenue"),
                        "total_assets":           financial.get("total_assets"),
                        "fin_year":               financial.get("year"),
                        "shareholders":           shareholders,
                        "has_controlling_entity": has_ctrl,
                        "is_independent":         is_independent,
                    }

                    # ── 특수관계인 자동 입력 ───────────────────────────────
                    if shareholders:
                        proj.manual_input.related_parties = [
                            f"{s['nm']} ({s['relate']})"
                            for s in shareholders
                            if s["nm"]
                        ]

                    st.session_state.pop("_dart_results", None)
                    filled = []
                    if financial.get("revenue") is not None:
                        filled.append(f"매출액({financial.get('year')}년 공시)")
                    if financial.get("total_assets") is not None:
                        filled.append(f"자산총계({financial.get('year')}년 공시)")
                    if shareholders:
                        filled.append(f"주주·특수관계인 {len(shareholders)}명")
                    extra = f" + {', '.join(filled)}" if filled else ""
                    st.success(f"자동 입력 완료: {info.corp_name}{extra}")
                    st.rerun()
        with col_clear:
            if st.button("검색 결과 닫기"):
                st.session_state.pop("_dart_results", None)
                st.rerun()

    st.divider()

    # ── ② 법인 기본 정보 (직접 입력 / 자동 입력 후 확인) ────────────────────

    st.markdown(section_title("법인 기본 정보"), unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="medium")
    with col1:
        new_name = st.text_input("법인명", value=proj.company.name)
        if new_name != proj.company.name:
            proj.company.name = new_name

        new_bno = st.text_input(
            "사업자등록번호",
            value=proj.company.business_no,
            placeholder="000-00-00000",
        )
        if new_bno != proj.company.business_no:
            proj.company.business_no = new_bno

        new_rep = st.text_input("대표자명", value=proj.company.representative)
        if new_rep != proj.company.representative:
            proj.company.representative = new_rep

    with col2:
        new_addr = st.text_area("주소", value=proj.company.address, height=68)
        if new_addr != proj.company.address:
            proj.company.address = new_addr

        # 사업연도 — 저장된 값 복원
        fy_start_default = _parse_stored_date(
            proj.company.fiscal_year_start,
            date(date.today().year - 1, 1, 1),
        )
        fy_end_default = _parse_stored_date(
            proj.company.fiscal_year_end,
            date(date.today().year - 1, 12, 31),
        )
        fy_start = st.date_input("사업연도 시작일", value=fy_start_default)
        fy_end   = st.date_input("사업연도 종료일", value=fy_end_default)
        proj.company.fiscal_year_start = str(fy_start)
        proj.company.fiscal_year_end   = str(fy_end)

    st.divider()

    # ── ③ 중소기업 판정 ─────────────────────────────────────────────────────

    st.markdown(section_title(
        "중소기업 판정",
        "6개 요소를 검토하여 세법상 중소기업 해당 여부를 결정합니다.",
    ), unsafe_allow_html=True)

    sme_result = render_sme_checker(prefill=st.session_state.get("_sme_prefill"))
    if st.button("중소기업 판정 저장"):
        proj.company.is_sme = sme_result["is_sme"]
        proj.company.sme_verified = True
        proj.company.sme_verification_notes = sme_result["notes"]
        verdict = "중소기업" if proj.company.is_sme else "일반법인"
        st.success(f"저장 완료 — {verdict}으로 분류됩니다.")

    st.divider()

    # ── ③-2 특정법인·부동산임대업 판정 (세무조정 산식·한도에 직접 영향) ──────

    st.markdown(section_title(
        "특정법인·부동산임대업 판정",
        "판정 결과에 따라 기업업무추진비 한도(50%), 업무용승용차 한도(400만·500만), "
        "간주임대료(조특법§138) 적용 여부가 달라집니다.",
    ), unsafe_allow_html=True)

    st.markdown("**① 특정법인 요건 (법§25⑤·법§27의2⑤, 영§42② — 세 가지 모두 충족 시 해당)**")
    _sc1 = st.checkbox(
        "1. 사업연도 종료일 현재 지배주주등의 지분 합계가 50%를 초과한다",
        value=proj.company.is_specified_corp,
        key="sc_req1",
        help="영§43⑦의 지배주주등 (특수관계인 지분 포함). DART 주주현황 참고.",
    )
    _sc2 = st.checkbox(
        "2. 부동산임대업이 주된 사업이거나, 부동산임대수입+이자소득+배당소득 합계가 "
        "매출액의 50% 이상이다",
        value=proj.company.is_specified_corp,
        key="sc_req2",
    )
    _sc3 = st.checkbox(
        "3. 해당 사업연도의 상시근로자 수가 5명 미만이다",
        value=proj.company.is_specified_corp,
        key="sc_req3",
        help="최대주주와 친족, 근로계약 1년 미만, 단시간근로자는 제외하고 계산 (영§42④).",
    )
    _is_spec = _sc1 and _sc2 and _sc3
    if _is_spec:
        st.error(
            "**특정법인 해당** — 기업업무추진비 한도 50% 축소 (법§25⑤), "
            "업무용승용차 감가상각비 한도 800만→400만원·운행기록부 미작성 시 "
            "전액인정 한도 1,500만→500만원 (영§50의2⑮)이 자동 적용됩니다."
        )
    else:
        st.caption("요건 미충족 — 일반 한도가 적용됩니다.")

    st.markdown("**② 부동산임대업 주업 여부 (조특법§138 간주임대료 적용 요건)**")
    _rental_main = st.checkbox(
        "사업연도 종료일 현재 자산총액 중 임대사업에 사용된 자산가액이 50% 이상이다 "
        "(조특령§132③)",
        value=proj.company.is_rental_main,
        key="rental_main_chk",
        help="추가 요건(차입금 적수 > 자기자본 적수×2)은 3단계 수기 입력의 "
             "임대보증금·차입금·자기자본으로 자동 판정됩니다.",
    )

    if st.button("특정법인·임대업 판정 저장"):
        proj.company.is_specified_corp = _is_spec
        proj.company.specified_corp_notes = (
            f"지배주주50%초과={_sc1}, 임대주업·금융수입50%={_sc2}, 상시근로자5인미만={_sc3}"
        )
        proj.company.is_rental_main = _rental_main
        st.success(
            f"저장 완료 — 특정법인 {'해당' if _is_spec else '비해당'} · "
            f"부동산임대업 주업 {'해당' if _rental_main else '비해당'}"
        )

    st.divider()

    # ── ④ 특수관계인 ────────────────────────────────────────────────────────

    st.markdown(section_title(
        "특수관계인 목록",
        "특수관계인 관련 세무조정에 자동 활용됩니다 — ① 가지급금 인정이자 분개 추천 (법§52, 영§88①6호) "
        "② 업무무관 가지급금 지급이자 (법§28①4호나목) ③ LLM 분석 시 부당행위 의심 거래 탐지. "
        "DART 자동 입력 시 주주 명단이 채워지며, 임원·친족 등을 추가하세요.",
    ), unsafe_allow_html=True)

    existing_parties = "\n".join(proj.manual_input.related_parties)
    related_parties = st.text_area(
        "특수관계인 목록",
        value=existing_parties,
        placeholder="대표이사 홍길동\n(주)OOO물산\n홍길동 배우자 박씨",
        height=120,
        label_visibility="collapsed",
    )
    if st.button("특수관계인 저장"):
        proj.manual_input.related_parties = [
            p.strip() for p in related_parties.splitlines() if p.strip()
        ]
        st.success(f"{len(proj.manual_input.related_parties)}명 저장됩니다.")

