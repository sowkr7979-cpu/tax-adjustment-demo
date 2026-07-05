"""4단계 — AI 검토 보조 (규칙 기반 검토 큐 + 선택적 LLM 메모 보조)."""
from __future__ import annotations
import threading
import time
from datetime import date

import streamlit as st

from src.parsers.smart_a import SmartALoader
from src.rules.classifier import classify_all
from src.llm.ollama_client import OllamaClient
from src.llm.analyzer import JournalAnalyzer
from src.ui.styles import page_header, section_title, info_card, striped_by_group
from src.utils.models import issue_label
from src.utils.safe_export import safe_df
from src.views.common import _parse_stored_date


def render(proj, llm_ok: bool) -> None:
    st.markdown(page_header(
        "AI 검토 보조 (선택)",
        "이 단계는 선택입니다 — 세무조정 계산(5단계)은 LLM 없이 규칙 엔진만으로 완료됩니다. "
        "LLM은 대량 분개 판단용이 아니라 검토 큐 요약·자료요청·검토메모 초안 작성용입니다.",
    ), unsafe_allow_html=True)

    loader: SmartALoader = st.session_state.loader

    if not loader.journals:
        st.markdown(info_card(
            "<b style='color:#1a73e8;'>안내</b> &nbsp; 먼저 2단계에서 분개장 파일을 업로드하세요."
        ), unsafe_allow_html=True)
        st.stop()

    rp_set = set(proj.manual_input.related_parties)
    total = len(loader.journals)
    stage2_cnt = len(
        [r for r in st.session_state.get("rule_results", []) if r.forward_to_stage2]
    )

    m1, m2, m3 = st.columns(3, gap="medium")
    m1.metric("전체 분개", f"{total:,}건")
    m2.metric("1차 완료", f"{len(st.session_state.get('rule_results', [])):,}건")
    m3.metric("LLM 2차 대상", f"{stage2_cnt:,}건")

    st.divider()

    st.markdown(section_title(
        "1단계 — 규칙 기반 분류",
        "계정코드·키워드 룰로 세무 이슈 가능 분개를 필터링합니다.",
    ), unsafe_allow_html=True)

    col_r1, _ = st.columns([1, 4])
    with col_r1:
        if st.button("1차 규칙 분류 실행", width="stretch"):
            with st.spinner("계정코드 기반 분류 중..."):
                rule_results = classify_all(loader.journals, rp_set)
                target = [r for r in rule_results if r.forward_to_stage2]
                st.session_state.rule_results = rule_results
                pct = 100 * len(target) / max(len(rule_results), 1)
                st.success(
                    f"1차 분류 완료 — LLM 2차 대상 {len(target):,}건 ({pct:.1f}%)"
                )

    # ── 1차 분류 내역 보기 (이슈코드별 드릴다운) ──
    _rrs = [r for r in st.session_state.get("rule_results", []) if r.rule_issue_code is not None]
    if _rrs:
        _by_issue: dict[str, list] = {}
        for r in _rrs:
            _by_issue.setdefault(r.rule_issue_code.value, []).append(r)

        with st.expander(
            f"1차 분류 내역 보기 — 이슈 분류 {len(_rrs):,}건 / 이슈코드 {len(_by_issue)}종"
        ):
            import pandas as pd
            # 이슈코드별 요약
            st.dataframe(pd.DataFrame([
                {
                    "이슈 분류": issue_label(code),
                    "이슈코드": code,
                    "분류 건수": f"{len(rs):,}",
                    "LLM 2차 대상": f"{sum(1 for x in rs if x.forward_to_stage2):,}",
                    "분류 근거": ", ".join(sorted({x.forward_reason or "" for x in rs} - {""})),
                }
                for code, rs in sorted(_by_issue.items(), key=lambda kv: -len(kv[1]))
            ]), width="stretch", hide_index=True)

            # 이슈코드 선택 → 분개 내역
            _issue_names = [f"{issue_label(c)} ({len(rs):,}건)" for c, rs in sorted(_by_issue.items(), key=lambda kv: -len(kv[1]))]
            _issue_keys = [c for c, rs in sorted(_by_issue.items(), key=lambda kv: -len(kv[1]))]
            _isel = st.selectbox(
                "이슈코드 선택 — 해당 분개 내역 표시",
                range(len(_issue_names)),
                format_func=lambda i: _issue_names[i],
                key="rule_drill_select",
            )
            _sel_pairs = {
                (r.journal_id, r.account_code) for r in _by_issue[_issue_keys[_isel]]
            }
            _matched = [
                ln for ln in loader.journals
                if (ln.journal_id, ln.account_code) in _sel_pairs
            ]
            _rdf = pd.DataFrame([
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
                for ln in _matched[:1000]
            ])
            if len(_matched) > 1000:
                st.caption(f"⚠ {len(_matched):,}건 중 1,000건만 표시 — 전체는 CSV로 다운로드하세요.")
            st.dataframe(
                striped_by_group(_rdf), width="stretch",
                hide_index=True, height=360,
            )
            _rcsv_df = pd.DataFrame([
                {
                    "날짜": str(ln.date), "전표번호": ln.journal_id,
                    "계정코드": ln.account_code, "계정과목": ln.account_name,
                    "적요": ln.description, "거래처": ln.counterparty_name,
                    "차변": ln.debit, "대변": ln.credit,
                    "원본위치": f"{ln.source_sheet}!행{ln.source_row}",
                }
                for ln in _matched
            ])
            st.download_button(
                "이 분류 내역 전체 CSV 다운로드",
                data=safe_df(_rcsv_df).to_csv(index=False).encode("utf-8-sig"),
                file_name=f"1차분류_{_issue_keys[_isel]}.csv",
                mime="text/csv",
                key="rule_drill_csv",
            )

    st.divider()

    st.markdown(section_title(
        "2단계 — 선택 거래 메모 보조",
        "로컬 LLM(Ollama)으로 회계사가 고른 소수 검토 큐만 요약·메모화합니다 (고객자료 외부 미전송).",
    ), unsafe_allow_html=True)

    if not llm_ok:
        st.markdown(info_card(
            "<b style='color:#0d0d0d;'>AI 검토보조는 선택 기능입니다</b> &nbsp; "
            "현재 로컬 Ollama가 실행 중이 아니어서 비활성 상태이며, 세무조정 계산(5단계)은 규칙엔진만으로 완결됩니다. "
            "활성화하려면 Ollama를 실행하고 모델을 준비하세요 (<code>ollama pull gemma4</code>). "
            "설계상 AI는 금액을 확정하지 않고 검토메모·요약만 보조합니다(ADR-002)."
        ), unsafe_allow_html=True)

    _job = st.session_state.get("llm_job")
    _job_running = bool(_job and _job.get("status") == "running")

    # ── 분석 대상 선택 — 1차 분류 이슈별로 골라서 LLM에 보낸다 ──
    _stage2_by_issue: dict[str, int] = {}
    for r in st.session_state.get("rule_results", []):
        if r.forward_to_stage2:
            _code = r.rule_issue_code.value if r.rule_issue_code is not None else "UNKNOWN"
            _stage2_by_issue[_code] = _stage2_by_issue.get(_code, 0) + 1

    _selected_issues: set[str] | None = None
    if _stage2_by_issue:
        _opts = sorted(_stage2_by_issue, key=lambda c: -_stage2_by_issue[c])
        _picked = st.multiselect(
            "AI 보조를 실행할 이슈 분류 선택 — 기본 미선택, 필요한 분류만 고르세요",
            options=_opts,
            default=[],
            format_func=lambda c: f"{issue_label(c)} — {_stage2_by_issue[c]:,}건",
            key="llm_issue_pick",
        )
        _selected_issues = set(_picked)
        _sel_cnt = sum(_stage2_by_issue[c] for c in _picked)
        _est_sec = max(_sel_cnt * 60, 10)  # CPU 추론 실측 분개 1건당 약 1분 (gemma4, 12 tok/s)
        _too_many = _sel_cnt > 30  # 로컬 CPU 추론 시간 보호
        st.caption(
            f"선택된 분석 대상 **{_sel_cnt:,}건** · 예상 소요 약 {_est_sec // 60}분 {_est_sec % 60}초 "
            f"(로컬 LLM 기준, 권장 30건 이하)"
        )
        if _too_many:
            st.warning(
                "선택 대상이 30건을 초과합니다. 로컬 CPU 추론은 1건당 약 1분이 걸리므로 "
                "금액 상위 거래나 특정 이슈만 좁혀서 실행하세요."
            )
    else:
        _too_many = False

    col_r2, _ = st.columns([1, 4])
    with col_r2:
        run_llm = st.button(
            "선택 큐 AI 보조 실행" if not _job_running else "분석 실행 중...",
            width="stretch",
            disabled=(
                "rule_results" not in st.session_state or not llm_ok or _job_running
                or (_selected_issues is not None and not _selected_issues)
                or _too_many
            ),
        )

    if run_llm:
        fy_end_val = _parse_stored_date(proj.company.fiscal_year_end, date.today())
        analyzer = JournalAnalyzer(
            client=OllamaClient(),
            fiscal_year_end=fy_end_val,
            company_name=proj.company.name,
            is_sme=proj.company.is_sme,
            related_parties=proj.manual_input.related_parties,
        )
        # 백그라운드 스레드 실행 — 다른 페이지로 이동해도 분석이 계속된다
        shared: dict = {"status": "running", "done": 0, "total": 0,
                        "results": None, "error": "", "started": time.time()}
        st.session_state.llm_job = shared

        def _worker(
            analyzer=analyzer,
            journals=loader.journals,
            rule_results=st.session_state.rule_results,
            shared=shared,
            issue_filter=_selected_issues,
        ) -> None:
            try:
                def _cb(done: int, total: int) -> None:
                    shared["done"], shared["total"] = done, total
                res = analyzer.analyze_batch(
                    journals, rule_results,
                    progress_callback=_cb, issue_filter=issue_filter,
                )
                shared["results"] = res
                shared["status"] = "completed"
            except Exception as e:
                shared["status"] = "error"
                shared["error"] = f"{type(e).__name__}: {e}"

        threading.Thread(target=_worker, daemon=True).start()
        st.rerun()

    # 진행 상태 표시 (실행 중이면 어느 시점에 돌아와도 여기서 확인 가능)
    _job = st.session_state.get("llm_job")
    if _job:
        if _job["status"] == "running":
            _total = _job["total"]
            _elapsed = int(time.time() - _job["started"])
            if _total:
                st.progress(
                    min(_job["done"] / _total, 1.0),
                    text=f"AI 보조 진행 중... {_job['done']:,}/{_total:,}건 "
                         f"(경과 {_elapsed // 60}분 {_elapsed % 60}초) — "
                         f"다른 페이지로 이동해도 분석은 계속됩니다",
                )
            else:
                st.progress(0.0, text="AI 보조 준비 중... (첫 배치 처리 중)")
            _c1, _c2 = st.columns([1, 3])
            if _c1.button("진행 상황 새로고침"):
                st.rerun()
            if _c2.checkbox("자동 새로고침 (10초)", value=True, key="llm_autorefresh"):
                time.sleep(10)
                st.rerun()
        elif _job["status"] == "error":
            st.error(f"AI 보조 오류: {_job['error']}")
            if st.button("오류 확인 (닫기)"):
                st.session_state.llm_job = None
                st.rerun()
        elif _job["status"] == "completed":
            _res = _job["results"] or []
            st.session_state.llm_results = _res
            st.session_state.llm_job = None
            if _res:
                st.success(f"AI 보조 완료 — {len(_res):,}건 처리됨")
            else:
                st.warning(
                    "AI 보조가 완료되었으나 유효한 결과가 없습니다. "
                    "모델 응답이 JSON 형식이 아니거나 컨텍스트 한계를 초과했을 수 있습니다."
                )

    if st.session_state.llm_results:
        st.divider()
        st.markdown(section_title("분석 결과"), unsafe_allow_html=True)
        import pandas as pd
        rows = [
            {
                "전표번호":    r.journal_id,
                "이슈 분류":   issue_label(r.tax_issue_code.value),
                "이슈가능":    "✓" if r.issue_possible else "—",
                "신뢰도":      round(r.stage2_confidence, 2),
                "검토필요":    "⚠" if r.review_required else "",
                "해당금액(원)": f"{r.affected_amount:,}",
                "사유":        r.review_reason[:60],
            }
            for r in st.session_state.llm_results
        ]
        st.dataframe(pd.DataFrame(rows), width="stretch", height=380)

