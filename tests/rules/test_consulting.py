"""세무 컨설팅 토픽 엔진 — 결정론적 트리거 테스트."""
from datetime import date

from src.rules.consulting import build_consulting_topics, ConsultingTopic
from src.project.taxproj import CompanyInfo, ManualInput
from src.utils.models import TaxAdjustmentResult


def _result(**kw):
    r = TaxAdjustmentResult(
        fiscal_year_start=date(2025, 1, 1),
        fiscal_year_end=date(2025, 12, 31),
        is_sme=True,
    )
    for k, v in kw.items():
        setattr(r, k, v)
    return r


def _topics(company=None, mi=None, result=None):
    return build_consulting_topics(
        company=company or CompanyInfo(),
        manual_input=mi or ManualInput(),
        result=result or _result(),
        fiscal_year_end=date(2025, 12, 31),
    )


def _titles(topics):
    return [t.title for t in topics]


def test_gajigeup_topic_triggers():
    """인정이자 발생 → 가지급금 정리 토픽(리스크·높음)."""
    topics = _topics(result=_result(deemed_interest=5_000_000))
    g = next(t for t in topics if t.title == "특수관계인 가지급금 정리")
    assert g.category == "리스크" and g.severity == "높음"
    assert "검토필요" in g.status  # ADR-002 — 항상 미확정
    assert "5,000,000" in g.finding


def test_sme_topic_only_for_sme():
    """중소기업이면 감면 검토 토픽, 아니면 없음."""
    assert "중소기업 세액감면·공제 적용 검토" in _titles(
        _topics(company=CompanyInfo(is_sme=True)))
    assert "중소기업 세액감면·공제 적용 검토" not in _titles(
        _topics(company=CompanyInfo(is_sme=False)))


def test_loss_expiry_imminent():
    """공제기한 1년 내 소멸 임박 이월결손금 → 토픽."""
    mi = ManualInput()
    mi.carryforward_losses = [{"year": 2011, "amount": 30_000_000}]  # 2011발생→10년→2021만료, 2025면 이미 만료
    mi.carryforward_losses = [{"year": 2015, "amount": 30_000_000}]  # 2015발생→10년→만료 2025, years_left=0 (만료) → 제외
    # 2016발생 → 10년 → years_left = 10-(2025-2016)=1 → 임박
    mi.carryforward_losses = [{"year": 2016, "amount": 30_000_000}]
    topics = _topics(mi=mi)
    assert "이월결손금 소멸 임박" in _titles(topics)


def test_loss_not_imminent_excluded():
    """공제기한 여유 있으면 토픽 없음."""
    mi = ManualInput()
    mi.carryforward_losses = [{"year": 2024, "amount": 30_000_000}]  # 2024→15년→여유
    assert "이월결손금 소멸 임박" not in _titles(_topics(mi=mi))


def test_entertainment_policy_topic():
    topics = _topics(result=_result(entertainment_excess=2_000_000))
    e = next(t for t in topics if t.title == "기업업무추진비 한도초과")
    assert e.category == "정책"


def test_risk_topics_sorted_first():
    """리스크 토픽이 특례·정책보다 앞에 정렬."""
    topics = _topics(
        company=CompanyInfo(is_sme=True),
        result=_result(deemed_interest=1_000_000, entertainment_excess=1_000_000),
    )
    cats = [t.category for t in topics]
    assert cats == sorted(cats, key=lambda c: {"리스크": 0, "특례·감면": 1, "정책": 2}[c])
    assert cats[0] == "리스크"


def test_empty_when_nothing_triggers():
    """트리거 없으면 빈 리스트 (일반론 남발 안 함)."""
    assert _topics(company=CompanyInfo(is_sme=False), result=_result()) == []
