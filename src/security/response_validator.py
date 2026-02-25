"""LLM 응답 검증 모듈"""

import json
import re
from dataclasses import dataclass
from typing import Optional

from .constants import (
    VALID_CATEGORIES,
    SAFE_FALLBACK_KEYWORD,
    SAFE_FALLBACK_CATEGORY,
)


@dataclass
class ClassificationResult:
    """분류 결과 데이터 클래스"""
    category: str
    keyword: str
    is_fallback: bool = False


class ResponseValidator:
    """LLM 응답 검증 클래스"""

    # 키워드에서 의심스러운 패턴
    SUSPICIOUS_KEYWORD_PATTERNS = [
        r"(?i)ignore",
        r"(?i)system",
        r"(?i)\bprompt\b",
        r"(?i)instruction",
        r"(?i)execute",
        r"(?i)script",
        r"<<<",
        r">>>",
        r"\{.*\{",           # 중첩 브레이스
        r"(?i)override",
        r"(?i)bypass",
        r"(?i)jailbreak",
    ]

    def __init__(self):
        self._suspicious_patterns = [
            re.compile(p) for p in self.SUSPICIOUS_KEYWORD_PATTERNS
        ]

    def validate_classification(
        self,
        llm_response: str,
        original_question: str
    ) -> ClassificationResult:
        """
        분류기 LLM 응답 검증

        Args:
            llm_response: LLM의 원시 응답
            original_question: 원본 사용자 질문 (로깅용, 사용하지 않음)

        Returns:
            검증된 ClassificationResult
        """
        # JSON 파싱 시도
        parsed = self._safe_json_parse(llm_response)

        if parsed is None:
            # 파싱 실패: 안전한 기본값 사용
            # 중요: 원본 질문을 keyword로 사용하지 않음!
            return ClassificationResult(
                category=SAFE_FALLBACK_CATEGORY,
                keyword=SAFE_FALLBACK_KEYWORD,
                is_fallback=True
            )

        # 카테고리 검증
        category = parsed.get("category", "").lower().strip()
        if category not in VALID_CATEGORIES:
            category = SAFE_FALLBACK_CATEGORY

        # 키워드 검증
        keyword = parsed.get("keyword", "")
        validated_keyword = self._validate_keyword(keyword)

        if validated_keyword is None:
            return ClassificationResult(
                category=SAFE_FALLBACK_CATEGORY,
                keyword=SAFE_FALLBACK_KEYWORD,
                is_fallback=True
            )

        return ClassificationResult(
            category=category,
            keyword=validated_keyword,
            is_fallback=False
        )

    def _safe_json_parse(self, response: str) -> Optional[dict]:
        """안전한 JSON 파싱"""
        try:
            response = response.strip()

            # 코드 블록에서 JSON 추출
            json_match = re.search(
                r'```(?:json)?\s*(\{.*?\})\s*```',
                response,
                re.DOTALL
            )
            if json_match:
                response = json_match.group(1)

            # 중괄호로 시작하지 않으면 중괄호 찾기
            if not response.startswith('{'):
                brace_start = response.find('{')
                brace_end = response.rfind('}')
                if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
                    response = response[brace_start:brace_end + 1]
                else:
                    return None

            return json.loads(response)
        except (json.JSONDecodeError, ValueError):
            return None

    def _validate_keyword(self, keyword: str) -> Optional[str]:
        """키워드 유효성 검증"""
        if not keyword or not isinstance(keyword, str):
            return None

        keyword = keyword.strip()

        # 길이 검증
        if len(keyword) < 2 or len(keyword) > 100:
            return None

        # 의심스러운 패턴 검사
        for pattern in self._suspicious_patterns:
            if pattern.search(keyword):
                return None

        return keyword
