"""
검색 결과 리스트에 대한 후처리 (중복 제거·재정렬).
구조는 향후 관광 RAG 검색 결과(dict 리스트)를 가정합니다.
"""
from typing import List, Dict, Set


def deduplicate_by_generic_name(results: List[Dict]) -> List[Dict]:
    """
    `id` 또는 `chunk_id` 키가 있으면 그 기준으로 중복 제거.
    없으면 리스트 순서를 유지한 채 전부 유지.
    """
    if not results:
        return results

    seen: Set[str] = set()
    out: List[Dict] = []
    for row in results:
        key = None
        for k in ("id", "chunk_id", "document_id"):
            if k in row and row[k] is not None:
                key = str(row[k])
                break
        if key is None:
            out.append(row)
            continue
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out


def rerank_by_relevance(results: List[Dict], keyword: str) -> List[Dict]:
    """keyword가 JSON 문자列に含まれるほどスコアを高くして並べ替え。"""
    if not results or not keyword:
        return results

    kw = keyword.lower()

    def score(row: Dict) -> int:
        blob = " ".join(str(v) for v in row.values()).lower()
        return blob.count(kw)

    return sorted(results, key=score, reverse=True)


def two_stage_search(search_fn, keyword: str, stage1_limit: int = 20, stage2_limit: int = 5) -> List[Dict]:
    """1段階で search_fn を呼び、件数制限と再ランク。"""
    results = search_fn(keyword)
    if not results:
        return results
    stage1 = results[:stage1_limit]
    reranked = rerank_by_relevance(stage1, keyword)
    return reranked[:stage2_limit]


def apply_optimizations(results: List[Dict], config, keyword: str = "") -> List[Dict]:
    optimized = results
    if getattr(config, "deduplicate_results", False):
        optimized = deduplicate_by_generic_name(optimized)
    if getattr(config, "two_stage_retrieval", False):
        optimized = rerank_by_relevance(optimized, keyword)
        optimized = optimized[: getattr(config, "stage2_limit", 5)]
    return optimized
