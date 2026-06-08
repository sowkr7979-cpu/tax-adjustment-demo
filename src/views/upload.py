"""2단계 — 재무제표 업로드 (표준화 파이프라인 + 진단 리포트)."""
from __future__ import annotations
import os
import tempfile
from pathlib import Path

import streamlit as st

from src.parsers.smart_a import SmartALoader
from src.ui.styles import page_header, section_title


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
        load_clicked = st.button("파일 로드 및 검증", use_container_width=True)

    if load_clicked:
        # 임시파일은 파싱 동안만 존재 — 파싱 직후 삭제 (회계자료 원본이 임시폴더에 남지 않도록)
        paths: dict[str, str] = {}
        try:
            for k, f in file_types.items():
                if f is None:
                    continue
                ext = Path(f.name).suffix or ".xls"
                f.seek(0)
                with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                    tmp.write(f.read())
                    paths[k] = tmp.name
            with st.spinner("파일 파싱 중..."):
                errors = loader.load(paths)
        finally:
            for p in paths.values():
                try:
                    os.unlink(p)
                except OSError:
                    pass

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

        ok_count = len(paths) - len(errors)
        if ok_count > 0:
            st.success(
                f"{ok_count}/{len(paths)}개 파일 로드 완료"
                + (f" — 분개장 {len(loader.journals):,}건" if loader.journals else "")
            )
        elif paths:
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
            ]), use_container_width=True, hide_index=True)
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

    # ── 전기(전년도) 재무제표 — 분석적 검토용 (선택) ──────────────────────────
    st.divider()
    st.markdown(section_title(
        "전기(전년도) 재무제표 업로드 (선택)",
        "전년 대비 증감분석(분석적 검토)과 기초잔액 대사에 사용됩니다 — "
        "당기 손익계산서가 단일연도 양식이어도 전기 손익계산서를 올리면 증감분석이 가능하고, "
        "전기 재무상태표를 올리면 당기 기초잔액 ↔ 전기 기말잔액 대사로 적수 계산의 신뢰성을 검증합니다.",
    ), unsafe_allow_html=True)

    prev_loader: SmartALoader = st.session_state.prev_loader
    _PREV_DEFS = [
        ("재무상태표", "전기 재무상태표 (B/S)"),
        ("손익계산서", "전기 손익계산서 (P&L)"),
    ]
    prev_files: dict[str, object | None] = {}
    pcols = st.columns(2, gap="medium")
    for (name, label), col in zip(_PREV_DEFS, pcols):
        with col:
            f = st.file_uploader(label, type=["xlsx", "xls"], key=f"prev_{name}")
            prev_files[name] = f

    if st.button("전기 재무제표 로드"):
        paths2: dict[str, str] = {}
        try:
            for k, f in prev_files.items():
                if f is None:
                    continue
                ext = Path(f.name).suffix or ".xls"
                f.seek(0)
                with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                    tmp.write(f.read())
                    paths2[k] = tmp.name
            if not paths2:
                st.warning("전기 파일을 선택하세요.")
            else:
                with st.spinner("전기 재무제표 파싱 중..."):
                    errors2 = prev_loader.load(paths2)
                for fname, err in errors2.items():
                    st.error(f"**전기 {fname}** 파싱 실패: {err}")
                ok2 = len(paths2) - len(errors2)
                if ok2 > 0:
                    st.success(f"전기 재무제표 {ok2}/{len(paths2)}개 로드 완료")
        finally:
            for p in paths2.values():
                try:
                    os.unlink(p)
                except OSError:
                    pass

    _prev_status = []
    if prev_loader.balance_sheet is not None:
        _prev_status.append(f"전기 B/S {len(prev_loader.balance_sheet)}계정")
    if prev_loader.income_statement is not None:
        _prev_status.append(f"전기 P&L {len(prev_loader.income_statement)}계정")
    if _prev_status:
        st.caption("✓ 로드됨: " + " · ".join(_prev_status) +
                   " — 5단계 증감분석·기초잔액 대사에 자동 반영")

