"""참고자료 RAG — 국세청 참고파일(추출텍스트) 키워드 검색.

계산엔진이 아니라 컨설팅·검토메모·PDF 보조에만 사용한다 (KICPA·security 리뷰 합의).
벡터DB·임베딩 없이 키워드 검색으로 시작 — 외부 네트워크/LLM API 불필요(로컬 텍스트만).
"""
from src.rag.reference_retriever import search_references, enrich_topics_with_references

__all__ = ["search_references", "enrich_topics_with_references"]
