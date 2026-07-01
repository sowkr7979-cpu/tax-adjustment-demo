"""수기 입력 UI 컴포넌트 + 입력 검증."""
from __future__ import annotations
from datetime import date
from itertools import islice

import streamlit as st

from src.project.taxproj import ManualInput
from src.rules.tax_credit_catalog import lookup_credit_spec
from src.ui.credit_formula import credit_formula_type, render_credit_formula
from src.rules.penalty_surtax import aggregate_surtax
from src.ui.review_questions import ReviewItemSpec, should_show, build_result
from src.ui.review_specs import (
    unfair_transaction_spec, welfare_spec, deemed_dividend_spec, inventory_spec,
    officer_retirement_spec, officer_bonus_spec,
)


def validate_manual_input(mi: ManualInput, fiscal_year_end: date) -> list[str]:
    """수기 입력 검증. 경고 메시지 리스트 반환."""
    warnings: list[str] = []

    # 이월결손금 공제기한 검증
    for item in mi.carryforward_losses:
        year = item.get("year", 0)
        amount = item.get("amount", 0)
        if not year or not amount:
            continue
        expiry = 15 if year >= 2009 else 5
        if (fiscal_year_end.year - year) >= expiry:
            warnings.append(
                f"이월결손금 {year}년 발생분({amount:,}원)은 "
                f"공제기한 {expiry}년을 초과했습니다. 공제 불가."
            )

    # 유보잔액 부호 검증
    for item in mi.prior_reserves:
        code = item.get("code", "")
        val = item.get("amount", 0)
        disposition = item.get("disposition", "유보")
        if disposition == "유보" and val < 0:
            warnings.append(f"유보 항목 [{code}]의 금액이 음수입니다. 확인 필요.")
        if disposition == "△유보" and val > 0:
            warnings.append(f"△유보 항목 [{code}]의 금액이 양수입니다. 확인 필요.")

    # 이월 세액공제 기한 (10년)
    for item in mi.carryforward_tax_credits:
        year = item.get("year", 0)
        amount = item.get("amount", 0)
        if year and amount and (fiscal_year_end.year - year) >= 10:
            warnings.append(
                f"이월세액공제 {year}년 발생분({amount:,}원) 공제기한(10년) 초과."
            )

    return warnings


def render_carryforward_loss(existing: list | None = None) -> list[dict]:
    """이월결손금 입력 — existing(전년 승계분)이 있으면 기본값으로 채운다."""
    existing = existing or []
    st.subheader("이월결손금 (연도별)")
    st.caption("전기 신고서 기준. 발생연도·금액을 정확히 입력하세요." +
               (" (전년도 자료에서 승계됨 — 당기 공제분 차감 확인)" if existing else ""))
    n = st.number_input(
        "이월결손금 항목 수", min_value=0, max_value=20,
        value=len(existing), step=1,
    )
    items = []
    for i in range(int(n)):
        _ex = existing[i] if i < len(existing) else {}
        c1, c2 = st.columns(2)
        with c1:
            year = st.number_input(
                f"발생연도 {i+1}", min_value=1990, max_value=2030,
                value=int(_ex.get("year", 2020)), key=f"loss_year_{i}",
            )
        with c2:
            amount = st.number_input(
                f"금액(원) {i+1}", min_value=0, step=1_000_000,
                value=int(_ex.get("amount", 0)), key=f"loss_amt_{i}",
            )
        items.append({"year": int(year), "amount": int(amount)})
    return items


def _comp_rows(journals, name_keywords: tuple, exclude: tuple = ()) -> list:
    """특정 계정 키워드에 매칭된 분개 [(거래처, 계정과목, JournalLine)] — 출처·내역 표시용."""
    rows = []
    for ln in journals or []:
        nm = ln.account_name.replace(" ", "")
        if any(k in nm for k in name_keywords) and not any(x in nm for x in exclude):
            if ln.debit <= 0:
                continue
            who = (ln.counterparty_name or "").strip() or "(거래처 미기재)"
            rows.append((who, ln.account_name.strip(), ln))
    return rows


# 기부금 자동 분류 키워드 (거래처명·적요 기준 추천 — 최종 판단은 사용자)
_DONATION_SPECIAL_KW = (
    "국가", "지방자치", "시청", "군청", "구청", "도청", "국방", "군부대", "위문",
    "국립", "공립", "학교", "대학", "교육청", "적십자", "공동모금", "재해", "이재민",
)
_DONATION_GENERAL_KW = (
    "사회복지", "복지법인", "복지재단", "문화재단", "장학", "학술", "종교",
    "교회", "사찰", "성당", "재단법인", "사단법인", "유니세프", "월드비전", "굿네이버스",
)
_DONATION_NONDESIG_KW = ("동창회", "향우회", "종친회", "정당", "조합")


def _suggest_donation_class(ln) -> str:
    text = f"{ln.counterparty_name} {ln.description}"
    if any(k in text for k in _DONATION_SPECIAL_KW):
        return "특례"
    if any(k in text for k in _DONATION_NONDESIG_KW):
        return "비지정"
    if any(k in text for k in _DONATION_GENERAL_KW):
        return "일반"
    return "미분류"


def _line_key(ln) -> str:
    return f"{ln.journal_id}|{ln.source_row}"


# ── 업무무관자산 (법§28①4호, 영§49·53) — 계정별 명세에서 후보 추출, 수기 체크 ──

_NONBIZ_KW = (
    "회원권", "골프", "콘도", "리조트", "별장",
    "서화", "미술품", "비업무", "업무무관",
)
# 가지급금·대여금 계정은 여기서 제외 — '가지급금 인정이자' 섹션의 분개 체크로
# 별도 반영되어 법§28①4호나목 분자에 합산된다 (중복 계산 방지)
_NONBIZ_EXCLUDE = ("가지급금", "대여금", "주임종")


def _render_nonbiz_drilldown(mi: ManualInput, loader, det) -> None:
    """결산부속명세서(계정별 세부) 2단계 드릴다운 — 계정 선택 → 세부 라인 체크.

    선택 라인은 계정별로 합산되어 업무무관자산 잔액·적수에 반영된다.
    같은 계정의 일부 라인만 선택하면 calc는 금액×일수 근사를 쓴다(전체계정=False).
    """
    import pandas as pd

    det = det.copy()
    det["금액"] = det["금액"].apply(lambda v: int(v) if str(v).strip() not in ("", "nan") else 0)
    # 라인 고유키 — 계정·거래처·적요·금액 조합 (체크 상태 저장/복원에 사용)
    det["_lid"] = (
        det["계정코드"].astype(str) + "|" + det["거래처코드"].astype(str) + "|"
        + det["거래처명"].astype(str) + "|" + det["적요"].astype(str) + "|"
        + det["금액"].astype(str)
    )
    saved = dict(mi.non_business_asset_checks or {})
    det["_sel"] = det["_lid"].map(lambda x: bool(saved.get(x)))

    grp = (det.groupby(["계정코드", "계정명"], as_index=False)
              .agg(금액=("금액", "sum"), 라인수=("금액", "size"), 선택=("_sel", "sum")))
    grp = grp[grp["금액"] != 0].sort_values("금액", ascending=False).reset_index(drop=True)
    if grp.empty:
        st.caption("결산부속명세서에서 잔액이 있는 계정을 찾지 못했습니다.")
        return

    # ── 1단계: 계정 선택 (전체 계정) ──
    def _acct_label(i: int) -> str:
        row = grp.iloc[i]
        nm = str(row["계정명"])
        star = "⭐ " if any(k in nm for k in _NONBIZ_KW) else ""
        warn = "  ⚠인정이자 중복주의" if any(k in nm for k in _NONBIZ_EXCLUDE) else ""
        chk = f"  ✅{int(row['선택'])}건" if int(row["선택"]) else ""
        return f"{star}{nm} · {int(row['금액']):,}원 · {int(row['라인수'])}건{chk}{warn}"

    sel = st.selectbox(
        "① 계정 선택 — 전체 계정에서 고른 뒤 ② 명세에서 업무무관 항목을 체크하세요",
        range(len(grp)), format_func=_acct_label, key="nonbiz_acct_sel",
    )
    acct_code = str(grp.iloc[sel]["계정코드"])
    acct_name = str(grp.iloc[sel]["계정명"])
    if any(k in acct_name for k in _NONBIZ_EXCLUDE):
        st.warning(
            f"**{acct_name}**: 특수관계인 가지급금·대여금은 '가지급금 인정이자' 섹션의 분개 "
            "체크로 이미 법§28①4호나목 분자에 반영됩니다 — 여기서 또 선택하면 중복될 수 있습니다."
        )

    # ── 2단계: 선택 계정의 세부 라인 체크 ──
    lines = det[(det["계정코드"].astype(str) == acct_code)
                & (det["계정명"].astype(str) == acct_name)].reset_index(drop=True)
    _disp = pd.DataFrame({
        "해당":   lines["_sel"].astype(bool),
        "거래처명": lines["거래처명"].astype(str),
        "적요":   lines["적요"].astype(str),
        "금액":   lines["금액"].astype(int),
        "비고":   lines["비고"].astype(str),
    })
    _edited = st.data_editor(
        _disp,
        column_config={
            "해당": st.column_config.CheckboxColumn("업무무관 해당"),
            "금액": st.column_config.NumberColumn("금액 (원)", format="%d"),
        },
        disabled=["거래처명", "적요", "금액", "비고"],
        use_container_width=True, hide_index=True,
        key=f"nonbiz_lines_{acct_code}_{acct_name}",
        height=min(360, 60 + 36 * len(lines)),
    )
    # 현재 계정의 체크만 갱신 — 다른 계정 선택분은 saved에 그대로 보존
    for i in range(len(lines)):
        saved[str(lines.iloc[i]["_lid"])] = bool(_edited.iloc[i]["해당"])
    mi.non_business_asset_checks = saved

    # ── 전체 누적 집계 — 계정별 1항목 (calc는 계정명 단위 적수, 중복 호출 방지) ──
    det["_sel"] = det["_lid"].map(lambda x: bool(saved.get(x)))
    chosen = det[det["_sel"]]
    line_counts = det.groupby(["계정코드", "계정명"]).size()
    nonbiz_list = []
    for (code, nm), sub in chosen.groupby(["계정코드", "계정명"]):
        _names = [s for s in sub["거래처명"].astype(str) if s]
        _disp_name = (_names[0] + (f" 외 {len(_names)-1}건" if len(_names) > 1 else "")) if _names else ""
        nonbiz_list.append({
            "계정명":   str(nm),
            "금액":     int(sub["금액"].sum()),
            "출처":     "계정명세",
            "전체계정":  len(sub) >= int(line_counts.get((code, nm), 0)),
            "거래처":   _disp_name,
        })
    mi.non_business_assets = nonbiz_list
    mi.non_business_asset_balance = int(sum(x["금액"] for x in nonbiz_list))

    # ── 선택 요약 + 차입금 비율 ──
    if nonbiz_list:
        _sumdf = pd.DataFrame([
            {"계정명": x["계정명"], "거래처": x["거래처"], "금액": x["금액"],
             "적수기준": "계정전체" if x["전체계정"] else "선택금액×일수"}
            for x in nonbiz_list
        ])
        st.markdown(
            f"**선택한 업무무관자산 — {len(nonbiz_list)}계정 합계 "
            f"{mi.non_business_asset_balance:,}원**"
        )
        st.dataframe(
            _sumdf, use_container_width=True, hide_index=True,
            column_config={"금액": st.column_config.NumberColumn("금액 (원)", format="%d")},
        )
    else:
        st.caption("아직 선택된 업무무관 항목이 없습니다 — 계정을 골라 세부 라인을 체크하세요.")

    _numer = mi.non_business_asset_balance + mi.related_loan_balance
    if _numer > 0:
        _debt = _bs_amount(loader, ("단기차입금", "장기차입금", "유동성장기부채"))
        if _debt:
            _ratio = min(1.0, _numer / _debt)
            st.caption(
                f"업무무관자산 {mi.non_business_asset_balance:,}원 + 특수관계인 가지급금 "
                f"{mi.related_loan_balance:,}원 = **{_numer:,}원** / 차입금 {_debt:,}원 → "
                f"지급이자 × {_ratio:.1%} 손금불산입 예정 (채권자불분명·건설자금 제외 후, 영§53②). "
                f"※ 기말잔액 기준 근사 — 정밀 계산은 적수 기준"
            )
        else:
            st.warning(
                "차입금 잔액을 찾지 못해 비율을 계산할 수 없습니다 — "
                "계정별명세서를 업로드하거나 간주임대료 섹션에서 차입금을 입력하세요."
            )


def _render_nonbiz_assets(mi: ManualInput, loader) -> None:
    """업무무관자산 선택 — 계정별명세서(없으면 재무상태표)의 계정을 표시하고
    사용자가 체크한 잔액 합계를 법§28①4호 지급이자 손금불산입 계산에 연결한다.

    자동 확정하지 않는다 — 키워드(가지급금·회원권 등)는 추천 체크일 뿐,
    업무무관 여부는 회계사 판단(수기 체크)으로 확정한다.
    """
    import pandas as pd

    st.markdown("---")
    st.markdown("**업무무관자산 (법§28①4호, 영§49·53) — 해당 자산을 체크하세요**")
    st.caption(
        "특수관계인 가지급금(법§28①4호나목)은 '가지급금 인정이자' 섹션의 분개 체크로 "
        "별도 반영되므로 이 표에는 표시되지 않습니다."
    )

    # 결산부속명세서(계정별 세부)가 있으면 계정→세부라인 드릴다운으로 선택
    _det = getattr(loader, "account_details", None) if loader is not None else None
    if _det is not None and not _det.empty:
        st.caption("결산부속명세서 인식 — 계정을 펼쳐 거래처별 세부 라인에서 업무무관자산을 선택합니다.")
        _render_nonbiz_drilldown(mi, loader, _det)
        return

    # 계정별명세서 우선, 없으면 재무상태표에서 계정 목록 추출
    src_rows: list[tuple[str, int, str]] = []
    for attr, src_name in (("account_statement", "계정별명세서"), ("balance_sheet", "재무상태표")):
        df = getattr(loader, attr, None) if loader is not None else None
        if df is None or df.empty or "계정명" not in df.columns or "기말잔액" not in df.columns:
            continue
        for _, row in df.iterrows():
            nm = str(row["계정명"]).strip()
            try:
                amt = int(row["기말잔액"] or 0)
            except (ValueError, TypeError):
                amt = 0
            if any(k in nm.replace(" ", "") for k in _NONBIZ_EXCLUDE):
                continue   # 가지급금·대여금은 인정이자 섹션의 분개 체크에서 별도 반영
            if nm and amt > 0 and not bool(row.get("합계행", False)):
                src_rows.append((nm, amt, src_name))
        break

    if not src_rows:
        st.caption("계정별명세서·재무상태표가 없어 직접 입력합니다.")
        mi.non_business_asset_balance = int(st.number_input(
            "업무무관자산 잔액 합계 (원)", min_value=0,
            value=mi.non_business_asset_balance, step=10_000_000,
            help="가지급금·회원권·별장 등 업무와 관련 없는 자산 (영§49)",
        ))
        return

    saved = mi.non_business_asset_checks or {}
    show_all = st.checkbox(
        "전체 계정에서 선택 (기본: 가지급금·회원권 등 후보만 표시)",
        value=False, key="nonbiz_show_all",
    )
    cands = []
    for nm, amt, src in src_rows:
        sug = any(k in nm.replace(" ", "") for k in _NONBIZ_KW)
        checked = bool(saved.get(nm, sug))
        if show_all or sug or checked:
            cands.append({"해당": checked, "계정명": nm, "기말잔액": amt, "출처": src})
    if not cands:
        st.caption(
            "후보 키워드(가지급금·회원권·골프·콘도·별장·서화 등)에 해당하는 계정이 없습니다 — "
            "'전체 계정에서 선택'을 켜면 모든 계정에서 직접 체크할 수 있습니다."
        )
        mi.non_business_asset_balance = 0
        return

    edited = st.data_editor(
        pd.DataFrame(cands),
        column_config={
            "해당": st.column_config.CheckboxColumn("업무무관자산 해당"),
            "기말잔액": st.column_config.NumberColumn("기말잔액 (원)", format="%d"),
        },
        disabled=["계정명", "기말잔액", "출처"],
        use_container_width=True, hide_index=True,
        key="nonbiz_asset_editor",
        height=min(320, 60 + 36 * len(cands)),
    )
    # 표시되지 않은 계정의 기존 체크는 보존하며 병합
    saved.update(dict(zip(edited["계정명"], edited["해당"].astype(bool))))
    mi.non_business_asset_checks = saved
    mi.non_business_asset_balance = int(edited.loc[edited["해당"], "기말잔액"].sum())
    mi.non_business_assets = [
        {"계정명": r["계정명"], "금액": int(r["기말잔액"]), "출처": r["출처"]}
        for _, r in edited.loc[edited["해당"]].iterrows()
    ]

    _numer = mi.non_business_asset_balance + mi.related_loan_balance
    if _numer > 0:
        _debt = _bs_amount(loader, ("단기차입금", "장기차입금", "유동성장기부채"))
        if _debt:
            _ratio = min(1.0, _numer / _debt)
            st.caption(
                f"업무무관자산 {mi.non_business_asset_balance:,}원 + 특수관계인 가지급금 "
                f"{mi.related_loan_balance:,}원 = **{_numer:,}원** / 차입금 {_debt:,}원 → "
                f"지급이자 × {_ratio:.1%} 손금불산입 예정 (채권자불분명·건설자금 제외 후, 영§53②). "
                f"※ 기말잔액 기준 근사 — 정밀 계산은 적수 기준"
            )
        else:
            st.warning(
                "차입금 잔액을 찾지 못해 비율을 계산할 수 없습니다 — "
                "계정별명세서를 업로드하거나 간주임대료 섹션에서 차입금을 입력하세요."
            )


# ── 가지급금·대여금 분개 체크 (법§52 인정이자 + 법§28①4호나목 업무무관 가지급금) ──

def _rp_names(related_parties: list | None) -> list[str]:
    """특수관계인 목록에서 매칭용 이름 추출 — '홍길동 (대표이사)' → '홍길동'."""
    names = []
    for rp in related_parties or []:
        nm = str(rp).split("(")[0].strip()
        if nm:
            names.append(nm)
    return names


def _render_loan_classifier(mi: ManualInput, journals: list, related_parties: list | None) -> bool:
    """가지급금·대여금 분개에서 특수관계인 가지급금을 체크.

    체크 결과는 두 세무조정에 연결된다 (law.go.kr 원문 확인):
      ① 인정이자 익금산입 — 무상·저율 대여는 부당행위 (법§52, 영§88①6호)
      ② 업무무관자산 지급이자 — 특수관계인 가지급금 (법§28①4호나목, 영§53①)
    """
    import pandas as pd

    lines = [
        ln for ln in journals
        if any(k in ln.account_name.replace(" ", "") for k in ("가지급금", "대여금", "주임종"))
        and (ln.debit > 0 or ln.credit > 0)
    ]
    if not lines:
        return False

    rp_list = _rp_names(related_parties)

    def _is_rp(ln) -> bool:
        cp = (ln.counterparty_name or "").strip()
        return bool(cp) and any(nm in cp or cp in nm for nm in rp_list)

    st.markdown("**가지급금·대여금 분개 — 특수관계인 가지급금 해당 건을 체크하세요**")
    st.caption(
        f"분개장에서 가지급금·대여금 계정 {len(lines)}건을 가져왔습니다. "
        + (f"1단계 특수관계인 목록({len(rp_list)}명) 기준으로 **거래처가 일치하는 건만** 추천 체크했습니다 "
           if rp_list else
           "특수관계인 목록이 비어 있어 가지급금 계정 건을 임시 추천 체크했습니다(1단계에서 특수관계인을 "
           "입력하면 매칭 건만 추천됩니다) ")
        + "— 특수관계 성립·업무무관성은 분개로 확정 불가하므로 최종 판단은 회계사가 확정하세요. "
        "체크 건은 ①인정이자(법§52, 영§88①6호) ②업무무관자산 지급이자(법§28①4호나목) "
        "두 조정에 모두 반영됩니다."
    )
    saved = (mi.misc_line_checks or {}).get("related_loan_lines", {})
    df = pd.DataFrame([
        {
            # 추천 체크 = 특수관계인 거래처 매칭 건만(영§2⑧). 특수관계인 미입력 시에만 가지급금 계정 폴백.
            "해당": bool(saved.get(
                _line_key(ln),
                _is_rp(ln) or (not rp_list and "가지급금" in ln.account_name.replace(" ", "")),
            )),
            "특수관계인": "✓" if _is_rp(ln) else "",
            "날짜": str(ln.date),
            "계정과목": ln.account_name,
            "적요": ln.description,
            "거래처": ln.counterparty_name,
            "차변": ln.debit,
            "대변": ln.credit,
            "_key": _line_key(ln),
        }
        for ln in lines[:500]
    ])
    if len(lines) > 500:
        st.warning(f"가지급금·대여금 {len(lines):,}건 중 500건만 표시됩니다.")
    edited = st.data_editor(
        df,
        column_config={
            "해당": st.column_config.CheckboxColumn("특수관계인 가지급금"),
            "차변": st.column_config.NumberColumn("차변 (원)", format="%d"),
            "대변": st.column_config.NumberColumn("대변 (원)", format="%d"),
            "_key": None,
        },
        disabled=["특수관계인", "날짜", "계정과목", "적요", "거래처", "차변", "대변"],
        use_container_width=True, hide_index=True,
        key="related_loan_editor",
        height=min(320, 60 + 36 * len(df)),
    )
    if mi.misc_line_checks is None:
        mi.misc_line_checks = {}
    mi.misc_line_checks["related_loan_lines"] = dict(
        zip(edited["_key"], edited["해당"].astype(bool))
    )
    _chk = edited.loc[edited["해당"]]

    # ── 동일인 가수금 자동 상계 (영§53③) ──
    # 가수금·주임종단기차입금 분개에서 체크된 가지급금 거래처와 동일인 금액을 찾아 상계
    _loan_by_cp: dict[str, int] = {}
    for _, r in _chk.iterrows():
        cp = str(r["거래처"]).strip() or "(거래처 미기재)"
        _loan_by_cp[cp] = _loan_by_cp.get(cp, 0) + int(r["차변"]) - int(r["대변"])
    _susu_by_cp: dict[str, int] = {}
    for ln in journals:
        if not any(k in ln.account_name.replace(" ", "") for k in ("가수금", "주임종단기차입")):
            continue
        cp = (ln.counterparty_name or "").strip()
        if cp and cp in _loan_by_cp:
            _susu_by_cp[cp] = _susu_by_cp.get(cp, 0) + ln.credit - ln.debit

    _net_rows = []
    _net_total = 0
    for cp, loan in _loan_by_cp.items():
        susu = max(0, _susu_by_cp.get(cp, 0))
        net = max(0, loan - susu)
        _net_total += net
        _net_rows.append({
            "거래처": cp,
            "가지급금 (차−대)": f"{loan:,}",
            "가수금 상계 (영§53③)": f"{susu:,}" if susu else "",
            "상계 후 잔액": f"{net:,}",
        })

    c1, c2, c3 = st.columns(3)
    c1.metric("체크 건수", f"{len(_chk)}건")
    c2.metric("가수금 상계", f"{sum(max(0, v) for v in _susu_by_cp.values()):,}원")
    c3.metric("상계 후 잔액 합계", f"{_net_total:,}원")
    if _net_rows:
        st.dataframe(pd.DataFrame(_net_rows), use_container_width=True, hide_index=True)
    st.caption(
        "※ 가수금은 가수금·주임종단기차입금 분개에서 동일 거래처 금액을 자동 탐지해 상계했습니다 "
        "(동일인 가지급금·가수금 상계 — 인정이자 적수는 규칙§44, 지급이자 적수는 영§53③). "
        "상환기간·이자율이 약정된 가수금은 상계하지 않는 것이 통설이므로(규칙·통칙) 해당 시 수동 조정. "
        "**인정이자는 5단계에서 체크 분개의 거래 날짜로 거래상대방별 일별 적수(積數)를 "
        "계산해 산정합니다** (영§89⑤, 별지 제19호 구조). 약정이자는 이자수익 분개에서 "
        "상대방별로 자동 매칭됩니다."
    )
    if _net_total > 0 and not mi.related_loan_balance:
        mi.related_loan_balance = _net_total

    # ── 거래상대방(차주)별 기초이월·약정이자 — 별지19호 1행/차주 ──────────────
    st.markdown("**거래상대방(차주)별 기초이월·약정이자** — 별지 제19호서식 1행/차주")
    st.caption(
        "전기에서 이월된 가지급금(당기 거래 0건이어도)과 차주별 수취 약정이자를 입력하세요. "
        "당기 증감은 위 분개 체크에서 거래상대방별로 자동 반영됩니다. "
        "상대방 간 통산은 하지 않습니다 (영§88③)."
    )
    _cp_cands: list[str] = list(_loan_by_cp.keys())
    for nm in rp_list:
        if nm and nm not in _cp_cands:
            _cp_cands.append(nm)
    _saved_p = {str(p.get("name", "")).strip(): p for p in (mi.related_loan_parties or [])}
    for nm in _saved_p:
        if nm and nm not in _cp_cands:
            _cp_cands.append(nm)
    _pdf = pd.DataFrame(
        [
            {
                "거래상대방": nm,
                "기초이월 가지급금": int(_saved_p.get(nm, {}).get("opening", 0)),
                "수취 약정이자": int(_saved_p.get(nm, {}).get("interest", 0)),
            }
            for nm in _cp_cands
        ] or [{"거래상대방": "", "기초이월 가지급금": 0, "수취 약정이자": 0}]
    )
    _pedit = st.data_editor(
        _pdf, num_rows="dynamic",
        column_config={
            "기초이월 가지급금": st.column_config.NumberColumn("기초이월 가지급금 (원)", format="%d", min_value=0),
            "수취 약정이자": st.column_config.NumberColumn("수취 약정이자 (원)", format="%d", min_value=0),
        },
        use_container_width=True, hide_index=True, key="related_loan_parties_editor",
    )
    mi.related_loan_parties = [
        {
            "name": str(r["거래상대방"]).strip(),
            "opening": int(r["기초이월 가지급금"] or 0),
            "interest": int(r["수취 약정이자"] or 0),
        }
        for _, r in _pedit.iterrows() if str(r.get("거래상대방", "")).strip()
    ]
    return True


# ── 임대보증금 분개 체크 (조특법§138 간주임대료) ──────────────────────────────

def _render_deposit_classifier(mi: ManualInput, journals: list) -> bool:
    """임대보증금·전세보증금 분개에서 '간주임대료 대상(받은 임대보증금)'을 식별.

    간주임대료 적수는 임대사업용 '받은 보증금' 총액 기준 (조특령§132⑤).
    체크는 '해당만 선택'이 아니라 '전체 ON, 제외할 것만 해제' — 누락(과소계상) 방지.
    받은 보증금(부채, 대변 누적)이 대상이고, 회사가 지급·예치한 보증금(자산)은 제외.
    """
    import pandas as pd

    lines = [
        ln for ln in journals
        if any(k in ln.account_name.replace(" ", "") for k in ("임대보증금", "전세보증금"))
        and (ln.debit > 0 or ln.credit > 0)
    ]
    if not lines:
        return False

    st.markdown("**임대보증금 분개 — 간주임대료 대상(받은 임대보증금)을 확인하세요**")
    st.caption(
        f"분개장에서 임대·전세보증금 계정 {len(lines)}건을 가져왔습니다. **기본 전체 체크** — "
        "임대 무관 보증금(영업·하자보수·입찰보증금)이나 회사가 **지급한 보증금(자산)**은 체크 해제하세요. "
        "받은 임대보증금(부채)만 간주임대료 대상입니다 (조특령§132⑤)."
    )
    saved = (mi.misc_line_checks or {}).get("rental_deposit_lines", {})

    def _is_received(ln) -> bool:
        # 받은 보증금(부채)은 통상 대변 계상. 차변 계상은 지급·반환 가능 — 기본 체크 ON은 대변건만
        return ln.credit >= ln.debit

    df = pd.DataFrame([
        {
            "해당": bool(saved.get(_line_key(ln), _is_received(ln))),
            "구분": "받은(부채)" if _is_received(ln) else "지급/반환?",
            "날짜": str(ln.date),
            "계정과목": ln.account_name,
            "적요": ln.description,
            "거래처(임차인)": ln.counterparty_name,
            "차변": ln.debit,
            "대변": ln.credit,
            "_key": _line_key(ln),
        }
        for ln in lines[:500]
    ])
    if len(lines) > 500:
        st.warning(f"임대·전세보증금 {len(lines):,}건 중 500건만 표시됩니다.")
    edited = st.data_editor(
        df,
        column_config={
            "해당": st.column_config.CheckboxColumn("간주임대료 대상"),
            "차변": st.column_config.NumberColumn("차변 (원)", format="%d"),
            "대변": st.column_config.NumberColumn("대변 (원)", format="%d"),
            "_key": None,
        },
        disabled=["구분", "날짜", "계정과목", "적요", "거래처(임차인)", "차변", "대변"],
        use_container_width=True, hide_index=True,
        key="rental_deposit_editor",
        height=min(300, 60 + 36 * len(df)),
    )
    if mi.misc_line_checks is None:
        mi.misc_line_checks = {}
    mi.misc_line_checks["rental_deposit_lines"] = dict(
        zip(edited["_key"], edited["해당"].astype(bool))
    )

    # ── 임대물건(임차인)별 기초 보증금 명세 — 표시·합계용 (적수는 총액 단일 트랙) ──
    st.markdown("**임대물건·임차인별 기초 보증금 명세** (합계가 기초 보증금 총액)")
    _saved_items = mi.rental_deposit_items or []
    _idf = pd.DataFrame(
        _saved_items or [{"물건/임차인": "", "기초 보증금": 0}],
    )
    if "물건/임차인" not in _idf.columns:
        _idf = pd.DataFrame([{"물건/임차인": "", "기초 보증금": 0}])
    _iedit = st.data_editor(
        _idf, num_rows="dynamic",
        column_config={
            "기초 보증금": st.column_config.NumberColumn("기초 보증금 (원)", format="%d", min_value=0),
        },
        use_container_width=True, hide_index=True, key="rental_deposit_items_editor",
    )
    mi.rental_deposit_items = [
        {"물건/임차인": str(r["물건/임차인"]).strip(), "기초 보증금": int(r["기초 보증금"] or 0)}
        for _, r in _iedit.iterrows() if str(r.get("물건/임차인", "")).strip()
    ]
    _items_total = sum(x["기초 보증금"] for x in mi.rental_deposit_items)
    if _items_total:
        st.caption(f"기초 보증금 총액(명세 합계): **{_items_total:,}원** — 적수 계산의 기초총액으로 사용")
        mi.rental_deposit = _items_total
    return True


# ── 지급이자 라인 분류 (법§28) — 이자비용 전체를 한 표에서 체크 ────────────────

def _suggest_interest_class(ln) -> str:
    """적요·거래처 기반 분류 추천 — 최종 판단은 사용자."""
    if any(k in ln.description for k in ("건설", "공사", "특정차입", "시설자금")):
        return "건설자금이자"
    if not (ln.counterparty_name or "").strip():
        return "채권자불분명"
    return "일반 (조정 없음)"


def _render_interest_classifier(mi: ManualInput, journals: list) -> bool:
    """이자비용 분개 전체를 한 표로 보여주고 라인별 분류. 렌더 시 True."""
    import pandas as pd

    lines = [
        ln for ln in journals
        if any(k in ln.account_name.replace(" ", "") for k in ("이자비용", "사채이자"))
        and ln.debit > 0
    ]
    if not lines:
        return False

    total_all = sum(ln.debit for ln in lines)
    st.caption(
        f"분개장의 **이자비용 전체 {len(lines)}건 · {total_all:,}원**입니다. "
        "조정 대상인 건만 체크하세요 (적요·거래처 기준 추천 반영됨) — "
        "체크하지 않은 건은 조정 없이 손금 인정됩니다."
    )
    saved = mi.interest_line_classes or {}

    def _saved_class(ln) -> str:
        return saved.get(_line_key(ln), _suggest_interest_class(ln))

    df = pd.DataFrame([
        {
            "채권자불분명": _saved_class(ln) == "채권자불분명",
            "비실명채권증권": _saved_class(ln) == "비실명 채권·증권이자",
            "건설자금": _saved_class(ln) == "건설자금이자",
            "날짜": str(ln.date),
            "계정과목": ln.account_name,
            "적요": ln.description,
            "거래처": ln.counterparty_name,
            "금액": ln.debit,
            "_key": _line_key(ln),
        }
        for ln in lines[:500]
    ])
    if len(lines) > 500:
        st.warning(f"이자비용 {len(lines):,}건 중 500건만 표시됩니다.")
    edited = st.data_editor(
        df,
        column_config={
            "채권자불분명": st.column_config.CheckboxColumn(
                "채권자불분명", help="채권자를 확인할 수 없는 사채이자 — 전액 손금불산입 (법§28①1호)",
            ),
            "비실명채권증권": st.column_config.CheckboxColumn(
                "비실명 채권·증권", help="소득세법§16①1·2·5·8호 채권·증권이자 중 지급받은 자 불분명 "
                                  "— 전액 손금불산입 (법§28①2호)",
            ),
            "건설자금": st.column_config.CheckboxColumn(
                "건설자금", help="사업용 자산 건설 차입금 이자 — 자본화 (법§28①3호)",
            ),
            "금액": st.column_config.NumberColumn("금액 (원)", format="%d"),
            "_key": None,
        },
        disabled=["날짜", "계정과목", "적요", "거래처", "금액"],
        use_container_width=True,
        hide_index=True,
        key="interest_line_editor",
        height=min(400, 60 + 36 * len(df)),
    )
    # 중복 체크는 1호 채권자불분명 > 2호 비실명 > 3호 건설자금 순으로 우선 적용 (영§55)
    _multi = (
        edited["채권자불분명"].astype(int) + edited["비실명채권증권"].astype(int)
        + edited["건설자금"].astype(int)
    ) > 1
    if _multi.any():
        st.warning(f"⚠ {int(_multi.sum())}건이 둘 이상 체크됨 — 채권자불분명 > 비실명 > 건설자금 순으로 처리합니다.")
    _cls = []
    for _, row in edited.iterrows():
        if row["채권자불분명"]:
            _cls.append("채권자불분명")
        elif row["비실명채권증권"]:
            _cls.append("비실명 채권·증권이자")
        elif row["건설자금"]:
            _cls.append("건설자금이자")
        else:
            _cls.append("일반 (조정 없음)")
    mi.interest_line_classes = dict(zip(edited["_key"], _cls))
    mi.interest_unknown_creditor = int(edited.loc[edited["채권자불분명"], "금액"].sum())
    mi.interest_nonreal_name = int(
        edited.loc[edited["비실명채권증권"] & ~edited["채권자불분명"], "금액"].sum()
    )
    mi.interest_construction = int(
        edited.loc[edited["건설자금"] & ~edited["채권자불분명"] & ~edited["비실명채권증권"], "금액"].sum()
    )
    normal = (total_all - mi.interest_unknown_creditor
              - mi.interest_nonreal_name - mi.interest_construction)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("이자비용 총액", f"{total_all:,}원")
    c2.metric("채권자불분명 (전액 손不)", f"{mi.interest_unknown_creditor:,}원")
    c3.metric("비실명 채권·증권 (전액 손不)", f"{mi.interest_nonreal_name:,}원")
    c4.metric("건설자금이자 (자본화)", f"{mi.interest_construction:,}원")
    st.caption(f"일반 이자비용 {normal:,}원은 조정 없이 손금 인정됩니다 (법§28 해당분만 손금불산입).")
    return True


def _render_donation_classifier(mi: ManualInput, journals: list) -> bool:
    """기부금 분개 라인별 분류 UI. 라인이 있으면 True (수기 입력 대체)."""
    import pandas as pd

    lines = [
        ln for ln in journals
        if "기부금" in ln.account_name.replace(" ", "") and ln.debit > 0
    ]
    if not lines:
        return False

    st.caption(
        f"분개장에서 기부금 {len(lines)}건을 가져왔습니다. 거래처·적요 기준으로 "
        f"분류를 추천했으니 확인·수정하세요. 합계는 자동 반영됩니다."
    )
    saved = mi.donation_line_classes or {}
    df = pd.DataFrame([
        {
            "분류": saved.get(_line_key(ln), _suggest_donation_class(ln)),
            "날짜": str(ln.date),
            "전표번호": ln.journal_id,
            "적요": ln.description,
            "거래처": ln.counterparty_name,
            "금액": ln.debit,
            "_key": _line_key(ln),
        }
        for ln in lines[:500]
    ])
    edited = st.data_editor(
        df,
        column_config={
            "분류": st.column_config.SelectboxColumn(
                "분류", options=["특례", "일반", "비지정", "미분류"], required=True,
            ),
            "금액": st.column_config.NumberColumn("금액 (원)", format="%d"),
            "_key": None,  # 숨김
        },
        disabled=["날짜", "전표번호", "적요", "거래처", "금액"],
        use_container_width=True,
        hide_index=True,
        key="donation_line_editor",
    )
    # 분류 저장 + 합계 반영
    mi.donation_line_classes = dict(zip(edited["_key"], edited["분류"]))
    mi.donation_special = int(edited.loc[edited["분류"] == "특례", "금액"].sum())
    mi.donation_general = int(edited.loc[edited["분류"] == "일반", "금액"].sum())
    mi.donation_nondesignated = int(edited.loc[edited["분류"] == "비지정", "금액"].sum())
    n_un = int((edited["분류"] == "미분류").sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("특례기부금", f"{mi.donation_special:,}원")
    c2.metric("일반기부금", f"{mi.donation_general:,}원")
    c3.metric("비지정기부금", f"{mi.donation_nondesignated:,}원")
    if n_un:
        st.warning(f"미분류 {n_un}건은 합계에서 제외됩니다 — 분류를 지정하세요.")
    return True


def _bs_amount_detail(loader, keywords: tuple, column: str = "기말잔액") -> tuple[int, str]:
    """계정별명세서 → 재무상태표 순으로 키워드 잔액 조회.

    column: "기말잔액" 또는 "기초잔액" (적수 계산의 기초 잔액용)
    반환: (합계, 출처 설명 "파일명: 계정A(금액), 계정B(금액)")
    """
    if loader is None:
        return 0, ""
    for attr, src_name in (
        ("account_statement", "계정별명세서"),
        ("balance_sheet", "재무상태표"),
    ):
        df = getattr(loader, attr, None)
        if df is None or df.empty or "계정명" not in df.columns or column not in df.columns:
            continue
        names = df["계정명"].astype(str).str.replace(" ", "")
        mask = names.apply(lambda n: any(k in n for k in keywords))
        if mask.any():
            matched = df.loc[mask]
            detail = ", ".join(
                f"{row['계정명']}({int(row[column]):,})"
                for _, row in matched.head(5).iterrows()
            )
            if len(matched) > 5:
                detail += f" 외 {len(matched) - 5}개"
            return int(matched[column].sum()), f"{src_name}: {detail}"
    return 0, ""


def _bs_amount(loader, keywords: tuple) -> int:
    """계정명 키워드 기말잔액 합계 (출처 불필요 시)."""
    return _bs_amount_detail(loader, keywords)[0]


def _render_line_check(
    mi: ManualInput, journals: list, attr: str, label: str,
    name_kws: tuple, desc_kws: tuple = (), help_text: str = "",
    suggest_fn=None,
) -> tuple[bool, int]:
    """분개 라인별 '해당' 체크 UI. (렌더 여부, 체크 합계) 반환.

    체크 합계를 어떻게 손금불산입에 반영할지는 호출부가 법령 산식에 따라 결정한다.
    suggest_fn(ln) -> bool: 저장된 체크가 없을 때의 기본 체크 추천.
    """
    import pandas as pd

    lines = [
        ln for ln in journals
        if (any(k in ln.account_name.replace(" ", "") for k in name_kws)
            or (desc_kws and any(k in ln.description for k in desc_kws)))
        and ln.debit > 0
    ]
    if not lines:
        return False, 0

    st.markdown(f"**{label}** — 분개장 {len(lines)}건")
    if help_text:
        st.caption(help_text)
    saved = (mi.misc_line_checks or {}).get(attr, {})
    df = pd.DataFrame([
        {
            "해당": bool(saved.get(
                _line_key(ln),
                bool(suggest_fn(ln)) if suggest_fn else False,
            )),
            "날짜": str(ln.date),
            "적요": ln.description,
            "거래처": ln.counterparty_name,
            "금액": ln.debit,
            "_key": _line_key(ln),
        }
        for ln in lines[:500]
    ])
    edited = st.data_editor(
        df,
        column_config={
            "해당": st.column_config.CheckboxColumn("해당"),
            "금액": st.column_config.NumberColumn("금액 (원)", format="%d"),
            "_key": None,
        },
        disabled=["날짜", "적요", "거래처", "금액"],
        use_container_width=True,
        hide_index=True,
        key=f"line_check_{attr}",
        height=min(250, 60 + 36 * len(df)),
    )
    if mi.misc_line_checks is None:
        mi.misc_line_checks = {}
    mi.misc_line_checks[attr] = dict(zip(edited["_key"], edited["해당"].astype(bool)))
    total = int(edited.loc[edited["해당"], "금액"].sum())
    return True, total


# unit별 '건' 명칭·도움말 (UI 표시용)
_UNIT_NOUN = {"line": "건", "officer": "임원", "category": "종류", "item": "건"}

# 복리후생비 귀속자(소득처분) 선택지 — welfare_spec DispositionRule mapping 키와 일치해야 함
_WELFARE_WHO = ("임원·직원(상여)", "주주(배당)", "불분명(대표자상여)")


def _render_welfare_table(mi: ManualInput, lines: list) -> None:
    """복리후생비 — 표 형식 검토 (건별 카드 대신).

    각 분개 행에 '지출성격: 열거외(손금불산입)' 체크(맨 오른쪽) + 귀속자(소득처분) + 부인금액.
    체크된 행만 welfare_spec 답(category='열거 외 비용')으로 저장 → 기존 계산 경로와 호환.
    영§45① 8개 열거항목은 손금 인정이므로 기본 미체크(자동 추천 안 함 — 적요만으론 판정 불가).
    """
    import pandas as pd
    from src.ui.review_specs import welfare_spec
    key = welfare_spec().key
    if not lines:
        st.caption("복리후생비·복리시설비 분개가 없습니다.")
        return
    saved = {str(a.get("_ref")): a for a in (mi.review_answers or {}).get(key, [])}
    rows = []
    for ln in lines:
        k = _line_key(ln)
        s = saved.get(k, {})
        rows.append({
            "날짜": str(ln.date),
            "적요": (ln.description or "")[:30],
            "거래처": ln.counterparty_name,
            "금액": int(ln.debit or 0),
            "귀속자(처분)": s.get("who", _WELFARE_WHO[0]),
            "부인금액": int(s.get("amount", ln.debit) or 0),
            "지출성격: 열거외(손금불산입)": s.get("category") == "열거 외 비용",
            "_key": k,
        })
    df = pd.DataFrame(rows)
    edited = st.data_editor(
        df,
        column_config={
            "금액": st.column_config.NumberColumn("금액(원)", format="%d"),
            "귀속자(처분)": st.column_config.SelectboxColumn(
                "귀속자(처분)", options=_WELFARE_WHO,
                help="열거외 손금불산입 시 소득처분 — 임직원=상여·주주=배당·불분명=대표자상여(영§106)"),
            "부인금액": st.column_config.NumberColumn(
                "부인금액(원)", format="%d",
                help="기본=금액 전액. 경조사비(8호) 등 일부만 부인 시 조정(부분부인)"),
            "지출성격: 열거외(손금불산입)": st.column_config.CheckboxColumn(
                "지출성격: 열거외(손금불산입)",
                help="영§45① 열거 8항목(직장체육·문화·회식·우리사주·건강/요양보험·어린이집·고용보험·"
                     "경조사 등)은 손금 인정. 열거에 없는 지출만 체크"),
            "_key": None,
        },
        disabled=["날짜", "적요", "거래처", "금액"],
        hide_index=True, use_container_width=True, key="welfare_editor",
        height=min(360, 60 + 36 * len(df)),
    )
    answers = []
    for _, r in edited.iterrows():
        if not bool(r["지출성격: 열거외(손금불산입)"]):
            continue
        answers.append({
            "category": "열거 외 비용",
            "amount": int(r["부인금액"] or 0),
            "who": str(r["귀속자(처분)"]),
            "_ref": str(r["_key"]),
        })
    if mi.review_answers is None:
        mi.review_answers = {}
    mi.review_answers[key] = answers
    _disallowed = sum(a["amount"] for a in answers)
    st.caption(
        f"열거외 손금불산입 {len(answers)}건 · 합계 {_disallowed:,}원 — 체크·금액은 회계사 확정값입니다."
    )


def _render_review_line_cards(
    mi: ManualInput, spec: ReviewItemSpec, candidate_labels: list[str] | None = None,
) -> None:
    """질문 카드 렌더러 — unit(line/officer/category/item)별 동적 인스턴스.

    decision tree(show_when)로 필요질문만 노출. 답은 mi.review_answers[spec.key]=[dict]로 저장.
    각 인스턴스의 조정금액·소득처분·법령게이트 결과를 즉시 표시한다.
    unit='item'은 1건 고정(건수 입력 없음).
    """
    if not isinstance(mi.review_answers, dict):
        mi.review_answers = {}
    prev = mi.review_answers.get(spec.key, []) or []
    _noun = _UNIT_NOUN.get(spec.unit, "건")
    if spec.unit == "item":
        n = 1
    else:
        n = int(st.number_input(
            f"{spec.target_label} {_noun}수", min_value=0, max_value=50,
            value=max(len(prev), 0), step=1, key=f"rev_n_{spec.key}",
            help=f"해당 {_noun}을 추가하고 질문에 답하면 조정금액·소득처분이 결정됩니다.",
        ))
    answers_list: list[dict] = []
    _cands = candidate_labels or []
    for i in range(n):
        p = prev[i] if i < len(prev) else {}
        a: dict = {}
        if spec.unit != "item":
            st.markdown(f"**{spec.target_label} — {_noun} #{i + 1}**")
        if _cands:
            _opts = ["(직접 입력)"] + _cands
            _pv = p.get("_ref", "")
            _idx = _opts.index(_pv) if _pv in _opts else 0
            _ref = st.selectbox(f"관련 {_noun} #{i + 1}", _opts, index=_idx,
                                key=f"rev_ref_{spec.key}_{i}")
            a["_ref"] = "" if _ref == "(직접 입력)" else _ref
        else:
            a["_ref"] = p.get("_ref", "")
        # decision tree — 앞 질문 답에 따라 show_when 충족 질문만 순차 노출
        for q in spec.questions:
            if not should_show(q, a):
                continue
            wkey = f"rev_{spec.key}_{i}_{q.id}"
            if q.kind == "select":
                opts = list(q.options)
                idx = opts.index(p[q.id]) if p.get(q.id) in opts else 0
                a[q.id] = st.selectbox(q.text, opts, index=idx, key=wkey, help=q.help)
            elif q.kind == "amount":
                a[q.id] = int(st.number_input(
                    q.text, min_value=0, value=int(p.get(q.id, 0) or 0),
                    step=1_000_000, key=wkey, help=q.help))
            elif q.kind == "number":
                a[q.id] = float(st.number_input(
                    q.text, min_value=0.0, value=float(p.get(q.id, 0) or 0),
                    step=1.0, key=wkey, help=q.help))
            elif q.kind == "yesno":
                a[q.id] = st.checkbox(q.text, value=bool(p.get(q.id, False)),
                                      key=wkey, help=q.help)
            elif q.kind in ("counterparty", "date"):
                a[q.id] = st.text_input(q.text, value=str(p.get(q.id, "")),
                                        key=wkey, help=q.help)
        _r = build_result(spec, a, line_ref=str(a.get("_ref", "")))
        if _r is not None:
            st.success(f"→ {_r.label} **{_r.amount:,}원** · 소득처분 **{_r.disposition}** ({_r.legal_basis})")
        elif a.get(spec.questions[0].id) not in ("해당없음", None, ""):
            st.caption("→ 법령 요건 미달(영§88③ 3억/5% 미달) 또는 금액 0 — 조정 제외")
        answers_list.append(a)
    mi.review_answers[spec.key] = answers_list
    # 카드 합계
    _results = [build_result(spec, a, line_ref=str(a.get("_ref", ""))) for a in answers_list]
    _results = [r for r in _results if r is not None]
    if _results:
        _total = sum(r.amount for r in _results)
        _by_disp: dict[str, int] = {}
        for r in _results:
            _by_disp[r.disposition] = _by_disp.get(r.disposition, 0) + r.amount
        _disp_txt = " · ".join(f"{k} {v:,}" for k, v in _by_disp.items())
        st.markdown(f"**합계 {_total:,}원** (처분별: {_disp_txt})")


def render_adjustment_data(
    mi: ManualInput, journals: list | None = None, loader=None,
    related_parties: list | None = None,
) -> None:
    """세무조정 필요자료 입력 — 체크리스트 '검토필요' 항목을 자동계산으로 승격.

    설계 원칙: 금액은 분개장에서 자동 집계하고, 사람은 판단 정보만 입력한다
    (임원이 누구인지, 평가방법을 신고했는지, 비율·한도가 얼마인지).
    """
    st.caption(
        "금액은 가급적 분개장에서 자동 집계됩니다. 판단 정보(명단·신고 여부·비율)만 "
        "입력하세요. 입력된 항목은 계산·검토 단계에서 자동 반영됩니다."
    )
    if not journals:
        st.info("분개장을 먼저 업로드(2단계)하면 임원 선택·금액 자동 집계가 활성화됩니다.")

    with st.expander("외화·파생상품 평가 (법§42③, 영§76)"):
        mi.forex_method_reported = st.checkbox(
            "화폐성 외화자산·부채 마감환율 평가방법 신고함",
            value=mi.forex_method_reported,
            help="신고한 경우 평가손익이 그대로 인정됩니다. 미신고 시 "
                 "외화환산이익은 익금불산입, 외화환산손실은 손금불산입 처리됩니다.",
        )
        mi.derivative_hedge_reported = st.checkbox(
            "통화선도 등 파생상품 마감환율 평가방법 신고함 (환위험회피용)",
            value=mi.derivative_hedge_reported,
            help="미신고 시 평가이익 익금불산입, 평가손실 손금불산입. "
                 "거래(정산) 손익은 실현분이므로 조정 대상이 아닙니다.",
        )

    with st.expander("임원 인건비 (법§26, 영§43~44)"):
        _bonus_rows = _comp_rows(journals, ("상여",))
        _retire_rows = _comp_rows(journals, ("퇴직급여", "퇴직금"), exclude=("충당",))
        bonus_by: dict[str, int] = {}
        for _who, _, _ln in _bonus_rows:
            bonus_by[_who] = bonus_by.get(_who, 0) + _ln.debit
        retire_by: dict[str, int] = {}
        for _who, _, _ln in _retire_rows:
            retire_by[_who] = retire_by.get(_who, 0) + _ln.debit
        all_names = sorted(set(bonus_by) | set(retire_by))

        if all_names:
            # 출처 계정과목 명시 — 상여금(판)/제조 등 어느 계정에서 집계했는지 표시
            _bonus_accts = sorted({a for _, a, _ in _bonus_rows})
            _retire_accts = sorted({a for _, a, _ in _retire_rows})
            st.caption(
                "분개장의 상여금·퇴직급여 계정 거래처 목록입니다. 임원만 선택하세요 — 금액은 자동 집계됩니다."
            )
            st.caption(
                f"**집계 출처 계정과목** — 상여: {', '.join(_bonus_accts) or '없음'}"
                f" / 퇴직: {', '.join(_retire_accts) or '없음'}"
            )
            mi.officer_names = st.multiselect(
                "임원 선택",
                all_names,
                default=[n for n in mi.officer_names if n in all_names],
                key="officer_names_sel",
            )
            auto_bonus = sum(bonus_by.get(n, 0) for n in mi.officer_names)
            auto_retire = sum(retire_by.get(n, 0) for n in mi.officer_names)
            mi.officer_bonus_paid = auto_bonus
            mi.officer_retirement_paid = auto_retire
            st.markdown(
                f"자동 집계 — 임원 상여금 **{auto_bonus:,}원** / 임원 퇴직급여 **{auto_retire:,}원**"
            )

            # 선택 임원의 집계 내역 — 계정과목별 합계 + 분개 라인
            if mi.officer_names:
                import pandas as pd
                _sel = set(mi.officer_names)
                _agg: dict[tuple, list] = {}
                for _gubun, _rows in (("상여", _bonus_rows), ("퇴직", _retire_rows)):
                    for _who, _acct, _ln in _rows:
                        if _who in _sel:
                            _agg.setdefault((_gubun, _who, _acct), []).append(_ln)
                if _agg:
                    st.markdown("**집계 내역 (구분 × 거래처 × 계정과목)**")
                    st.dataframe(pd.DataFrame([
                        {
                            "구분": g, "거래처(임원)": w, "계정과목": a,
                            "건수": len(lns), "금액": f"{sum(x.debit for x in lns):,}",
                        }
                        for (g, w, a), lns in sorted(_agg.items())
                    ]), use_container_width=True, hide_index=True)
                    with st.expander("분개 라인 상세 보기"):
                        from src.ui.styles import striped_by_group
                        st.dataframe(striped_by_group(pd.DataFrame([
                            {
                                "구분": g, "날짜": str(x.date), "전표번호": x.journal_id,
                                "계정과목": x.account_name, "적요": x.description,
                                "거래처": x.counterparty_name, "금액": f"{x.debit:,}",
                                "원본위치": f"{x.source_sheet}!행{x.source_row}",
                            }
                            for (g, w, a), lns in sorted(_agg.items())
                            for x in lns
                        ])), use_container_width=True, hide_index=True, height=300)
        else:
            st.caption("분개장에서 상여금·퇴직급여 거래처를 찾지 못했습니다 — 금액을 직접 입력하세요.")
            c1, c2 = st.columns(2)
            mi.officer_bonus_paid = int(c1.number_input(
                "임원 상여금 지급액 (원)", min_value=0, value=mi.officer_bonus_paid, step=1_000_000,
            ))
            mi.officer_retirement_paid = int(c2.number_input(
                "임원 퇴직금 지급액 (원)", min_value=0, value=mi.officer_retirement_paid, step=1_000_000,
            ))

        # 판단 정보 (분개장으로 알 수 없는 것)
        c3, c4, c5 = st.columns(3)
        mi.officer_bonus_limit = int(c3.number_input(
            "정관·주총 결의 상여 한도 (원)", min_value=0, value=mi.officer_bonus_limit, step=1_000_000,
            help="지급기준이 없으면 0 — 지급액 전액이 손금불산입됩니다",
        ))
        mi.officer_retirement_tenure = float(c4.number_input(
            "근속연수 (년)", min_value=0.0, value=mi.officer_retirement_tenure, step=0.5,
        ))
        mi.officer_retirement_last_salary = int(c5.number_input(
            "직전 1년 총급여 (원)", min_value=0, value=mi.officer_retirement_last_salary, step=1_000_000,
            help="정관 규정이 없을 때 한도 = 총급여 × 1/10 × 근속연수",
        ))

        # ── 임원 상여 한도 — 질문형 (임원 게이트·지급기준 초과, 영§43②) ──
        st.divider()
        st.markdown("**임원 상여금 한도초과 — 질문형 (지급기준 초과)**")
        if mi.officer_bonus_paid:
            st.caption(f"참고: 자동 집계된 임원 상여 지급액 {mi.officer_bonus_paid:,}원")
        _render_review_line_cards(mi, officer_bonus_spec(), [])

        # ── 임원 퇴직금 한도 — 질문형 (정관규정 우선 분기, 영§44④⑤) ──
        st.divider()
        st.markdown("**임원 퇴직금 한도초과 — 질문형 (정관규정 우선)**")
        if mi.officer_retirement_paid:
            st.caption(f"참고: 자동 집계된 임원 퇴직급여 지급액 {mi.officer_retirement_paid:,}원 "
                       "(아래 '실제 지급 퇴직급여'에 입력)")
        _render_review_line_cards(mi, officer_retirement_spec(), [])

    with st.expander("업무용승용차 (법§27의2, 영§50의2)"):
        c1, c2 = st.columns(2)
        mi.vehicle_has_insurance = c1.checkbox(
            "업무전용 자동차보험 가입", value=mi.vehicle_has_insurance,
            help="미가입 시 관련비용 전액 손금불산입 (영§50의2④1호) — 증빙불비와 무관한 별도 요건",
        )
        mi.vehicle_has_logbook = c2.checkbox(
            "운행기록부 작성", value=mi.vehicle_has_logbook,
            help="미작성 시 업무사용비율 = min(100%, 1,500만원 ÷ 관련비용) — 영§50의2⑦. "
                 "관련비용이 연 1,500만원(특정법인 500만원) 이하면 100% 인정",
        )
        if not mi.vehicle_has_insurance:
            st.error(
                "⚠ 업무전용 자동차보험 **미가입** 상태로 저장되어 있습니다 → "
                "승용차 관련비용 **전액 손금불산입**됩니다 (영§50의2④1호). "
                "실제로 가입했다면 위 체크박스를 켜세요. (증빙 유무와는 무관한 판정입니다)"
            )
        c3, c4 = st.columns(2)
        mi.vehicle_business_ratio = float(c3.number_input(
            "업무사용비율 (운행기록부 기준)", min_value=0.0, max_value=1.0,
            value=mi.vehicle_business_ratio, step=0.05,
        ))

        # 승용차 감가상각비 — 고정자산대장의 차량운반구에서 자산별 분류 후 집계
        # 법§27의2①: 개별소비세법 §1②3호 승용자동차만 대상
        # (화물차·9인승 이상 승합차·1,000cc 이하 경차는 제외)
        _veh_assets = [
            a for a in (getattr(loader, "fixed_assets", None) or [])
            if any(k in f"{a.asset_name}{a.category}{a.account_code}" for k in ("차량", "운반구"))
        ]
        if _veh_assets:
            import pandas as pd
            st.markdown("**차량운반구 자산별 분류** — 업무용승용차(법§27의2) 해당 여부를 확인하세요")
            st.caption(
                "개별소비세법상 승용자동차만 해당 — 화물차(포터·봉고 등)·9인승 이상 승합차"
                "(스타렉스·카니발 9인승 등)·경차(모닝·스파크 등)는 제외 추천됨"
            )
            _EXCLUDE_KW = (
                "포터", "봉고", "스타렉스", "그레이스", "트럭", "화물", "덤프",
                "버스", "승합", "탑차", "윙바디", "지게차", "굴삭기", "크레인",
                "마이티", "메가트럭", "포크레인",
                "모닝", "스파크", "레이", "캐스퍼", "마티즈", "다마스", "라보",
                "1톤", "2.5톤", "오토바이", "이륜",
            )
            _saved_v = mi.vehicle_asset_checks or {}
            _vdf = pd.DataFrame([
                {
                    "해당": bool(_saved_v.get(
                        a.asset_code,
                        not any(k in a.asset_name for k in _EXCLUDE_KW),
                    )),
                    "자산코드": a.asset_code,
                    "자산명": a.asset_name,
                    "감가상각비": a.company_depr,
                }
                for a in _veh_assets
            ])
            _vedit = st.data_editor(
                _vdf,
                column_config={
                    "해당": st.column_config.CheckboxColumn("업무용승용차 해당"),
                    "감가상각비": st.column_config.NumberColumn("감가상각비 (원)", format="%d"),
                },
                disabled=["자산코드", "자산명", "감가상각비"],
                use_container_width=True, hide_index=True,
                key="vehicle_asset_editor",
            )
            mi.vehicle_asset_checks = dict(zip(_vedit["자산코드"], _vedit["해당"].astype(bool)))
            mi.vehicle_depreciation = int(_vedit.loc[_vedit["해당"], "감가상각비"].sum())
            with c4:
                st.markdown(
                    f"승용차 감가상각비 (해당 체크 합계)<br>**{mi.vehicle_depreciation:,}원**",
                    unsafe_allow_html=True,
                )
        else:
            mi.vehicle_depreciation = int(c4.number_input(
                "승용차 감가상각비 계상액 (원)", min_value=0, value=mi.vehicle_depreciation, step=1_000_000,
                help="연 800만원 한도 적용 대상. 고정자산대장 업로드 시 자산별 분류가 활성화됩니다",
            ))

    with st.expander("지급이자 (법§28) — 이자비용 전체 분류"):
        if not (journals and _render_interest_classifier(mi, journals)):
            st.caption("분개장에서 이자비용 계정을 찾지 못했습니다 — 직접 입력하세요.")
            c1, c2, c3 = st.columns(3)
            mi.interest_unknown_creditor = int(c1.number_input(
                "채권자불분명 사채이자 (원)", min_value=0, value=mi.interest_unknown_creditor, step=1_000_000,
                help="채권자를 확인할 수 없는 사채이자 — 전액 손금불산입 (법§28①1호)",
            ))
            mi.interest_nonreal_name = int(c2.number_input(
                "비실명 채권·증권이자 (원)", min_value=0, value=mi.interest_nonreal_name, step=1_000_000,
                help="소득세법§16①1·2·5·8호 채권·증권이자 중 지급받은 자 불분명 — 전액 손금불산입 (법§28①2호)",
            ))
            mi.interest_construction = int(c3.number_input(
                "건설자금이자 (원)", min_value=0, value=mi.interest_construction, step=1_000_000,
                help="사업용 유형자산 건설에 소요된 차입금 이자 — 자본화 대상",
            ))
        # 업무무관자산 — 계정별 명세에서 후보를 끌어와 수기 체크 (법§28①4호)
        _render_nonbiz_assets(mi, loader)

    with st.expander("기부금 (법§24) — 분개장 라인별 분류"):
        if not (journals and _render_donation_classifier(mi, journals)):
            st.caption("분개장에 기부금 계정이 없습니다 — 금액을 직접 입력하세요.")
            c1, c2, c3 = st.columns(3)
            mi.donation_special = int(c1.number_input(
                "특례기부금 (원)", min_value=0, value=mi.donation_special, step=1_000_000,
                help="국가·지자체, 국방헌금 등 — 기준소득 50% 한도",
            ))
            mi.donation_general = int(c2.number_input(
                "일반기부금 (원)", min_value=0, value=mi.donation_general, step=1_000_000,
                help="사회복지·문화 등 공익법인 — 10% 한도",
            ))
            mi.donation_nondesignated = int(c3.number_input(
                "비지정기부금 (원)", min_value=0, value=mi.donation_nondesignated, step=1_000_000,
                help="전액 손금불산입",
            ))

        # ── 전기 이월 기부금 (법§24⑤⑥) — 발생연도별, 당기 우선공제 대상 ──
        import pandas as pd
        st.markdown("**전기 이월 기부금 (법§24⑤, 10년)**")
        st.caption(
            "전기 한도초과로 이월된 특례·일반 기부금을 발생연도별로 입력하면, 당기 한도 내에서 "
            "당기 지출분보다 **먼저** 손금산입됩니다(법§24⑥). 공제기한(10년) 초과분은 자동 소멸. "
            "전년도 .taxproj 승계 시 자동 채워집니다."
        )
        _cf_df = pd.DataFrame(
            mi.donation_carryforwards or [],
            columns=["year", "type", "amount"],
        )
        _cf_edit = st.data_editor(
            _cf_df, num_rows="dynamic",
            column_config={
                "year": st.column_config.NumberColumn("발생연도", format="%d", min_value=2000, max_value=2100),
                "type": st.column_config.SelectboxColumn("종류", options=["특례", "일반"]),
                "amount": st.column_config.NumberColumn("이월액 (원)", format="%d", min_value=0),
            },
            use_container_width=True, hide_index=True, key="donation_cf_editor",
        )
        mi.donation_carryforwards = [
            {"year": int(row["year"]), "type": str(row["type"] or "일반"),
             "amount": int(row["amount"] or 0)}
            for _, row in _cf_edit.iterrows()
            if row.get("year") and int(row.get("amount") or 0) > 0
            and str(row.get("type") or "") in ("특례", "일반")
        ]

    with st.expander("재고자산·유가증권 평가 (법§42, 영§74~75)"):
        st.caption(
            "재고자산 종류별(영§73)로 신고한 평가방법과 장부상 방법을 선택하세요. "
            "불일치 또는 무신고가 있으면 조정 대상으로 표시됩니다."
        )
        _METHODS = ["선입선출법", "후입선출법", "총평균법", "이동평균법", "개별법", "매가환원법"]
        _CATS = ["상품", "제품", "재공품", "원재료", "저장품"]
        if mi.inventory_methods is None:
            mi.inventory_methods = {}

        # 컬럼 헤더 — 어느 쪽이 세무상 신고방법인지 명시
        _h1, _h2, _h3 = st.columns([1, 2, 2])
        _h1.markdown("**종류**")
        _h2.markdown("**① 신고방법 (세무서에 신고한 평가방법)**")
        _h3.markdown("**② 장부방법 (회계장부상 실제 적용)**")

        _mismatches = []
        _mismatch_cats: list[str] = []
        for cat in _CATS:
            saved_m = mi.inventory_methods.get(cat, {})
            c1, c2, c3 = st.columns([1, 2, 2])
            c1.markdown(f"**{cat}**")
            reported = c2.selectbox(
                f"{cat} 신고방법", ["해당없음", "무신고"] + _METHODS,
                index=(["해당없음", "무신고"] + _METHODS).index(saved_m.get("신고", "해당없음")),
                key=f"inv_rep_{cat}", label_visibility="collapsed",
            )
            book = c3.selectbox(
                f"{cat} 장부방법", ["해당없음"] + _METHODS,
                index=(["해당없음"] + _METHODS).index(saved_m.get("장부", "해당없음")),
                key=f"inv_book_{cat}", label_visibility="collapsed",
            )
            mi.inventory_methods[cat] = {"신고": reported, "장부": book}
            if book == "해당없음":
                continue
            # 영§74: 무신고 시 선입선출법 강제, 신고방법과 장부방법 불일치 시 신고방법(또는 FIFO 중 큰 금액)
            if reported == "무신고" and book != "선입선출법":
                _mismatches.append(f"{cat}: 무신고 — 선입선출법 강제 (장부 {book})")
                _mismatch_cats.append(cat)
            elif reported not in ("해당없음", "무신고") and reported != book:
                _mismatches.append(f"{cat}: 신고 {reported} ≠ 장부 {book}")
                _mismatch_cats.append(cat)

        if _mismatches:
            st.warning("평가방법 조정 대상:\n" + "\n".join(f"- {m}" for m in _mismatches))
        # ── ② 평가액 입력 — ①에서 조정대상으로 식별된 종류만(중복 입력 방지, 영§74④ 단서 자동) ──
        st.markdown("**② 재고자산 평가조정 — 위 ①에서 조정대상인 종류만 평가액 입력**")
        if _mismatch_cats:
            st.caption("①에서 무신고·신고≠장부로 표시된 종류만 평가액(장부·선입선출·신고방법)을 입력하면 "
                       "조정금액이 산출됩니다. 무신고=선입선출(부동산 개별법), 신고방법외·변경무신고는 신고평가액이 "
                       "더 크면 신고방법 적용(영§74④ 단서).")
            _render_review_line_cards(mi, inventory_spec(), _mismatch_cats)
        else:
            st.caption("①에서 무신고·신고≠장부 종류가 없어 평가조정 대상이 없습니다. "
                       "변경 무신고 등 특수사유가 있으면 아래에서 직접 입력하세요.")
            with st.expander("재고 평가조정 직접 입력 (특수사유)"):
                _render_review_line_cards(mi, inventory_spec(), list(_CATS))
        st.caption(
            "유가증권 평가손익은 분개장에서 자동 집계되어 부인됩니다 "
            "(일반법인 원가법 강제 — 영§75). 별도 입력 불필요.",
        )

    with st.expander("기타 손금불산입 (법§21의2·26·27, 영§45·48) — 분개장 라인별 체크"):
        any_rendered = False
        if journals:
            # ── 징벌적 손해배상금 (법§21의2, 영§23) ──
            # 전액이 아니라 실손해 초과분만 손금불산입.
            # 실손해액이 불분명하면 지급액 × 2/3 (영§23② 계산식)
            _rp, _tp = _render_line_check(
                mi, journals, "_punitive_lines", "징벌적 손해배상금 (법§21의2, 영§23)",
                ("손해배상",), ("손해배상", "배상금"),
                "징벌적 배상 법률(영§23 별표1) 또는 외국 법령에 따른 손해배상 건만 체크",
            )
            if _rp:
                mi.punitive_actual_known = st.radio(
                    "실제 발생한 손해액이 분명합니까? (영§23②)",
                    ["분명함 — 실손해액 입력", "불분명 — 지급액의 2/3 손금불산입"],
                    index=0 if mi.punitive_actual_known else 1,
                    horizontal=True, key="punitive_known_radio",
                ).startswith("분명")
                if mi.punitive_actual_known:
                    mi.punitive_actual_amount = int(st.number_input(
                        "실제 발생한 손해액 (원)", min_value=0,
                        value=mi.punitive_actual_amount, step=1_000_000,
                        help="판결문·합의서 기준. 손금불산입 = 지급액 - 실손해액",
                    ))
                    mi.punitive_damages = max(0, _tp - mi.punitive_actual_amount)
                else:
                    mi.punitive_damages = int(_tp * 2 / 3)
                st.markdown(
                    f"→ 체크 지급액 {_tp:,}원 중 손금불산입 **{mi.punitive_damages:,}원**"
                )
                any_rendered = True

            # ── 공동경비 분담 초과 (영§48) ──
            # 전액이 아니라 분담기준(출자비율 또는 매출액·총자산 비율) 초과분만 손금불산입
            _rj, _tj = _render_line_check(
                mi, journals, "_joint_lines", "공동경비 (영§48)",
                ("공동경비",), ("공동경비", "경비분담", "분담금"),
                "공동 운영·사업 관련 경비로 당사가 부담한 건을 체크",
            )
            if _rj:
                c1, c2 = st.columns(2)
                mi.joint_total_pool = int(c1.number_input(
                    "공동경비 총액 — 전체 공동사업자 합계 (원)", min_value=0,
                    value=mi.joint_total_pool, step=1_000_000,
                ))
                mi.joint_share_ratio = float(c2.number_input(
                    "당사 분담비율 (%) — 출자비율 또는 매출액·총자산 비율 (영§48①)",
                    min_value=0.0, max_value=100.0,
                    value=mi.joint_share_ratio * 100, step=1.0,
                )) / 100
                _fair_share = int(mi.joint_total_pool * mi.joint_share_ratio)
                mi.joint_expense_excess = max(0, _tj - _fair_share)
                st.markdown(
                    f"→ 부담액 {_tj:,}원 - 적정 분담액 {_fair_share:,}원 = "
                    f"손금불산입 **{mi.joint_expense_excess:,}원**"
                )
                any_rendered = True

            # ── 업무무관비용 (법§27) — 해당 건 전액 손금불산입 ──
            _rn, _tn = _render_line_check(
                mi, journals, "non_business_expense", "업무무관비용 (법§27)",
                ("업무무관",), ("업무무관",),
                "업무무관자산 유지·관리비 등 해당 건 체크 — 전액 손금불산입",
            )
            if _rn:
                mi.non_business_expense = _tn
                st.markdown(f"→ 업무무관비용 손금불산입 **{_tn:,}원**")
                any_rendered = True

        if not any_rendered:
            st.caption("공동경비·업무무관비용·징벌적 손해배상금 관련 분개를 찾지 못했습니다 — 직접 입력하세요.")
            c1, c2, c3 = st.columns(3)
            mi.joint_expense_excess = int(c1.number_input(
                "공동경비 분담기준 초과액 (원)", min_value=0, value=mi.joint_expense_excess, step=1_000_000,
            ))
            mi.non_business_expense = int(c2.number_input(
                "업무무관비용 (원)", min_value=0, value=mi.non_business_expense, step=1_000_000,
            ))
            mi.punitive_damages = int(c3.number_input(
                "징벌적 손해배상금 (원)", min_value=0, value=mi.punitive_damages, step=1_000_000,
            ))

        # ── 복리후생비 (영§45①) — 표 형식 검토 (지출성격 열거외 체크 + 귀속자 처분) ──
        st.divider()
        st.markdown("**복리후생비 (영§45①) — 표 검토**")
        st.caption(
            "열거 8항목(직장체육·문화·회식·우리사주·건강/요양보험·어린이집·고용보험·경조사)은 손금 인정. "
            "표 맨 오른쪽 **'지출성격: 열거외'**를 체크한 건만 손금불산입되고 귀속자로 소득처분됩니다. "
            "적요만으론 열거 여부 판정이 어려워 자동 추천은 하지 않습니다(회계사 확정)."
        )
        def _is_welfare(ln) -> bool:
            _n = ln.account_name.replace(" ", "")   # 라인당 1회만 정규화
            return bool(ln.debit) and ("복리후생비" in _n or "복리시설비" in _n)
        _wf_lines = list(islice(
            (ln for ln in (journals or []) if _is_welfare(ln)), 500))   # 500건 조기종료
        _render_welfare_table(mi, _wf_lines)

    with st.expander("가지급금 인정이자·수입배당금·간주임대료 (법§52·18의2, 조특법§138)"):
        # 가지급금·대여금 분개 체크 — 특수관계인 목록 기반 추천 (인정이자 + 업무무관이자 연동)
        _render_loan_classifier(mi, journals or [], related_parties)
        c1, c2, c2r, c2o = st.columns(4)
        mi.related_loan_balance = int(c1.number_input(
            "가지급금 잔액 (분개 미체크 시 폴백, 원)", min_value=0,
            value=mi.related_loan_balance, step=1_000_000,
            help="위 분개 체크가 있으면 거래상대방별 일별 적수로 자동 계산되어 이 값은 "
                 "사용되지 않습니다. 체크가 없을 때만 잔액 × 365일로 적수를 근사합니다",
        ))
        mi.related_loan_interest = int(c2.number_input(
            "수취 약정이자 (자동매칭 실패 시, 원)", min_value=0,
            value=mi.related_loan_interest, step=100_000,
            help="약정이자는 이자수익 분개의 거래처로 상대방별 자동 매칭됩니다 — "
                 "분개에 없는 약정이자만 입력 (전체 합계에 가산)",
        ))
        mi.related_loan_rate = float(c2r.number_input(
            "가중평균차입이자율 (%)", min_value=0.0, max_value=20.0,
            value=mi.related_loan_rate * 100, step=0.1, format="%.2f",
            help="영§89③: 시가 = 가중평균차입이자율 원칙. 0이면 당좌대출이자율(4.6%) 적용 "
                 "(적용 불가·5년 초과 대여·신고 선택 시)",
        )) / 100
        _loan_open, _loan_open_src = _bs_amount_detail(
            loader, ("가지급금", "단기대여금", "장기대여금", "주임종"), column="기초잔액",
        )
        mi.related_loan_opening = int(c2o.number_input(
            "기초 이월 가지급금 (원)", min_value=0,
            value=mi.related_loan_opening or _loan_open, step=1_000_000,
            help="전기말 이월 잔액 — 적수 계산에 기초분(잔액 × 경과일수)으로 반영됩니다. "
                 "당기 신규 대여만 있으면 0",
        ))
        if _loan_open:
            st.caption(
                f"기초잔액 자동 집계 {_loan_open:,}원 ← {_loan_open_src} — "
                f"특수관계인 외 대여금이 섞여 있으면 수정하세요"
            )
        mi.dividend_ownership_ratio = float(st.number_input(
            "수입배당금 출자비율 (%)", min_value=0.0, max_value=100.0,
            value=mi.dividend_ownership_ratio * 100, step=1.0,
            help="수입배당금 익금불산입 비율 결정 (법§18의2). 배당금 자체는 분개장에서 자동 집계",
        )) / 100
        st.caption("간주임대료 — 부동산임대업 주업 + 차입금 과다 법인만 해당 (조특법§138)")
        # 임대보증금 분개 체크(받은 보증금 식별) + 임대물건별 기초 명세
        _render_deposit_classifier(mi, journals)
        # 계정별명세서·재무상태표에서 잔액 자동 집계 + 출처 표시
        _bs_deposit, _src_dep = _bs_amount_detail(loader, ("임대보증금", "전세보증금"))
        _bs_debt, _src_debt = _bs_amount_detail(loader, ("단기차입금", "장기차입금", "유동성장기부채"))
        _bs_equity, _src_eq = _bs_amount_detail(loader, ("자본총계",))
        if not _bs_equity:
            _bs_equity, _src_eq = _bs_amount_detail(loader, ("자본금",))
        if any((_bs_deposit, _bs_debt, _bs_equity)):
            st.markdown("**자동 집계 출처** (아래 기본값으로 반영, 수정 가능)")
            if _bs_deposit:
                st.caption(f"임대보증금 {_bs_deposit:,}원 ← {_src_dep}")
            if _bs_debt:
                st.caption(f"차입금 {_bs_debt:,}원 ← {_src_debt}")
            if _bs_equity:
                st.caption(f"자기자본 {_bs_equity:,}원 ← {_src_eq}")
        c3, c4, c5, c6 = st.columns(4)
        mi.rental_deposit = int(c3.number_input(
            "임대보증금 (원)", min_value=0,
            value=mi.rental_deposit or _bs_deposit, step=10_000_000,
        ))
        mi.rental_debt = int(c4.number_input(
            "차입금 잔액 (원)", min_value=0,
            value=mi.rental_debt or _bs_debt, step=10_000_000,
        ))
        mi.rental_equity = int(c5.number_input(
            "자기자본 (원)", min_value=0,
            value=mi.rental_equity or _bs_equity, step=10_000_000,
        ))
        mi.rental_bank_rate = float(c6.number_input(
            "정기예금이자율", min_value=0.0, max_value=0.2,
            value=mi.rental_bank_rate, step=0.001, format="%.3f",
        ))
        # 조특령§132⑤ 산식 입력값: (보증금 적수 − 건설비상당액 적수) × 1/365 × 이자율 − 금융수익
        _bs_con, _src_con = _bs_amount_detail(loader, ("건물", "구축물"))
        if _bs_con:
            st.caption(
                f"건물·구축물 취득가액 {_bs_con:,}원 ← {_src_con} — 아래 기본값으로 반영. "
                f"**일부만 임대하는 경우 임대용 면적 비율로 수정**하세요 (조특령§132⑥, 토지 제외)"
            )
        c7, c8, c9 = st.columns(3)
        mi.rental_construction_cost = int(c7.number_input(
            "임대용부동산 건설비상당액 (원)", min_value=0,
            value=mi.rental_construction_cost or _bs_con, step=10_000_000,
            help="토지가액 제외한 건물 건설비 (조특령§132⑥). 보증금 적수에서 적수로 차감됩니다.",
        ))
        mi.rental_area_ratio = float(c8.number_input(
            "임대 면적비율 (0~1)", min_value=0.0, max_value=1.0,
            value=mi.rental_area_ratio, step=0.01, format="%.2f",
            help="임대면적 ÷ 전체면적 (조특칙§59). 건설비상당액 적수를 면적 기준으로 안분합니다. "
                 "0이면 금액비율(건설비÷건물가액)로 폴백. 건물 전체 임대면 1.0.",
        ))
        mi.rental_financial_income = int(c9.number_input(
            "보증금 운용 금융수익 (원)", min_value=0,
            value=mi.rental_financial_income, step=1_000_000,
            help="보증금에서 발생한 이자·할인료·배당금 등 (조특령§132⑤). 간주익금에서 차감됩니다.",
        ))
        if mi.rental_deposit > 0:
            if mi.rental_debt <= mi.rental_equity * 2:
                st.info(
                    f"차입금 {mi.rental_debt:,}원 ≤ 자기자본 {mi.rental_equity:,}원 × 2 → "
                    "차입금 과다 요건 미충족 추정, 간주임대료 미적용 (조특령§132① — "
                    "5단계에서 적수 기준으로 재판정)"
                )
            else:
                _gross = int(max(0, mi.rental_deposit - mi.rental_construction_cost) * mi.rental_bank_rate)
                _incl = max(0, _gross - mi.rental_financial_income)
                st.caption(
                    f"예상 간주익금(잔액 기준 근사) = (보증금 {mi.rental_deposit:,} − 건설비 {mi.rental_construction_cost:,}) "
                    f"× {mi.rental_bank_rate:.1%} − 금융수익 {mi.rental_financial_income:,} = **{_incl:,}원** — "
                    "5단계에서는 분개장으로 **임대보증금·차입금 적수(積數)를 일별 계산**해 "
                    "정산합니다 (조특령§132⑤). 부동산임대업 주업 여부는 1단계 기본정보에서 판정"
                )

    with st.expander("자산수증익·채무면제익 이월결손금 보전 (법§18 6호, 영§16)"):
        st.caption(
            "결손 법인이 무상으로 받은 자산가액(국고보조금 제외)과 채무면제·소멸 이익 중 "
            "**이월결손금 보전에 충당한 금액은 익금불산입**(손금산입 △, 기타)입니다. "
            "보전 대상 이월결손금(영§16)은 법§14② 결손금 중 미공제분으로, "
            "**과세표준 공제기한(15년)이 지난 결손금도 포함**됩니다."
        )
        # 분개장 파싱 — 자산수증이익·채무면제이익 계정의 수익(대변) 합계를 prefill (금액만, 판단은 회계사)
        _gift_parsed = sum(
            ln.credit for ln in (journals or [])
            if "자산수증" in ln.account_name.replace(" ", "")
        )
        _debt_parsed = sum(
            ln.credit for ln in (journals or [])
            if any(k in ln.account_name.replace(" ", "") for k in ("채무면제", "채무조정이익"))
        )
        if _gift_parsed or _debt_parsed:
            st.caption(
                f"📄 분개장 발견 — 자산수증이익 **{_gift_parsed:,}원** · 채무면제이익 **{_debt_parsed:,}원** "
                "(계정 대변 합계). ⚠ 국고보조금(법§36)·출자전환분은 제외 대상이며 보전 충당액·이월결손금 범위는 "
                "분개로 확정 불가하니 회계사가 확인 후 적용하세요."
            )
            if st.button("분개 금액 불러오기 (수익 계상액 prefill)", key="gift_debt_prefill"):
                mi.asset_gift_revenue = int(_gift_parsed)
                mi.debt_forgiveness_revenue = int(_debt_parsed)
                st.rerun()
        cda, cdb = st.columns(2)
        mi.asset_gift_revenue = int(cda.number_input(
            "자산수증이익 (수익 계상액, 원)", min_value=0,
            value=mi.asset_gift_revenue, step=1_000_000,
            help="영업외수익으로 계상된 자산수증이익 (국고보조금 등 법§36 대상은 제외)",
        ))
        mi.debt_forgiveness_revenue = int(cdb.number_input(
            "채무면제이익 (수익 계상액, 원)", min_value=0,
            value=mi.debt_forgiveness_revenue, step=1_000_000,
            help="채무의 면제·소멸로 인한 부채 감소액 중 수익으로 계상된 금액. "
                 "출자전환분은 아래 체크 후 시가 초과분만 입력.",
        ))
        # 출자전환 채무면제익 분기 (법§17①1호 단서·영§15)
        mi.debt_forgiveness_equity_swap = st.checkbox(
            "출자전환으로 발생한 채무면제익이 포함되어 있는가? (법§17①1호 단서)",
            value=mi.debt_forgiveness_equity_swap,
        )
        if mi.debt_forgiveness_equity_swap:
            st.warning(
                "⚠ **출자전환 채무면제익** — 출자전환으로 발행한 주식의 **시가를 초과하는 채무면제분만** "
                "채무면제익(법§17①1호 단서·영§15)입니다. 시가 이하분은 주식발행초과금(익금불산입). "
                "위 '채무면제이익' 칸에는 **시가 초과분만** 입력하세요. "
                "이 채무면제익도 이월결손금 보전 충당분은 익금불산입(법§18 6호)."
            )
        mi.debt_relief_carryforward = int(st.number_input(
            "보전에 충당하는 이월결손금 (영§16, 원)", min_value=0,
            value=mi.debt_relief_carryforward, step=1_000_000,
            help="보전에 충당하는 이월결손금. 공제기한(15년)이 지난 결손금도 포함 가능 "
                 "(법§13 과세표준 공제용 이월결손금과 별개). 충당 여부·금액은 납세자 선택",
        ))
        _g18 = mi.asset_gift_revenue + mi.debt_forgiveness_revenue
        if _g18:
            _off18 = min(_g18, mi.debt_relief_carryforward)
            st.markdown(
                f"→ 익금불산입 = min(이익 {_g18:,}원, 이월결손금 {mi.debt_relief_carryforward:,}원) "
                f"= **{_off18:,}원** (나머지 {_g18 - _off18:,}원은 과세)"
            )
        st.divider()
        st.caption(
            "아래는 수익으로 계상한 경우에만 입력 — 전액 익금불산입 (법§18 4·5호). "
            "국세환급가산금·부가세 매출세액을 정상 회계처리했다면 0."
        )
        c18a, c18b = st.columns(2)
        mi.refund_interest_revenue = int(c18a.number_input(
            "국세환급금 이자 (수익 계상액, 원)", min_value=0,
            value=mi.refund_interest_revenue, step=100_000,
            help="국세·지방세 과오납 환급금에 부가된 이자(국세환급가산금)를 잡이익·이자수익으로 "
                 "계상한 금액 — 전액 익금불산입 (법§18 4호)",
        ))
        mi.vat_output_revenue = int(c18b.number_input(
            "부가가치세 매출세액 (수익 계상액, 원)", min_value=0,
            value=mi.vat_output_revenue, step=100_000,
            help="부가세 매출세액을 수익으로 계상한 경우 — 전액 익금불산입 (법§18 5호). "
                 "정상 회계처리 시 손익 미반영이라 0",
        ))

    with st.expander("중소기업 결손금 소급공제 환급 (법§72, 영§110) — 당기 결손 시"):
        st.caption(
            "당기 결손금이 발생한 **중소기업**은 직전 사업연도 법인세를 소급하여 환급받을 수 있습니다(법§72). "
            "환급세액 = 직전 산출세액 − (직전 과세표준 − 소급공제 결손금) × 직전 세율, "
            "한도는 직전 산출세액 − 직전 공제·감면세액(영§110①). "
            "**당기 결손금은 5단계에서 자동 산정**되며, 아래는 직전 사업연도 신고서 값만 입력합니다."
        )
        mi.loss_carryback_enabled = st.checkbox(
            "결손금 소급공제 환급을 검토한다 (당기 결손 + 중소기업)",
            value=mi.loss_carryback_enabled,
        )
        if mi.loss_carryback_enabled:
            mi.loss_carryback_both_filed = st.checkbox(
                "당기·직전 사업연도 모두 기한내 신고했다 (법§72④ 요건)",
                value=mi.loss_carryback_both_filed,
            )
            clc1, clc2 = st.columns(2)
            mi.loss_carryback_prior_tax_base = int(clc1.number_input(
                "직전 사업연도 과세표준 (원)", min_value=0, step=1_000_000,
                value=int(mi.loss_carryback_prior_tax_base),
                help="직전연도 법인세 신고서(과세표준및세액조정계산서)의 과세표준",
            ))
            mi.loss_carryback_prior_gross_tax = int(clc2.number_input(
                "직전 사업연도 산출세액 (원)", min_value=0, step=1_000_000,
                value=int(mi.loss_carryback_prior_gross_tax),
                help="§55의2 토지등 양도소득에 대한 법인세는 제외한 산출세액 (법§72①1호)",
            ))
            mi.loss_carryback_prior_credit = int(st.number_input(
                "직전 사업연도 공제·감면세액 (원)", min_value=0, step=1_000_000,
                value=int(mi.loss_carryback_prior_credit),
                help="한도(직전 법인세액 = 산출세액 − 공제·감면세액, 영§110①) 산정용. "
                     "가산세는 포함하지 않습니다.",
            ))
            mi.loss_carryback_requested_loss = int(st.number_input(
                "신청 소급공제 결손금 (원, 0이면 상한 전액)", min_value=0, step=1_000_000,
                value=int(mi.loss_carryback_requested_loss),
                help="소급공제를 신청할 결손금. 0이면 상한(min[당기결손금, 직전 과표]) 전액을 적용합니다. "
                     "일부만 신청하면 잔여 결손금은 이월공제(법§13①1호) 대상으로 남습니다.",
            ))
            mi.loss_carryback_step2_override = int(st.number_input(
                "직전 세율 2호 직접 입력 (원, 직전연도 2022 이하일 때만)", min_value=0, step=1_000_000,
                value=int(mi.loss_carryback_step2_override),
                help="엔진 세율테이블은 2023년 이후만 수록 — 직전 사업연도가 2022년 이하이면 "
                     "(직전 과표 − 소급공제 결손금) × 직전 세율을 직접 계산해 입력하세요. 0이면 미입력.",
            ))
            st.caption(
                "⚠ 추징 주의(법§72⑤): 추후 결손금 경정 감소·직전 경정·중소기업 탈락 시 "
                "환급세액 + 이자상당액(1일 10만분의 22, 영§110④)이 징수됩니다. "
                "환급 신청 여부·금액은 회계사·납세자가 확정합니다. 환급가능세액 초안은 5단계에서 산출됩니다."
            )

    with st.expander("➕ 세무조정 직접 입력 (규칙엔진 미포착 항목 수동 가감)"):
        st.caption(
            "규칙엔진이 자동 계산하지 못한 세무조정을 회계사가 직접 추가합니다. "
            "입력한 항목은 **소득금액조정합계표(별지15호)**에 가산/차감으로 반영되고 "
            "각사업연도소득·과세표준에 합산됩니다. **유보/△유보로 처분하면 자본금과적립금조정명세서(을)에 "
            "자동 반영**되어 차기로 승계됩니다. 금액·소득처분·근거는 회계사가 확정합니다."
        )
        _CAT_OPTS = ["익금산입", "손금불산입", "손금산입", "익금불산입"]
        # 조정구분에 맞는 소득처분만 노출 (사외유출은 가산에만 성립, 차감은 △유보·기타)
        _DISP_ADD = ["유보", "상여", "배당", "기타사외유출", "기타", "검토필요"]
        _DISP_DED = ["△유보", "기타", "검토필요"]
        _existing_ca = mi.custom_adjustments or []
        _n_ca = st.number_input(
            "직접 입력할 세무조정 항목 수", min_value=0, max_value=30,
            value=len(_existing_ca), step=1, key="custom_adj_count",
        )
        _rows_ca: list[dict] = []
        for i in range(int(_n_ca)):
            _ex = _existing_ca[i] if i < len(_existing_ca) else {}
            st.markdown(f"**항목 {i+1}**")
            c1, c2 = st.columns([3, 2])
            _name = c1.text_input(
                "항목명", value=str(_ex.get("name", "")), key=f"custom_adj_name_{i}",
                placeholder="예: 임대료 귀속시기 차이 익금산입",
            )
            _cat = c2.selectbox(
                "조정구분", _CAT_OPTS,
                index=_CAT_OPTS.index(_ex["category"]) if _ex.get("category") in _CAT_OPTS else 0,
                key=f"custom_adj_cat_{i}",
            )
            c3, c4 = st.columns([2, 2])
            _amt = c3.number_input(
                "금액(원)", min_value=0, step=1_000_000,
                value=int(_ex.get("amount", 0)), key=f"custom_adj_amt_{i}",
                help="차감은 금액을 음수로 넣지 말고 조정구분(손금산입/익금불산입)으로 선택하세요.",
            )
            _disp_opts = _DISP_ADD if _cat in ("익금산입", "손금불산입") else _DISP_DED
            _disp = c4.selectbox(
                "소득처분", _disp_opts,
                index=_disp_opts.index(_ex["disposition"]) if _ex.get("disposition") in _disp_opts else 0,
                key=f"custom_adj_disp_{i}",
            )
            _basis = st.text_input(
                "근거(법령·사유)", value=str(_ex.get("basis", "")), key=f"custom_adj_basis_{i}",
                placeholder="예: 법§40 권리의무확정주의 — 당기 귀속 임대료",
            )
            if _name.strip() and _amt:
                _rows_ca.append({
                    "name": _name.strip(), "amount": int(_amt), "category": _cat,
                    "disposition": _disp, "basis": _basis.strip(),
                })
            if i < int(_n_ca) - 1:
                st.divider()
        mi.custom_adjustments = _rows_ca
        if _rows_ca:
            _add_sum = sum(x["amount"] for x in _rows_ca if x["category"] in ("익금산입", "손금불산입"))
            _ded_sum = sum(x["amount"] for x in _rows_ca if x["category"] in ("손금산입", "익금불산입"))
            st.markdown(
                f"→ 직접 입력 합계: **가산 {_add_sum:,}원** · **차감 {_ded_sum:,}원** "
                f"(순효과 {_add_sum - _ded_sum:+,}원 — 각사업연도소득에 반영)"
            )
            st.caption("⚠ 직접 입력 항목은 규칙엔진·법령 검증을 거치지 않습니다 — 금액·소득처분·근거의 정확성은 회계사 책임입니다.")

    with st.expander("부당행위계산 부인 (법§52, 영§88) — 특수관계인 거래 검토"):
        st.caption(
            "고가매입·저가양도·자산 무상이전 등은 시가 비교가 필요해 자동 계산하지 않습니다 "
            "(영§88③: 시가와 거래가액의 차액이 3억원 이상이거나 시가의 5% 이상인 경우에 한해 적용). "
            "금전 대여(영§88①6호)는 위 가지급금 인정이자에서 자동 계산되므로 여기에 중복 입력하지 마세요."
        )
        # 특수관계인 거래 분개 참고 표시 (거래처 매칭)
        _rp_nm = _rp_names(related_parties)
        if journals and _rp_nm:
            _rp_lines = [
                ln for ln in journals
                if (ln.counterparty_name or "").strip()
                and any(nm in ln.counterparty_name or ln.counterparty_name.strip() in nm
                        for nm in _rp_nm)
                # 가지급금·대여금·인건비성 계정은 별도 조정에서 처리 — 참고 표에서 제외
                and not any(k in ln.account_name.replace(" ", "")
                            for k in ("가지급금", "대여금", "가수금", "급여", "상여", "퇴직"))
            ]
            if _rp_lines:
                import pandas as pd
                st.markdown(f"**특수관계인 거래 분개 {len(_rp_lines):,}건** (검토 참고용)")
                st.dataframe(pd.DataFrame([
                    {
                        "날짜": str(ln.date), "계정과목": ln.account_name,
                        "적요": ln.description, "거래처": ln.counterparty_name,
                        "차변": f"{ln.debit:,}" if ln.debit else "",
                        "대변": f"{ln.credit:,}" if ln.credit else "",
                    }
                    for ln in _rp_lines[:300]
                ]), use_container_width=True, hide_index=True, height=240)
                if len(_rp_lines) > 300:
                    st.caption(f"{len(_rp_lines):,}건 중 300건만 표시")
            else:
                st.caption("특수관계인 목록과 일치하는 거래처의 분개가 없습니다 (가지급금·인건비 제외).")
        elif not _rp_nm:
            st.caption("1단계에서 특수관계인 목록을 저장하면 관련 거래 분개가 여기에 표시됩니다.")

        # ── 건별 질문형 입력 (금전대여 제외·영§88③ 게이트·건별 소득처분) ──
        st.divider()
        _cand_labels: list[str] = []
        if journals and _rp_nm and _rp_lines:
            _cand_labels = [
                f"{str(ln.date)} · {ln.account_name} · {ln.counterparty_name} · "
                f"{(ln.debit or ln.credit):,}원"
                for ln in _rp_lines[:300]
            ]
        _render_review_line_cards(mi, unfair_transaction_spec(), _cand_labels)

    with st.expander("의제배당 (법§16①) — 감자·해산·합병·무상증자 등"):
        st.caption(
            "감자·소각·퇴사·해산·합병·분할·무상증자(잉여금 자본전입) 시 교부받은 재산·주식가액이 "
            "주식 취득가액을 초과하면 의제배당으로 익금산입(법§16①). 무상증자(2호)는 취득가액 차감 "
            "없이 전액, 상법§459① 자본준비금·재평가적립금 자본전입은 제외."
        )
        st.caption(
            "후보는 ① 적요에 감자·소각·합병·분할·잔여재산 등이 있는 분개 ② **투자주식 계정(매도가능증권·"
            "관계기업투자주식 등)의 대변(처분·감소) 분개**에서 추출합니다. ⚠ **무상주 수령(2호)·미인식 감자**는 "
            "회계상 분개가 없을 수 있어 자동 후보로 안 잡힙니다 — 주식변동·배당통지로 직접 확인해 카드를 추가하세요."
        )
        _DD_INV_ACCTS = ("매도가능증권", "관계기업투자", "투자주식", "지분법적용투자",
                         "단기매매증권", "당기손익인식금융자산", "기타포괄손익")
        # 후보 300건에서 조기종료 — 49k 전건 순회 회피(islice generator)
        _dd_cands = list(islice((
            f"{str(ln.date)} · {ln.account_name} · {ln.description[:20]} · "
            f"{(ln.debit or ln.credit):,}원"
            for ln in (journals or [])
            if any(k in (ln.description or "")
                   for k in ("유상감자", "무상주", "잉여금", "감자", "소각", "합병", "분할",
                             "청산", "잔여재산", "자본전입"))
            or (any(a in (ln.account_name or "") for a in _DD_INV_ACCTS) and (ln.credit or 0) > 0)
        ), 300))
        _render_review_line_cards(mi, deemed_dividend_spec(), _dd_cands)

    with st.expander("세액공제·감면 / 가산세 / 기납부세액 (법§55~64·73, 조특법)"):
        st.caption(
            "산출세액 이후 차감 항목입니다. 항목명에 **조특§7·§24·§10·§29의7**을 적으면 해당 "
            "**산식 입력칸**이 나타나 회계사가 인자(투자액·율·산출세액 등)만 입력하면 공제·감면액이 "
            "자동 산출됩니다. 최저한세·농특세 적용 여부는 카탈로그 분류로 자동 제시되며 체크로 확정합니다 "
            "(조특§132·농특세법§4). 율·요건 충족은 회계사 최종 확인."
        )
        _n_credit = int(st.number_input(
            "세액공제·감면 항목 수", min_value=0, max_value=20,
            value=len(mi.tax_credit_items), step=1,
        ))
        _company = getattr(st.session_state.get("project", None), "company", None)
        _credits: list[dict] = []
        for _i in range(_n_credit):
            _prev = mi.tax_credit_items[_i] if _i < len(mi.tax_credit_items) else {}
            _nm = st.text_input(
                f"항목명 #{_i + 1}", value=str(_prev.get("name", "")),
                key=f"tc_name_{_i}",
                placeholder="예: 통합투자세액공제(조특§24)·R&D세액공제(조특§10)·중소기업특별감면(조특§7)·고용증대(조특§29의7)",
            )
            _spec = lookup_credit_spec(_nm) if _nm else None
            _ftype = credit_formula_type(_nm)
            # 산식 매칭 항목 → 산식 입력칸으로 자동 산출(회계사는 인자만 입력). 미매칭 → 금액 직접 입력.
            if _ftype:
                _amt, _formula = render_credit_formula(_ftype, _prev.get("formula", {}), _company, _i)
            else:
                _amt = int(st.number_input(
                    f"공제·감면액 #{_i + 1} (원)", min_value=0,
                    value=int(_prev.get("amount", 0) or 0), step=100_000, key=f"tc_amt_{_i}",
                    help="항목명에 조특§7·24·10·29의7을 적으면 산식 입력칸이 나타나 자동 산출됩니다.",
                ))
                _formula = {}
            if _spec:
                st.caption(
                    f"📑 **{_spec.article}** 추천 분류 — 최저한세 "
                    f"**{'적용' if _spec.subject_to_min_tax else '미적용'}** · 농특세 "
                    f"**{'과세' if _spec.farm_surtax_taxable else '비과세'}** "
                    f"({_spec.note}) — 아래 체크박스로 최종 확정"
                )
            cc3, cc4 = st.columns(2)
            # 최저한세·농특세 기본값을 카탈로그 추천 분류에서 자동 제시 (요건 자동검토)
            _smt = cc3.checkbox(
                f"최저한세 적용 #{_i + 1}",
                value=bool(_prev.get("subject_to_min_tax",
                                     _spec.subject_to_min_tax if _spec else True)),
                key=f"tc_smt_{_i}",
                help="조특§132 최저한세 적용대상이면 체크. 중소기업 R&D세액공제 등은 미적용 — 해제",
            )
            _fst = cc4.checkbox(
                f"농특세 과세 #{_i + 1}",
                value=bool(_prev.get("farm_surtax_taxable",
                                     _spec.farm_surtax_taxable if _spec else False)),
                key=f"tc_fst_{_i}",
                help="농어촌특별세 과세대상이면 체크(감면세액×20%, 농특세법§5①). "
                     "조특§7 중소기업 특별감면·R&D는 비과세(농특세법§4) — 해제",
            )
            _credits.append({
                "name": _nm, "amount": _amt, "formula": _formula,
                "subject_to_min_tax": _smt, "farm_surtax_taxable": _fst,
            })
            if _i < _n_credit - 1:
                st.divider()
        mi.tax_credit_items = _credits

        cga, cgb = st.columns(2)
        mi.surtax_amount = int(cga.number_input(
            "가산세 합계 (원)", min_value=0, value=mi.surtax_amount, step=100_000,
            help="무신고·과소신고·납부지연 가산세(국기법§47의2~4) + 지급명세서·계산서 등 "
                 "불성실 가산세(법§75 계열). 산출세액에 가산. 아래 계산기로 자동 산정 가능",
        ))
        mi.prepaid_tax_amount = int(cgb.number_input(
            "기납부세액 (원)", min_value=0, value=mi.prepaid_tax_amount, step=100_000,
            help="중간예납세액(법§63) + 원천납부세액(법§73) + 수시부과세액. 차감납부세액에서 차감",
        ))

        with st.popover("가산세 계산기 (국기법§47의2~4)"):
            st.caption("무신고와 과소신고는 동시 적용되지 않습니다 — 해당하는 하나만 입력하세요.")
            _nf_tax = int(st.number_input("무신고납부세액 (원)", min_value=0, value=0, step=100_000, key="sx_nf"))
            _nf_fraud = st.checkbox("부정행위 (무신고 40%·역외 60%)", key="sx_nf_fraud")
            _nf_off = st.checkbox("역외거래 부정", key="sx_nf_off")
            _nf_rev = int(st.number_input("수입금액 (법인 비교용, 원)", min_value=0, value=0, step=10_000_000, key="sx_rev"))
            _ur_tax = int(st.number_input("과소신고납부세액 (원)", min_value=0, value=0, step=100_000, key="sx_ur"))
            _ur_fraud = int(st.number_input("그 중 부정행위분 (원)", min_value=0, value=0, step=100_000, key="sx_ur_fraud"))
            _lp_tax = int(st.number_input("미납·과소납부세액 (원)", min_value=0, value=0, step=100_000, key="sx_lp"))
            _lp_days = int(st.number_input("미납 일수", min_value=0, value=0, step=1, key="sx_days"))
            _other = int(st.number_input("기타 가산세 (법§75 계열 수기 합산, 원)", min_value=0, value=0, step=100_000, key="sx_other"))
            if _nf_tax > 0 and _ur_tax > 0:
                st.warning(
                    "무신고와 과소신고는 동시 적용되지 않습니다 (무신고면 과소신고 없음). "
                    "둘 다 입력하면 합산되어 과대 산정되니 해당하는 하나만 입력하세요."
                )
            _sr = aggregate_surtax(
                no_filing_tax=_nf_tax, no_filing_fraud=_nf_fraud, no_filing_offshore=_nf_off,
                revenue=_nf_rev,
                under_report_tax=_ur_tax, under_report_fraud_portion=_ur_fraud,
                unpaid_tax=_lp_tax, unpaid_days=_lp_days, other_manual=_other,
            )
            st.markdown(
                f"무신고 {_sr.no_filing:,} · 과소신고 {_sr.under_report:,} · "
                f"납부지연 {_sr.late_payment:,} · 기타 {_sr.other_manual:,} = **합계 {_sr.total:,}원**"
            )
            if st.button("위 합계를 가산세로 적용", key="sx_apply"):
                mi.surtax_amount = _sr.total
                st.success(f"가산세 {_sr.total:,}원을 적용했습니다. 위 '가산세 합계'에 반영됩니다.")
        if _credits or mi.surtax_amount or mi.prepaid_tax_amount:
            _tc_sum = sum(c["amount"] for c in _credits)
            st.caption(
                f"세액공제·감면 합계 {_tc_sum:,}원 · 가산세 {mi.surtax_amount:,}원 · "
                f"기납부세액 {mi.prepaid_tax_amount:,}원 → 5단계 차감납부세액에 반영됩니다."
            )

        st.divider()
        st.caption(
            "토지등 양도소득에 대한 법인세 (법§55의2) — 비사업용토지·주택·별장·조합원입주권·분양권 "
            "양도 시 일반 법인세에 **추가 납부**(최저한세·세액공제 대상 아님). 해당 없으면 0."
        )
        clt1, clt2, clt3 = st.columns([2, 2, 1])
        mi.land_transfer_income = int(clt1.number_input(
            "토지등 양도소득 (원)", min_value=0, value=mi.land_transfer_income, step=1_000_000,
            help="양도가액 − 장부가액 등으로 계산한 양도소득",
        ))
        _lt_types = ["비사업용토지", "주택별장", "조합원입주권분양권"]
        mi.land_transfer_type = clt2.selectbox(
            "자산 유형", _lt_types,
            index=_lt_types.index(mi.land_transfer_type) if mi.land_transfer_type in _lt_types else 0,
            help="비사업용토지 10% · 주택/별장 20% · 조합원입주권/분양권 20% (미등기 비사업용토지·주택별장 40%)",
        )
        mi.land_transfer_unregistered = clt3.checkbox(
            "미등기", value=mi.land_transfer_unregistered,
            help="미등기 양도 — 비사업용토지·주택별장은 40% 적용 (법§55의2① 2·3호). "
                 "단 장기할부·법령상 등기불능 등 영§92의2④ 미등기 제외사유에 해당하면 미등기로 보지 "
                 "않으니 체크 해제 (회계사 판단).",
        )
        if mi.land_transfer_income:
            _lt_rate = {"비사업용토지": (0.10, 0.40), "주택별장": (0.20, 0.40),
                        "조합원입주권분양권": (0.20, 0.20)}.get(mi.land_transfer_type, (0.0, 0.0))
            _r = _lt_rate[1] if mi.land_transfer_unregistered else _lt_rate[0]
            st.markdown(
                f"→ 토지등 양도소득 법인세 = {mi.land_transfer_income:,}원 × {_r:.0%} "
                f"= **{int(mi.land_transfer_income * _r):,}원** (일반 법인세에 추가)"
            )


def render_prior_reserves(existing: list | None = None) -> list[dict]:
    """전기 유보잔액 입력 — existing(전년 승계분)이 있으면 기본값으로 채운다."""
    existing = existing or []
    st.subheader("전기 유보잔액")
    st.caption("항목별 기초잔액. 전기 신고서 자본금·적립금 조정명세서(을) 기준." +
               (" (전년도 자료에서 승계됨 — 추인 여부 확인)" if existing else ""))
    n = st.number_input(
        "유보 항목 수", min_value=0, max_value=50,
        value=len(existing), step=1,
    )
    items = []
    for i in range(int(n)):
        _ex = existing[i] if i < len(existing) else {}
        c1, c2, c3 = st.columns(3)
        with c1:
            code = st.text_input(
                f"항목명 {i+1}", value=str(_ex.get("code", "")), key=f"res_code_{i}",
            )
        with c2:
            amount = st.number_input(
                f"금액(원) {i+1}", step=1_000_000,
                value=int(_ex.get("amount", 0)), key=f"res_amt_{i}",
            )
        with c3:
            disp = st.selectbox(
                f"처분구분 {i+1}", ["유보", "△유보"],
                index=(1 if str(_ex.get("disposition", "")) == "△유보" else 0),
                key=f"res_disp_{i}",
            )
        items.append({"code": code, "amount": int(amount), "disposition": disp})
    return items
