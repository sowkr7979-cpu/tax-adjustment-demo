"""2단계 — 재무제표 업로드 (표준화 파이프라인 + 진단 리포트)."""
from __future__ import annotations
import os
import tempfile
from pathlib import Path

import streamlit as st

from src.parsers.smart_a import SmartALoader
from src.ui.styles import page_header, section_title


def _load_uploads(loader: SmartALoader, files: dict) -> tuple[dict, int, int]:
    """업로드 객체 dict({유형: UploadedFile|None})를 임시파일 경유로 파싱한다.

    회계 원본이 임시폴더에 남지 않도록 파싱 직후 임시파일을 삭제한다.
    반환: (파일별 오류 dict, 성공 건수, 시도 건수).
    """
    paths: dict[str, str] = {}
    try:
        for k, f in files.items():
            if f is None:
                continue
            ext = Path(f.name).suffix or ".xls"
            f.seek(0)
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(f.read())
                paths[k] = tmp.name
        errors = loader.load(paths) if paths else {}
    finally:
        for p in paths.values():
            try:
                os.unlink(p)
            except OSError:
                pass
    return errors, len(paths) - len(errors), len(paths)


def render(loader: SmartALoader) -> None:
    st.markdown(page_header(
        "재무제표 업로드",
        "회계 프로그램(Smart A·WEHAGO 등)에서 내보낸 Excel 파일을 유형별로 업로드합니다. "
        "양식이 달라도 자동 인식하며, 계정코드가 없으면 분개장 코드로 보충합니다.",
    ), unsafe_allow_html=True)

    loader: SmartALoader = st.session_state.loader

    FILE_DEFS = [
        ("재무상태표",          "재무상태표 (B/S)"),
        ("손익계산서",          "손익계산서 (P&L)"),
        ("원가명세서",          "제조원가명세서"),
        ("이익잉여금처분계산서", "이익잉여금처분계산서"),
        ("고정자산대장",        "유형자산·무형자산 대장"),
        ("분개장",              "전표·분개장"),
        ("계정별원장",          "계정별원장"),
        ("계정별명세서",        "계정별 잔액명세서 (임대보증금·차입금 등 자동 분석)"),
        ("결산부속명세서",      "결산부속명세서 (계정별 거래처 세부 — 업무무관자산 드릴다운)"),
    ]

    file_types: dict[str, object | None] = {name: None for name, _ in FILE_DEFS}  # 업로드 파일 객체

    for i in range(0, len(FILE_DEFS), 2):
        cols = st.columns(2, gap="medium")
        for j, col in enumerate(cols):
            if i + j >= len(FILE_DEFS):
                break
            name, label = FILE_DEFS[i + j]
            with col:
                f = st.file_uploader(label, type=["xlsx", "xls"], key=name)
                if f:
                    file_types[name] = f  # 업로드 객체 보관 — 임시파일은 로드 시점에만 생성

    st.divider()

    col_btn, _ = st.columns([1, 3], gap="medium")
    with col_btn:
        load_clicked = st.button("파일 로드 및 검증", width="stretch")

    if load_clicked:
        with st.spinner("파일 파싱 중..."):
            errors, ok_count, total = _load_uploads(loader, file_types)

        # 파일별 에러 표시
        for fname, err in errors.items():
            st.error(f"**{fname}** 파싱 실패: {err}")

        # 행 수준 파싱 경고 (일부 행 건너뜀)
        if loader.parse_warnings:
            with st.expander(f"⚠ 행 파싱 경고 {sum(len(v) for v in loader.parse_warnings.values())}건 — 클릭하여 확인"):
                for fname, msgs in loader.parse_warnings.items():
                    st.markdown(f"**{fname}**")
                    for msg in msgs:
                        st.caption(f"  • {msg}")

        # 누락 파일·균형 검증 경고
        for w in loader.validate():
            st.warning(w)

        if ok_count > 0:
            st.success(
                f"{ok_count}/{total}개 파일 로드 완료"
                + (f" — 분개장 {len(loader.journals):,}건" if loader.journals else "")
            )
        elif total:
            st.error("업로드된 파일을 모두 파싱하지 못했습니다.")

    # ── 파일 표준화 진단 리포트 — 무엇을 어떻게 인식했는지 투명하게 표시 ──
    if loader.file_meta:
        _FMT_LABEL = {
            "xls":  "XLS (Excel 97-2003)",
            "xlsx": "XLSX (Excel)",
            "html": "⚠ HTML형 파일 (확장자만 .xls) — 표 추출로 처리",
            "csv":  "CSV/텍스트",
            "unknown": "판별 불가 — Excel 엔진으로 시도",
        }
        with st.expander(f"📋 파일 표준화 진단 — {len(loader.file_meta)}개 파일 처리 내역"):
            import pandas as pd
            st.dataframe(pd.DataFrame([
                {
                    "파일": name,
                    "실제 포맷": _FMT_LABEL.get(m.get("format", ""), m.get("format", "")),
                    "인코딩/엔진": m.get("encoding", ""),
                    "헤더 행": m.get("header_row", 1),
                    "데이터 행": f"{m.get('rows', 0):,}",
                    "빈 행 제거": m.get("empty_rows_dropped", 0),
                    "비고": " · ".join(m.get("notes", [])),
                }
                for name, m in loader.file_meta.items()
            ]), width="stretch", hide_index=True)
            # 인식된 컬럼 확인 — 컬럼 매핑 오류를 사람이 즉시 발견할 수 있게
            _fm_names = list(loader.file_meta.keys())
            _fm_sel = st.selectbox(
                "파일 선택 — 인식된 컬럼 보기", range(len(_fm_names)),
                format_func=lambda i: _fm_names[i], key="file_meta_sel",
            )
            _cols = loader.file_meta[_fm_names[_fm_sel]].get("columns", [])
            st.caption(f"인식된 컬럼 {len(_cols)}개: " + " | ".join(_cols[:40]))
            st.caption(
                "※ 음수 표기 (1,234)·△·▲, 쉼표, '원' 단위는 자동 변환됩니다. "
                "계정과목 동의어(접대비↔기업업무추진비 등)는 검색 시 자동 확장됩니다."
            )

    if loader.journals:
        st.divider()
        st.markdown(section_title("로드 결과"), unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3, gap="medium")
        m1.metric("분개 라인", f"{len(loader.journals):,}건")
        m2.metric("고정자산", f"{len(loader.fixed_assets):,}개")
        m3.metric("업로드 파일", f"{sum(1 for v in file_types.values() if v)}개")

    # ── 전기(전년도) 자료 — 분석적 검토용 (선택) ──────────────────────────────
    st.divider()
    st.markdown(section_title(
        "전기(전년도) 자료 업로드 (선택)",
        "전년 대비 증감분석(분석적 검토)에 사용됩니다. 전기 재무상태표·손익계산서는 "
        "당기 재무제표에 전기 열로 이미 표시되므로 받지 않습니다. 대신 **전표 분개장·"
        "유형/무형자산 대장·제조원가명세서·계정별원장·계정별 잔액명세서**를 올리면, "
        "요약 수치가 아닌 거래·자산·원가 단위로 전년 대비 증감을 검토할 수 있어 "
        "분석적 검토에 더 목적적합합니다. 필요한 자료만 골라 올려도 됩니다.",
    ), unsafe_allow_html=True)

    prev_loader: SmartALoader = st.session_state.prev_loader
    # 당기와 동일한 파서를 재사용. 전기 B/S·P&L은 당기 재무제표 전기 열로 갈음하므로 제외
    _PREV_DEFS = [
        ("원가명세서",   "전기 제조원가명세서 — 원가 항목 증감분석"),
        ("고정자산대장", "전기 유형·무형자산 대장 — 자산 증감 비교"),
        ("분개장",       "전기 전표·분개장 — 거래 상세 비교"),
        ("계정별원장",   "전기 계정별원장 — 계정 흐름 비교"),
        ("계정별명세서", "전기 계정별 잔액명세서 — 보증금·차입금 등 잔액 대사"),
    ]
    prev_files: dict[str, object | None] = {name: None for name, _ in _PREV_DEFS}
    for i in range(0, len(_PREV_DEFS), 2):
        pcols = st.columns(2, gap="medium")
        for j, col in enumerate(pcols):
            if i + j >= len(_PREV_DEFS):
                break
            name, label = _PREV_DEFS[i + j]
            with col:
                prev_files[name] = st.file_uploader(
                    label, type=["xlsx", "xls"], key=f"prev_{name}"
                )

    if st.button("전기 자료 로드"):
        if not any(prev_files.values()):
            st.warning("전기 파일을 선택하세요.")
        else:
            with st.spinner("전기 자료 파싱 중..."):
                errors2, ok2, total2 = _load_uploads(prev_loader, prev_files)
            for fname, err in errors2.items():
                st.error(f"**전기 {fname}** 파싱 실패: {err}")
            if ok2 > 0:
                st.success(
                    f"전기 자료 {ok2}/{total2}개 로드 완료"
                    + (f" — 전기 분개장 {len(prev_loader.journals):,}건"
                       if prev_loader.journals else "")
                )

    # 로드된 전기 자료 요약 — 어떤 자료가 증감분석에 반영되는지 투명하게 표시
    _prev_status = []
    if prev_loader.cost_statement is not None:
        _prev_status.append(f"원가명세서 {len(prev_loader.cost_statement)}계정")
    if prev_loader.fixed_assets:
        _prev_status.append(f"고정자산 {len(prev_loader.fixed_assets)}개")
    if prev_loader.journals:
        _prev_status.append(f"분개 {len(prev_loader.journals):,}건")
    if prev_loader.ledger is not None:
        _prev_status.append(f"계정별원장 {len(prev_loader.ledger):,}행")
    if prev_loader.account_statement is not None:
        _prev_status.append(f"잔액명세서 {len(prev_loader.account_statement)}계정")
    if _prev_status:
        st.caption("✓ 전기 자료 로드됨: " + " · ".join(_prev_status) +
                   " — 5단계 증감분석·기초잔액 대사에 자동 반영")

