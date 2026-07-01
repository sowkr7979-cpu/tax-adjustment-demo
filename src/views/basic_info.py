"""1단계 — 기본정보 (DART 검색·중소기업·특정법인·특수관계인)."""
from __future__ import annotations
from datetime import date

import streamlit as st

from src.apis.dart_api import DartApiClient, DART_CORP_POPUP
from src.ui.sme_checker import render_sme_checker, ksic_to_industry
from src.ui.styles import page_header, section_title, info_card
from src.views.common import (
    _parse_stored_date, _fmt_bizr, _set_fiscal_year_from_acc_mt, _dart_preview,
)


def _render_audit_report_link(proj, dart: DartApiClient, has_dart_key: bool) -> None:
    """비상장·최대주주현황 미제출 법인 → DART 감사보고서(주주현황·특수관계자 주석) 바로가기.

    hyslrSttus 공시가 없어 DART 자동입력분이 0명인 경우 호출된다.
    proj.company.corp_code가 있으면 최신 감사보고서를 찾아 문서 뷰어 링크를 만들고,
    없으면(외부감사 비대상 등) 기업개황 화면으로 연결한다.
    """
    corp_code = (getattr(proj.company, "corp_code", "") or "").strip()

    st.markdown(
        '<div style="background:#fef7e0;border:1px solid #fde293;border-radius:12px;'
        'padding:0.85rem 1.1rem;margin:0.5rem 0 0.5rem 0;font-size:14px;color:#3c4043;'
        'line-height:1.55;">'
        '비상장 등으로 <b>DART 최대주주현황</b>(정기보고서) 공시가 없는 법인은 '
        '<b>감사보고서의 「주주현황」·「특수관계자 거래」 주석</b>에서 특수관계인을 확인합니다 '
        '— 아래 버튼으로 해당 문서로 이동하세요.'
        '</div>',
        unsafe_allow_html=True,
    )

    if not has_dart_key:
        st.caption("DART_API_KEY가 설정되어야 감사보고서를 자동으로 찾을 수 있습니다.")
        return
    if not corp_code:
        st.caption(
            "감사보고서 자동 검색은 위 ① 회사 검색에서 **자동 입력**으로 법인을 "
            "선택한 뒤 사용할 수 있습니다 (DART corp_code 필요)."
        )
        return

    skey = f"_audit_report_{corp_code}"
    if st.button(
        "📄 DART 감사보고서 찾기",
        help="이 법인의 최신 감사보고서를 DART에서 찾아 바로가기 링크를 만듭니다.",
    ):
        with st.spinner("DART에서 감사보고서 검색 중..."):
            try:
                st.session_state[skey] = {"ok": True, "report": dart.find_audit_report(corp_code)}
            except Exception as e:   # noqa: BLE001 — 조회 실패는 자료 없음과 구분해 안내
                st.session_state[skey] = {"ok": False, "error": str(e)}

    res = st.session_state.get(skey)
    if not res:
        return

    popup_url = DART_CORP_POPUP.format(corp_code=corp_code)
    if not res["ok"]:
        st.warning(
            f"감사보고서 조회 실패 (DART 오류: {res['error']}) — "
            "'자료 없음'이 아닙니다. 아래에서 DART를 직접 확인하세요."
        )
        st.link_button("DART 기업개황·공시목록 열기", popup_url)
        return

    rpt = res["report"]
    if rpt is None:
        st.info(
            "DART에 이 법인의 감사보고서가 없습니다 (외부감사 비대상 추정) — "
            "주주명부 기준으로 특수관계인을 아래 표에 직접 입력하세요."
        )
        st.link_button("DART 기업개황·공시목록 열기", popup_url)
        return

    _dt = rpt["rcept_dt"]
    _dt_fmt = f"{_dt[:4]}.{_dt[4:6]}.{_dt[6:]}" if len(_dt) == 8 else _dt
    st.success(f"최신 감사보고서: **{rpt['report_nm']}** ({_dt_fmt})")
    st.link_button(
        "📄 감사보고서 열기 — 주주현황·특수관계자 주석 확인",
        rpt["url"],
    )
    st.caption(
        "열린 문서 좌측 목차에서 「주주의 현황」 또는 주석의 「특수관계자와의 거래」를 "
        "확인해 임원·친족·관계회사를 아래 표에 직접 추가하세요."
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
            "<b style='color:#ea8600;'>DART_API_KEY 미설정</b> &nbsp; "
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
                        # 상세(표·출처 구분·지분율) + 이름 목록(다운스트림 매칭) 동시 채움
                        proj.manual_input.related_party_details = [
                            {
                                "이름":      s["nm"],
                                "관계":      s.get("relate", ""),
                                "지분율(%)": s.get("ownership_pct", ""),
                                "출처":      "DART",
                            }
                            for s in shareholders
                            if s["nm"]
                        ]
                        proj.manual_input.related_parties = [
                            s["nm"] for s in shareholders if s["nm"]
                        ]
                        # DART에서 불러온 인원수 기록 (④ 특수관계인 표시용)
                        st.session_state["_dart_related_count"] = len(
                            proj.manual_input.related_party_details
                        )

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
        "DART 최대주주현황(사업보고서 제출 회사) 자동 입력 시 주주 명단·지분율이 채워집니다 — "
        "비상장 미제출 법인은 주주명부·감사보고서(특수관계자 거래 주석)로 임원·친족·관계회사를 직접 추가하세요.",
    ), unsafe_allow_html=True)

    # ── 상세 목록 구성 (DART 자동입력 + 수기) — 구버전 .taxproj(이름 문자열만) 호환 마이그레이션 ──
    import pandas as pd
    import re as _re

    def _parse_legacy(s: str) -> tuple[str, str]:
        """'홍길동 (최대주주)' → ('홍길동', '최대주주'). 괄호 없으면 관계 공란."""
        m = _re.match(r"^(.*?)\s*\((.*)\)\s*$", s.strip())
        return (m.group(1).strip(), m.group(2).strip()) if m else (s.strip(), "")

    _details = [dict(d) for d in (proj.manual_input.related_party_details or [])]
    if not _details and proj.manual_input.related_parties:
        for s in proj.manual_input.related_parties:
            _nm, _rel = _parse_legacy(s)
            _details.append({"이름": _nm, "관계": _rel, "지분율(%)": "", "출처": "수기"})

    # 주주현황(보유주식수·금액) 칸 — 구버전·DART 자동입력분에는 없으므로 기본키 보강
    for _d in _details:
        _d.setdefault("관계", "")
        _d.setdefault("보유주식수", "")
        _d.setdefault("금액(원)", "")
        _d.setdefault("지분율(%)", "")
        _d.setdefault("출처", "수기")

    _dart_n = sum(1 for d in _details if d.get("출처") == "DART")
    _man_n = len(_details) - _dart_n

    # ── 입력 현황 (총원 + DART/수기 구분) ──
    _c1, _c2, _c3 = st.columns(3)
    _c1.metric("특수관계인 합계", f"{len(_details)}명")
    _c2.metric("🟢 DART 자동입력", f"{_dart_n}명")
    _c3.metric("✏️ 수기 입력", f"{_man_n}명")
    if _dart_n:
        st.caption(
            f"※ DART 최대주주·특수관계인 현황에서 **{_dart_n}명**의 주주 명단이 채워졌습니다(아래 표 '출처'=DART). "
            "DART에 없는 임원·친족·관계회사 등은 표 맨 아래 빈 행에 추가하세요."
        )
    else:
        st.caption(
            "※ DART 자동 입력분 없음 (비상장·공시 없음·조회 실패 등) — 주주명부 기준으로 직접 입력하세요. "
            "DART 조회는 위 ① 회사정보에서 실행합니다."
        )
        _render_audit_report_link(proj, dart, has_dart_key)
    if not _details:
        st.warning(
            "⚠ 특수관계인이 **0명**입니다 — 가지급금 인정이자(법§52)·부당행위 탐지에 필요하니 "
            "주주·임원·친족·관계회사를 입력하세요."
        )

    # 숫자 칸 파서 (콤마·공백·빈칸·NaN 허용) — 저장·미리보기 공용
    def _to_int(v) -> int | None:
        try:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            s = str(v).replace(",", "").replace(" ", "").strip()
            return int(float(s)) if s and s.lower() != "nan" else None
        except (ValueError, TypeError):
            return None

    # ── 표 편집 (감사보고서 주주현황 형식: 이름·관계·보유주식수·금액·지분율·출처) ──
    _cols = ["이름", "관계", "보유주식수", "금액(원)", "지분율(%)", "출처"]
    _rp_df = pd.DataFrame(_details, columns=_cols)
    _rp_df["보유주식수"] = pd.to_numeric(_rp_df["보유주식수"], errors="coerce")
    _rp_df["금액(원)"] = pd.to_numeric(_rp_df["금액(원)"], errors="coerce")
    _edited = st.data_editor(
        _rp_df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "이름": st.column_config.TextColumn("이름", required=True, width="medium"),
            "관계": st.column_config.TextColumn("관계", help="최대주주·대표이사·임원·친족·관계회사 등"),
            "보유주식수": st.column_config.NumberColumn(
                "보유주식수", min_value=0, step=1, format="%d",
                help="감사보고서 주주현황의 보유주식수 — 입력 시 지분율이 자동 계산됩니다",
            ),
            "금액(원)": st.column_config.NumberColumn(
                "금액(원)", min_value=0, step=1, format="%d",
                help="주주현황의 금액 (주식 액면·평가액)",
            ),
            "지분율(%)": st.column_config.TextColumn(
                "지분율(%)", help="직접 입력하거나, 보유주식수 입력 시 합계 대비 자동 계산됩니다",
            ),
            "출처": st.column_config.SelectboxColumn(
                "출처", options=["DART", "수기"], default="수기",
                help="DART 주주현황 자동입력분과 직접 추가한 항목을 구분합니다",
            ),
        },
        key="rp_editor",
    )
    st.caption(
        "감사보고서 「주주현황」을 그대로 옮길 수 있습니다 — 구분(이름)·보유주식수·금액·지분율. "
        "보유주식수만 채우면 지분율은 합계 대비 자동 계산되어 아래 미리보기에 표시됩니다."
    )
    if st.button("특수관계인 저장"):
        _rows = []
        for _, _row in _edited.iterrows():
            _nm = str(_row.get("이름", "") or "").strip()
            if _nm:
                _rows.append((_nm, _row))
        _total_sh = sum(s for s in (_to_int(r.get("보유주식수")) for _, r in _rows) if s)
        _new_details, _new_names = [], []
        for _nm, _row in _rows:
            _sh  = _to_int(_row.get("보유주식수"))
            _amt = _to_int(_row.get("금액(원)"))
            _pct_in = str(_row.get("지분율(%)", "") or "").strip()
            if not _pct_in and _sh and _total_sh:          # 보유주식수 → 지분율 자동 계산
                _pct_in = f"{round(_sh / _total_sh * 100, 2):g}"
            _new_details.append({
                "이름":      _nm,
                "관계":      str(_row.get("관계", "") or "").strip(),
                "보유주식수": _sh if _sh is not None else "",
                "금액(원)":   _amt if _amt is not None else "",
                "지분율(%)": _pct_in,
                "출처":      (str(_row.get("출처", "") or "").strip() or "수기"),
            })
            _new_names.append(_nm)   # 다운스트림(거래처명 부분일치)은 이름만 사용
        proj.manual_input.related_party_details = _new_details
        proj.manual_input.related_parties = _new_names
        st.success(f"{len(_new_names)}명 저장되었습니다 "
                   f"(DART {sum(1 for d in _new_details if d['출처']=='DART')} · "
                   f"수기 {sum(1 for d in _new_details if d['출처']=='수기')}).")

    # ── 미리보기 (읽기전용): 🟢 DART 음영 · 🔴 30% 초과 지배주주 하이라이트 · 지분율 합계 ──
    def _pct(v) -> float | None:
        try:
            return float(str(v).replace("%", "").replace(",", "").strip())
        except (ValueError, AttributeError):
            return None

    _valid = _edited.copy()
    _valid["이름"] = _valid["이름"].astype(str)
    _valid = _valid[
        _valid["이름"].str.strip().ne("") & _valid["이름"].str.strip().str.lower().ne("nan")
    ].reset_index(drop=True)
    if len(_valid) > 0:
        _sh_list  = [_to_int(v) for v in _valid["보유주식수"]]
        _amt_list = [_to_int(v) for v in _valid["금액(원)"]]
        _total_sh = sum(s for s in _sh_list if s)
        # 지분율: 입력값 우선, 없으면 보유주식수/합계로 도출 (None 보존 — NaN 변환 방지)
        _pcts = []
        for _i, _v in enumerate(_valid["지분율(%)"]):
            _p = _pct(_v)
            if _p is None and _sh_list[_i] and _total_sh:
                _p = round(_sh_list[_i] / _total_sh * 100, 2)
            _pcts.append(_p)
        _total = round(sum(p for p in _pcts if p is not None), 2)
        _total_amt = sum(a for a in _amt_list if a)
        _n_ctrl = int(sum(1 for p in _pcts if p is not None and p > 30))

        def _comma(n) -> str:
            return f"{n:,}" if isinstance(n, int) and n else ""

        _prev = pd.DataFrame({
            "이름":      _valid["이름"].values,
            "관계":      _valid["관계"].astype(str).replace("nan", "").values,
            "보유주식수": [_comma(s) for s in _sh_list],
            "금액(원)":   [_comma(a) for a in _amt_list],
            "지분율(%)": [(f"{p:g}" if p is not None else "") for p in _pcts],
            "출처":      _valid["출처"].astype(str).replace("nan", "").values,
        })
        _sum_row = {
            "이름": "합계", "관계": "",
            "보유주식수": _comma(_total_sh),
            "금액(원)":   _comma(_total_amt),
            "지분율(%)": (f"{_total:g}" if _total else ""),
            "출처": "",
        }
        _prev_disp = pd.concat([_prev, pd.DataFrame([_sum_row])], ignore_index=True)
        _last = len(_prev_disp) - 1
        _pct_col = list(_prev_disp.columns).index("지분율(%)")

        def _style_row(row):
            css = [""] * len(row)
            if row.name == _last:                       # 합계 행
                return ["font-weight:700; background-color:#f0f0f5"] * len(row)
            if str(row.get("출처", "")) == "DART":        # DART 음영 (연한 초록)
                css = ["background-color:#e8f5e9"] * len(row)
            p = _pct(row.get("지분율(%)"))                # 30% 초과 지배주주 하이라이트
            if p is not None and p > 30:
                css[_pct_col] = (css[_pct_col] + "; " if css[_pct_col] else "") + \
                    "background-color:#ffd6d6; font-weight:700; color:#b00020"
            return css

        st.markdown(
            "**현황 미리보기** — 🟢 DART 자동입력 음영 · 🔴 지분율 30% 초과 지배주주 하이라이트"
        )
        st.dataframe(
            _prev_disp.style.apply(_style_row, axis=1),
            use_container_width=True, hide_index=True,
        )
        _cap = f"지분율 합계 {_total:g}%"
        if _total_sh:
            _cap += f" · 보유주식수 합계 {_total_sh:,}주"
        if _total_amt:
            _cap += f" · 금액 합계 {_total_amt:,}원"
        if _n_ctrl:
            _cap += (f" · 🔴 30% 초과 지배주주 후보 {_n_ctrl}명 "
                     "(영§43⑦ 지배주주등·법§52 특수관계 판정 참고 — 회계사 확인)")
        st.caption(_cap)

