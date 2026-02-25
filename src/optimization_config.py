"""
RAG 최적화 설정
각 개선사항을 on/off할 수 있는 설정 클래스
"""
from dataclasses import dataclass


@dataclass
class OptimizationConfig:
    """RAG 최적화 설정"""
    
    # 설정 이름
    name: str
    
    # 개선사항 1: GPT-4 사용
    use_gpt4: bool = False
    
    # 개선사항 2: 검색 결과 중복 제거
    deduplicate_results: bool = False
    
    # 개선사항 3: 두 단계 검색
    two_stage_retrieval: bool = False
    
    # 두 단계 검색 설정
    stage1_limit: int = 20  # 1단계: 광범위 검색
    stage2_limit: int = 5   # 2단계: 정밀 선택
    
    def __str__(self):
        """설정 정보 문자열 표현"""
        features = []
        if self.use_gpt4:
            features.append("GPT-4")
        if self.deduplicate_results:
            features.append("중복제거")
        if self.two_stage_retrieval:
            features.append("2단계검색")
        
        if not features:
            return f"{self.name} (베이스라인)"
        return f"{self.name} ({' + '.join(features)})"


# ===== 8가지 설정 버전 정의 =====

# Baseline: 원본 (개선사항 없음)
BASELINE = OptimizationConfig(
    name="baseline",
    use_gpt4=False,
    deduplicate_results=False,
    two_stage_retrieval=False,
)

# V1: GPT-4만
V1_GPT4 = OptimizationConfig(
    name="v1_gpt4",
    use_gpt4=True,
    deduplicate_results=False,
    two_stage_retrieval=False,
)

# V2: 중복 제거만
V2_DEDUP = OptimizationConfig(
    name="v2_dedup",
    use_gpt4=False,
    deduplicate_results=True,
    two_stage_retrieval=False,
)

# V3: 두 단계 검색만
V3_TWOSTAGE = OptimizationConfig(
    name="v3_twostage",
    use_gpt4=False,
    deduplicate_results=False,
    two_stage_retrieval=True,
)

# V4: GPT-4 + 중복 제거
V4_GPT4_DEDUP = OptimizationConfig(
    name="v4_gpt4_dedup",
    use_gpt4=True,
    deduplicate_results=True,
    two_stage_retrieval=False,
)

# V5: GPT-4 + 두 단계 검색
V5_GPT4_TWOSTAGE = OptimizationConfig(
    name="v5_gpt4_twostage",
    use_gpt4=True,
    deduplicate_results=False,
    two_stage_retrieval=True,
)

# V6: 중복 제거 + 두 단계 검색
V6_DEDUP_TWOSTAGE = OptimizationConfig(
    name="v6_dedup_twostage",
    use_gpt4=False,
    deduplicate_results=True,
    two_stage_retrieval=True,
)

# V7: 모두 적용
V7_ALL = OptimizationConfig(
    name="v7_all",
    use_gpt4=True,
    deduplicate_results=True,
    two_stage_retrieval=True,
)

# 모든 설정 리스트 (순서대로 평가)
ALL_CONFIGS = [
    BASELINE,
    V1_GPT4,
    V2_DEDUP,
    V3_TWOSTAGE,
    V4_GPT4_DEDUP,
    V5_GPT4_TWOSTAGE,
    V6_DEDUP_TWOSTAGE,
    V7_ALL,
]

# 이름으로 설정 찾기
CONFIG_MAP = {config.name: config for config in ALL_CONFIGS}


def get_config(name: str) -> OptimizationConfig:
    """이름으로 설정 가져오기"""
    if name not in CONFIG_MAP:
        raise ValueError(f"Unknown config: {name}. Available: {list(CONFIG_MAP.keys())}")
    return CONFIG_MAP[name]
