"""사용자 입력 검증 모듈"""

import re
from dataclasses import dataclass
from typing import Optional

from .constants import (
    MAX_INPUT_LENGTH,
    MIN_INPUT_LENGTH,
    INJECTION_PATTERNS,
    FORBIDDEN_SEQUENCES,
)


@dataclass
class ValidationResult:
    """검증 결과 데이터 클래스"""
    is_valid: bool
    sanitized_input: Optional[str] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None


class InputValidator:
    """사용자 입력 검증 클래스"""

    def __init__(self, max_length: int = MAX_INPUT_LENGTH):
        self.max_length = max_length
        self._compiled_patterns = [
            re.compile(pattern) for pattern in INJECTION_PATTERNS
        ]

    def validate(self, user_input: str) -> ValidationResult:
        """
        사용자 입력 검증 및 정화

        검증 순서:
        1. 타입 검증
        2. 길이 검증
        3. 금지 시퀀스 검증
        4. 프롬프트 인젝션 패턴 검증
        5. 입력 정화
        """
        # 1. 타입 검증
        if not isinstance(user_input, str):
            return ValidationResult(
                is_valid=False,
                error_message="입력은 문자열이어야 합니다.",
                error_code="INVALID_TYPE"
            )

        # 2. 길이 검증
        stripped = user_input.strip()
        if len(stripped) < MIN_INPUT_LENGTH:
            return ValidationResult(
                is_valid=False,
                error_message="질문이 너무 짧습니다. 2자 이상 입력해주세요.",
                error_code="TOO_SHORT"
            )

        if len(stripped) > self.max_length:
            return ValidationResult(
                is_valid=False,
                error_message=f"질문이 너무 깁니다. {self.max_length}자 이하로 입력해주세요.",
                error_code="TOO_LONG"
            )

        # 3. 금지 시퀀스 검증
        for seq in FORBIDDEN_SEQUENCES:
            if seq in user_input:
                return ValidationResult(
                    is_valid=False,
                    error_message="허용되지 않는 문자가 포함되어 있습니다.",
                    error_code="FORBIDDEN_SEQUENCE"
                )

        # 4. 프롬프트 인젝션 패턴 검증
        for pattern in self._compiled_patterns:
            if pattern.search(user_input):
                return ValidationResult(
                    is_valid=False,
                    error_message="의약품 관련 질문만 입력해주세요.",
                    error_code="INJECTION_DETECTED"
                )

        # 5. 입력 정화
        sanitized = self._sanitize(stripped)

        return ValidationResult(
            is_valid=True,
            sanitized_input=sanitized
        )

    def _sanitize(self, user_input: str) -> str:
        """입력 문자열 정화"""
        result = user_input

        # 연속 공백을 단일 공백으로
        result = re.sub(r'\s+', ' ', result)

        # 제어 문자 제거 (개행과 탭은 공백으로 변환)
        result = ''.join(
            char if ord(char) >= 32 else ' '
            for char in result
        )

        # 다시 연속 공백 정리
        result = re.sub(r'\s+', ' ', result).strip()

        return result


# 싱글톤 인스턴스
_validator = InputValidator()


def validate_user_input(user_input: str) -> ValidationResult:
    """사용자 입력 검증 헬퍼 함수"""
    return _validator.validate(user_input)
