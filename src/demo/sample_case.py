"""가상 회사 '한빛정밀(주)' 데모 케이스.

⚠️ 전부 가상 데이터다. 실제 회사·거래와 무관하며, 라이브 배포 데모에서
   면접관이 파일 업로드 없이 규칙 엔진 결과를 바로 볼 수 있도록 제공한다.

build_demo_loader(): SmartALoader를 메모리로 채운다 (분개장·손익계산서·재무상태표·고정자산).
build_demo_project(): CompanyInfo·ManualInput이 채워진 TaxProject.

계정코드 규약(집계 엔진 인식): 8132 기업업무추진비 · 8391 벌과금 ·
711x 배당금수익 · 998x 법인세비용 · 4xxx 매출.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from src.parsers.smart_a import SmartALoader
from src.project.taxproj import CompanyInfo, ManualInput, TaxProject
from src.utils.models import FixedAsset, JournalLine

_FY_START = date(2025, 1, 1)
_FY_END = date(2025, 12, 31)


def _jl(
    jid: str,
    line_no: int,
    d: date,
    acode: str,
    aname: str,
    desc: str,
    debit: int = 0,
    credit: int = 0,
    counterparty: str = "",
    card_no: str = "",
    evidence: str = "",
    row: int = 1,
) -> JournalLine:
    """데모 분개 라인 — 필수 필드를 안전한 기본값으로 채운다."""
    return JournalLine(
        journal_id=jid,
        line_no=line_no,
        date=d,
        account_code=acode,
        account_name=aname,
        description=desc,
        counterparty_code="",
        counterparty_name=counterparty,
        debit=debit,
        credit=credit,
        evidence_type=evidence,
        evidence_no="",
        card_no=card_no,
        vehicle_no="",
        project="",
        source_file="데모_분개장.xlsx",
        source_sheet="분개장",
        source_row=row,
    )


def _demo_journals() -> list[JournalLine]:
    j: list[JournalLine] = []
    n = 0

    # ── 매출 (수입금액) ─────────────────────────────────────
    n += 1
    j.append(_jl("M001", 0, date(2025, 6, 30), "4011", "제품매출",
                 "상반기 제품매출", credit=1_600_000_000, counterparty="대성전자", row=n))
    n += 1
    j.append(_jl("M002", 0, date(2025, 12, 31), "4011", "제품매출",
                 "하반기 제품매출", credit=1_400_000_000, counterparty="대성전자", row=n))

    # ── 기업업무추진비 (접대비) — 한도초과 + 증빙불비 ───────
    # 카드/적격증빙 있는 라인
    ent_dates = [date(2025, m, 15) for m in range(1, 12)]
    for i, d in enumerate(ent_dates):
        n += 1
        j.append(_jl(f"E{i:03d}", 0, d, "8132", "기업업무추진비",
                     f"거래처 접대 {d.month}월", debit=4_500_000,
                     counterparty="협력업체", card_no="1234-****-****-5678",
                     evidence="신용카드", row=n))
    # 증빙불비(3만원 초과, 카드·증빙 없음) 라인
    for i, d in enumerate([date(2025, 3, 20), date(2025, 7, 8), date(2025, 10, 5)]):
        n += 1
        j.append(_jl(f"EN{i:03d}", 0, d, "8132", "기업업무추진비",
                     "거래처 경조사비(현금)", debit=1_500_000,
                     counterparty="거래처", card_no="", evidence="", row=n))

    # ── 벌과금·과태료 (손금불산입) ──────────────────────────
    n += 1
    j.append(_jl("P001", 0, date(2025, 4, 10), "8391", "세금과공과금",
                 "교통 과태료", debit=1_200_000, counterparty="관할구청", row=n))
    n += 1
    j.append(_jl("P002", 0, date(2025, 9, 2), "8391", "세금과공과금",
                 "지급명세서 미제출 가산세", debit=1_800_000, counterparty="세무서", row=n))

    # ── 법인세비용 (손금불산입) ─────────────────────────────
    n += 1
    j.append(_jl("T001", 0, date(2025, 12, 31), "9981", "법인세비용",
                 "법인세비용 계상", debit=42_000_000, counterparty="", row=n))

    # ── 수입배당금 (익금불산입 검토) ────────────────────────
    n += 1
    j.append(_jl("D001", 0, date(2025, 5, 20), "7111", "배당금수익",
                 "자회사 배당 수령", credit=30_000_000, counterparty="한빛머티리얼즈", row=n))

    return j


def build_demo_loader() -> SmartALoader:
    """분개장·손익계산서·재무상태표·고정자산이 채워진 SmartALoader."""
    loader = SmartALoader()
    loader.journals = _demo_journals()

    loader.income_statement = pd.DataFrame([
        {"계정코드": "4011", "계정명": "제품매출", "당기금액": 3_000_000_000, "전기금액": 2_600_000_000},
        {"계정코드": "5010", "계정명": "매출원가", "당기금액": 1_950_000_000, "전기금액": 1_720_000_000},
        {"계정코드": "8132", "계정명": "기업업무추진비", "당기금액": 54_000_000, "전기금액": 38_000_000},
        {"계정코드": "8391", "계정명": "세금과공과금", "당기금액": 9_000_000, "전기금액": 6_500_000},
        {"계정코드": "8200", "계정명": "감가상각비", "당기금액": 60_000_000, "전기금액": 55_000_000},
        {"계정코드": "7111", "계정명": "배당금수익", "당기금액": 30_000_000, "전기금액": 12_000_000},
        {"계정코드": "9981", "계정명": "법인세비용", "당기금액": 42_000_000, "전기금액": 33_000_000},
        {"계정코드": "9990", "계정명": "당기순이익", "당기금액": 250_000_000, "전기금액": 205_000_000},
    ])

    loader.balance_sheet = pd.DataFrame([
        {"계정코드": "0101", "계정명": "현금및현금성자산", "기초잔액": 180_000_000, "기말잔액": 210_000_000},
        {"계정코드": "0201", "계정명": "기계장치", "기초잔액": 320_000_000, "기말잔액": 300_000_000},
        {"계정코드": "0260", "계정명": "차량운반구", "기초잔액": 45_000_000, "기말잔액": 38_000_000},
        {"계정코드": "0301", "계정명": "단기차입금", "기초잔액": 150_000_000, "기말잔액": 120_000_000},
    ])

    # 고정자산 — 정률법 기계장치 회사계상액이 세무한도를 초과 → 감가상각 시부인
    loader.fixed_assets = [
        FixedAsset(
            asset_code="M-01", asset_name="CNC 가공기", account_code="0201",
            acquired_date=date(2024, 1, 5), category="기계장치",
            book_value_start=100_000_000, accumulated_depr_start=0,
            denied_depr_start=0, deemed_depr_start=0,
            new_acquisition=0, disposal=0,
            useful_life=5, depr_rate=0.451, months=12, method="정률법",
            tax_depr_limit=0, company_depr=60_000_000, disposal_date=None,
        ),
        FixedAsset(
            asset_code="M-02", asset_name="자동검사설비", account_code="0201",
            acquired_date=date(2023, 7, 1), category="기계장치",
            book_value_start=80_000_000, accumulated_depr_start=20_000_000,
            denied_depr_start=0, deemed_depr_start=0,
            new_acquisition=0, disposal=0,
            useful_life=5, depr_rate=0.451, months=12, method="정률법",
            tax_depr_limit=0, company_depr=30_000_000, disposal_date=None,
        ),
    ]
    return loader


def build_demo_project() -> TaxProject:
    """회사정보·수기입력이 채워진 데모 TaxProject."""
    company = CompanyInfo(
        name="한빛정밀(주)",
        business_no="123-45-67890",
        representative="김한빛",
        address="경기도 화성시 동탄산단로 (가상)",
        is_sme=True,
        sme_verified=True,
        sme_verification_notes="데모 — 매출 30억·자산총액 요건 충족 가정",
        industry_code="C29294",
        fiscal_year_start=_FY_START.isoformat(),
        fiscal_year_end=_FY_END.isoformat(),
        is_specified_corp=False,
        is_rental_main=False,
    )
    mi = ManualInput()
    proj = TaxProject(company=company, manual_input=mi)
    return proj
