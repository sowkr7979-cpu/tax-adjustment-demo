"""법인세법 세무조정 전수 검토 체크리스트 (coverage matrix).

프로젝트 원칙: 모든 세무조정은 국가법령정보(law.go.kr) 기반.
이 모듈은 법인세법상 주요 세무조정 항목 전체를 카탈로그로 갖고,
분개장·재무제표를 스캔하여 각 항목의 검토 상태를 판정한다:

  자동계산  — 규칙 엔진이 산식으로 금액까지 계산
  검토필요  — 관련 계정·거래가 발견됨, 추가 자료·전문가 판단 필요
  해당없음  — 관련 계정·거래가 분개장에 없음

감사프로그램(audit program)과 같은 원리 — 항목을 빠뜨리지 않는
완전성(completeness) 확보가 목적이다.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from src.utils.models import JournalLine


@dataclass
class CoverageResult:
    item: str            # 조정 항목명
    legal_basis: str     # 법령 근거 (조문 표시)
    status: str          # "자동계산" | "검토필요" | "해당없음"
    detail: str          # 발견 계정·금액 요약 / 필요 추가자료
    amount_hint: int = 0 # 관련 금액 (참고용 — 조정액이 아님)
    lines: list[JournalLine] = field(default_factory=list)  # 매칭된 분개 내역 (드릴다운용)


@dataclass
class _CheckSpec:
    item: str
    legal_basis: str
    account_keywords: tuple[str, ...] = ()      # 계정명 키워드
    code_prefixes: tuple[str, ...] = ()         # 계정코드 접두어
    desc_keywords: tuple[str, ...] = ()         # 적요 키워드 (계정 무관 탐지)
    auto_calc: bool = False                     # 규칙 엔진 자동계산 여부
    need: str = ""                              # 검토필요 시 필요한 자료·판단


# 법인세법 주요 세무조정 카탈로그 — 법령정보 기반 (조문은 legal_basis.py와 동일 체계)
_CHECKLIST: list[_CheckSpec] = [
    _CheckSpec("감가상각비 시부인", "법§23, 영§26~28",
               ("감가상각",), auto_calc=True),
    _CheckSpec("기업업무추진비 한도·증빙", "법§25",
               ("기업업무추진비", "접대비"), ("8132", "813"), auto_calc=True),
    _CheckSpec("퇴직급여충당금·퇴직연금", "법§33, 영§44의2",
               ("퇴직급여충당", "퇴직연금"), auto_calc=True,
               need="장부상 충당금 기초·기말잔액, 총급여액, 퇴직금추계액"),
    _CheckSpec("대손충당금·대손금", "법§34",
               ("대손충당", "대손상각"), auto_calc=True,
               need="설정대상 채권잔액, 대손실적률"),
    _CheckSpec("벌과금·과태료·가산세", "법§21",
               ("벌과금", "과태료", "범칙금"), ("8391",),
               desc_keywords=("가산세", "과태료", "벌금", "범칙금", "벌과금"),
               auto_calc=True),
    _CheckSpec("수입배당금 익금불산입", "법§18의2",
               ("배당금수익", "수입배당금"), ("711",), auto_calc=True,
               need="피출자법인별 출자비율"),
    _CheckSpec("가지급금 인정이자", "법§52, 영§89",
               ("가지급금", "주임종단기채권"), auto_calc=True,
               need="특수관계인 가지급금 적수, 약정이자"),
    # ── 이하 탐지 전용 (검토필요 판정) ──
    _CheckSpec("외화자산·부채 평가손익", "법§42③, 영§76",
               ("외화환산",),
               need="화폐성 외화자산·부채 잔액, 평가방법 신고 여부(마감환율/거래일환율)"),
    _CheckSpec("통화선도 등 파생상품 평가손익", "영§73, §76",
               ("통화선도", "파생상품", "스왑", "통화옵션"),
               need="계약 내역, 환위험회피 목적 여부, 평가방법 신고 여부"),
    _CheckSpec("외환차손익 (실현분)", "법§42",
               ("외환차익", "외환차손"),
               need="실현 환손익은 원칙적으로 익금·손금 — 평가분과의 구분 확인"),
    _CheckSpec("임원 상여금 한도", "법§26, 영§43",
               ("상여금", "상여"),
               need="임원 여부 구분, 정관·주총·이사회 결의 지급기준"),
    _CheckSpec("임원 퇴직급여 한도", "법§26, 영§44",
               ("퇴직급여", "퇴직금"),
               need="임원 여부 구분, 정관 퇴직급여 규정, 연봉·근속연수"),
    _CheckSpec("업무용승용차 관련비용", "법§27의2, 영§50의2",
               ("차량유지", "차량비", "렌트료", "리스료"),
               need="차량별 운행기록부, 업무전용보험 가입 여부, 감가상각비 연 800만원 한도"),
    _CheckSpec("지급이자 손금불산입", "법§28, 영§53~56",
               ("이자비용",),
               need="채권자불분명 사채이자, 건설자금이자, 업무무관자산 보유 여부"),
    _CheckSpec("기부금 한도", "법§24",
               ("기부금",),
               need="특례·일반·비지정 구분, 기준소득금액"),
    _CheckSpec("법인세비용 손금불산입", "법§21 1호",
               ("법인세비용", "법인세등"), ("998",),
               need="법인세·지방소득세 비용계상액 전액 손금불산입"),
    _CheckSpec("자산수증이익·채무면제이익", "법§18 6호",
               ("자산수증", "채무면제"), ("7191", "7192"),
               need="이월결손금 보전 충당 여부"),
    _CheckSpec("국고보조금·공사부담금", "법§36~37",
               ("국고보조금", "공사부담금"),
               need="일시상각충당금 설정 여부"),
    _CheckSpec("재고자산 평가", "법§42, 영§74",
               ("재고자산평가", "평가손실", "평가충당"),
               need="평가방법 신고 여부, 신고방법과 장부방법 일치 확인"),
    _CheckSpec("미수수익·선급비용 (손익귀속)", "법§40, 영§70",
               ("미수수익", "선급비용", "선수수익"),
               need="권리의무확정주의 — 기간귀속 적정성"),
    _CheckSpec("간주임대료", "조특법§138",
               ("임대보증금", "전세보증금"),
               need="부동산임대업 주업 여부, 차입금 과다 여부"),
    # ── law.go.kr 법인세법 제13~55조 전수 대조로 추가된 항목 ──
    _CheckSpec("유가증권 평가손익", "법§42, 영§75",
               ("단기매매증권평가", "당기손익인식금융자산평가", "금융자산평가"),
               auto_calc=True,
               need="일반법인은 원가법만 인정 — 평가손익 전액 부인 (금융회사 제외)"),
    _CheckSpec("징벌적 손해배상금", "법§21의2",
               ("손해배상",), desc_keywords=("손해배상", "배상금", "합의금"),
               need="실손해 초과분(징벌적 부분) 손금불산입 — 판결문·합의서 확인"),
    _CheckSpec("업무무관비용", "법§27, 영§49~50",
               ("업무무관",), desc_keywords=("업무무관",),
               need="업무무관자산 유지비·관리비, 타인 사용 자산 비용"),
    _CheckSpec("복리후생비 (열거 외 항목)", "법§26, 영§45",
               ("복리후생비", "복리시설비"),
               need="영§45 열거 항목(직장체육비·경조사비 등) 외 지출 여부 검토"),
    _CheckSpec("공동경비 분담 초과", "영§48",
               ("공동경비",), desc_keywords=("공동경비", "경비분담", "분담금"),
               need="출자·매출 비율 기준 분담기준 초과 부담액"),
    _CheckSpec("의제배당", "법§16",
               ("의제배당",), desc_keywords=("유상감자", "무상주", "잉여금자본전입"),
               need="감자·해산·합병·잉여금 자본전입으로 인한 의제배당 여부"),
    _CheckSpec("자본거래 수익 익금불산입", "법§17",
               ("주식발행초과금", "감자차익", "합병차익", "분할차익"),
               need="자본거래 수익은 익금불산입 — 회계처리 확인"),
    _CheckSpec("잉여금 처분 손비", "법§20",
               ("잉여금처분",), desc_keywords=("잉여금처분",),
               need="잉여금 처분을 손비로 계상한 금액 손금불산입"),
    _CheckSpec("자산 평가손실", "법§22",
               ("평가손실", "손상차손", "재고자산평가손실"),
               need="법§42에 따른 평가만 인정 — 임의 평가손실 손금불산입"),
    _CheckSpec("보험차익 일시상각", "법§38",
               ("보험차익",),
               need="보험차익으로 대체 자산 취득 시 일시상각충당금 손금산입 가능"),
    _CheckSpec("합병·분할 세무조정", "법§44~47",
               ("합병차익", "분할차익", "합병차손", "영업권"),
               need="적격 여부, 승계 자산 세무가액, 이월결손금 승계 제한"),
    _CheckSpec("토지 등 양도소득 법인세", "법§55의2",
               ("유형자산처분이익", "토지처분", "부동산처분"),
               need="비사업용 토지·주택 양도 시 추가 법인세 (10~40%)"),
]


def run_coverage_check(
    journals: list[JournalLine],
    auto_calculated: set[str] | None = None,
) -> list[CoverageResult]:
    """분개장을 스캔해 체크리스트 전 항목의 검토 상태를 판정한다.

    auto_calculated: 이번 실행에서 규칙 엔진이 실제로 계산한 항목명 집합
                     (None이면 _CheckSpec.auto_calc 기준)
    """
    results: list[CoverageResult] = []

    for spec in _CHECKLIST:
        hits: dict[str, int] = {}   # "코드 계정명" → 금액합
        hit_count = 0
        matched_lines: list[JournalLine] = []

        for ln in journals:
            name = ln.account_name.replace(" ", "")
            code = ln.account_code.strip()
            matched = (
                any(kw in name for kw in spec.account_keywords)
                or any(code.startswith(p) for p in spec.code_prefixes if p)
            )
            # 적요 키워드 — 계정과 무관하게 탐지 (예: 세금과공과 안의 가산세)
            if not matched and spec.desc_keywords:
                matched = any(kw in ln.description for kw in spec.desc_keywords)
            if matched:
                key = f"{code} {ln.account_name}"
                hits[key] = hits.get(key, 0) + max(ln.debit, ln.credit)
                hit_count += 1
                matched_lines.append(ln)

        total = sum(hits.values())
        if not hits:
            results.append(CoverageResult(
                item=spec.item, legal_basis=spec.legal_basis,
                status="해당없음", detail="관련 계정·적요 미발견",
            ))
            continue

        acct_summary = ", ".join(list(hits.keys())[:4])
        if len(hits) > 4:
            acct_summary += f" 외 {len(hits) - 4}개"

        is_auto = spec.item in auto_calculated if auto_calculated is not None else spec.auto_calc
        results.append(CoverageResult(
            item=spec.item, legal_basis=spec.legal_basis,
            status="자동계산" if is_auto else "검토필요",
            detail=(
                f"{acct_summary} — {hit_count}건"
                + (f" | 필요자료: {spec.need}" if spec.need and not is_auto else "")
            ),
            amount_hint=total,
            lines=matched_lines,
        ))

    return results
