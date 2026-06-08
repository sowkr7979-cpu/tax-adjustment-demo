# -*- coding: utf-8 -*-
"""고정자산대장 파싱 — 더존 감가상각비명세서 양식 (소계 행 계정명 역부여)."""
import pandas as pd

from src.parsers.smart_a import parse_fixed_assets


def _write_dz_statement(path):
    """더존 '유형자산감가상각비명세서' 양식 재현 — 제목 행 + [소계] 그룹."""
    rows = [
        ["유형자산감가상각비명세서", "", "", "", "", "", "", "", "", "", "", ""],
        ["회사명 :(주)테스트", "", "", "", "", "", "", "", "", "", "", ""],
        ["자산명", "취득일", "기초가액", "당기증감", "기말잔액", "전기말상각누계액",
         "상각대상금액", "년수", "상각률", "월수", "당기상각비", "당기말상각누계액"],
        ["본사사옥", "2010-01-01", "1,000,000,000", "", "1,000,000,000", "400,000,000",
         "1,000,000,000", "40", "0.025", "12", "25,000,000", "425,000,000"],
        ["[소계] 건물", "", "1,000,000,000", "", "", "", "", "", "", "", "25,000,000", ""],
        ["그랜저 12가3456", "2023-05-01", "50,000,000", "", "50,000,000", "20,000,000",
         "30,000,000", "5", "0.451", "12", "13,530,000", "33,530,000"],
        ["포터 87나6543", "2022-03-01", "20,000,000", "", "20,000,000", "10,000,000",
         "10,000,000", "5", "0.451", "12", "4,510,000", "14,510,000"],
        ["[소계] 차량운반구", "", "70,000,000", "", "", "", "", "", "", "", "18,040,000", ""],
        ["계측기A", "2024-01-01", "9,000,000", "", "9,000,000", "3,000,000",
         "6,000,000", "5", "0.451", "12", "2,706,000", "5,706,000"],
        ["[소계] 비품", "", "9,000,000", "", "", "", "", "", "", "", "2,706,000", ""],
    ]
    pd.DataFrame(rows).to_excel(path, index=False, header=False)


def test_subtotal_category_backfill(tmp_path):
    p = tmp_path / "유무형자산명세서.xlsx"
    _write_dz_statement(p)
    assets = parse_fixed_assets(p)

    # 소계 행은 자산이 아니다 — 개별 자산 4개만
    names = [a.asset_name for a in assets]
    assert len(assets) == 4
    assert not any("소계" in n for n in names)

    # 소계 행의 계정명이 위쪽 자산들에 역부여됨
    by_name = {a.asset_name: a for a in assets}
    assert by_name["본사사옥"].category == "건물"
    assert by_name["그랜저 12가3456"].category == "차량운반구"
    assert by_name["포터 87나6543"].category == "차량운반구"
    assert by_name["계측기A"].category == "비품"   # '계측기'가 소계로 오인되지 않음


def test_dz_columns_mapped(tmp_path):
    p = tmp_path / "유무형자산명세서.xlsx"
    _write_dz_statement(p)
    assets = parse_fixed_assets(p)
    car = next(a for a in assets if "그랜저" in a.asset_name)
    # 기초가액(취득가) − 상각누계 = 장부가
    assert car.book_value_start == 30_000_000
    assert car.accumulated_depr_start == 20_000_000
    assert car.company_depr == 13_530_000
    # 상각률 0.451 ≠ 1/5 → 정률법 추론
    assert car.method == "정률법"
    bld = next(a for a in assets if a.asset_name == "본사사옥")
    # 0.025 == 1/40 → 정액법 추론
    assert bld.method == "정액법"
