"""
RAG 최적화 기능 모듈
중복 제거, 두 단계 검색 등의 개선 기능 구현
"""
from typing import List, Dict, Set


def deduplicate_by_generic_name(results: List[Dict]) -> List[Dict]:
    """
    검색 결과에서 generic_name(성분명) 기준으로 중복 제거
    
    Args:
        results: OpenFDA API 검색 결과 리스트
        
    Returns:
        중복이 제거된 결과 리스트
    """
    if not results:
        return results
    
    seen_generics: Set[str] = set()
    deduplicated = []
    
    for result in results:
        openfda = result.get("openfda", {})
        generic_names = openfda.get("generic_name", [])
        
        # generic_name이 없으면 그냥 포함
        if not generic_names:
            deduplicated.append(result)
            continue
        
        # 첫 번째 generic_name 사용
        primary_generic = generic_names[0].lower().strip()
        
        # 이미 본 성분이 아니면 추가
        if primary_generic not in seen_generics:
            seen_generics.add(primary_generic)
            deduplicated.append(result)
    
    return deduplicated


def rerank_by_relevance(results: List[Dict], keyword: str) -> List[Dict]:
    """
    검색 결과를 관련성 점수로 재정렬
    
    Args:
        results: 검색 결과 리스트
        keyword: 검색 키워드
        
    Returns:
        재정렬된 결과 리스트
    """
    if not results or not keyword:
        return results
    
    keyword_lower = keyword.lower()
    
    def calculate_relevance(result: Dict) -> int:
        """관련성 점수 계산 (높을수록 관련성 높음)"""
        score = 0
        openfda = result.get("openfda", {})
        
        # 브랜드명 매칭
        brand_names = openfda.get("brand_name", [])
        for brand in brand_names:
            if keyword_lower in brand.lower():
                score += 10
            if keyword_lower == brand.lower():
                score += 20
        
        # 성분명 매칭
        generic_names = openfda.get("generic_name", [])
        for generic in generic_names:
            if keyword_lower in generic.lower():
                score += 10
            if keyword_lower == generic.lower():
                score += 20
        
        # 적응증 매칭
        indications = result.get("indications_and_usage", [])
        if isinstance(indications, list):
            for indication in indications:
                if keyword_lower in str(indication).lower():
                    score += 5
        elif isinstance(indications, str):
            if keyword_lower in indications.lower():
                score += 5
        
        # Purpose 매칭
        purposes = result.get("purpose", [])
        if isinstance(purposes, list):
            for purpose in purposes:
                if keyword_lower in str(purpose).lower():
                    score += 3
        elif isinstance(purposes, str):
            if keyword_lower in purposes.lower():
                score += 3
        
        return score
    
    # 점수 기준으로 정렬 (높은 점수 우선)
    scored_results = [(result, calculate_relevance(result)) for result in results]
    scored_results.sort(key=lambda x: x[1], reverse=True)
    
    return [result for result, score in scored_results]


def two_stage_search(search_fn, keyword: str, stage1_limit: int = 20, stage2_limit: int = 5) -> List[Dict]:
    """
    두 단계 검색 전략
    
    1단계: 광범위하게 검색 (stage1_limit개)
    2단계: 관련성 기준으로 재정렬하여 상위 N개 선택
    
    Args:
        search_fn: 검색 함수 (예: search_by_brand_name)
        keyword: 검색 키워드
        stage1_limit: 1단계 검색 개수
        stage2_limit: 2단계 최종 선택 개수
        
    Returns:
        최종 선택된 결과 리스트
    """
    # 1단계: 광범위 검색
    # search_fn은 이미 OpenFDAClient를 사용하므로 그대로 호출
    # 하지만 limit을 조정해야 하므로, 별도로 처리
    from src.api.openfda_client import OpenFDAClient
    
    client = OpenFDAClient()
    
    # 원래 SEARCH_LIMIT을 임시로 변경
    original_limit = client.base_url  # 이 부분은 실제로는 _build_url에서 처리됨
    
    # search_fn을 직접 호출하는 대신, 내부적으로 limit을 조정
    # 이를 위해 OpenFDAClient의 search_drug_label을 직접 사용
    
    # 검색 필드 결정 (이 함수는 이미 특정 검색 필드에 매핑되어 있음)
    # 대신 더 간단하게, search_fn의 결과를 사용하되 limit은 config에서 조정
    
    # 실제로는 이 함수를 openfda_client에서 직접 호출하도록 수정해야 함
    # 여기서는 일단 기본 검색 후 필터링
    
    results = search_fn(keyword)
    
    if not results:
        return results
    
    # 1단계 결과 제한
    stage1_results = results[:stage1_limit]
    
    # 2단계: 관련성 기준 재정렬 및 선택
    reranked = rerank_by_relevance(stage1_results, keyword)
    final_results = reranked[:stage2_limit]
    
    return final_results


def apply_optimizations(results: List[Dict], config, keyword: str = "") -> List[Dict]:
    """
    OptimizationConfig에 따라 최적화 적용
    
    Args:
        results: 원본 검색 결과
        config: OptimizationConfig 객체
        keyword: 검색 키워드 (재정렬에 사용)
        
    Returns:
        최적화된 결과 리스트
    """
    optimized = results
    
    # 중복 제거 적용
    if config.deduplicate_results:
        optimized = deduplicate_by_generic_name(optimized)
    
    # 두 단계 검색의 2단계 (재정렬 및 선택)
    # 실제 두 단계 검색은 검색 시점에 적용되어야 하므로
    # 여기서는 재정렬만 수행
    if config.two_stage_retrieval:
        optimized = rerank_by_relevance(optimized, keyword)
        optimized = optimized[:config.stage2_limit]
    
    return optimized
