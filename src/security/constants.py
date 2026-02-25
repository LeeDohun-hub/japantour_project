"""보안 관련 상수 정의"""

# 입력 제한
MAX_INPUT_LENGTH = 500
MIN_INPUT_LENGTH = 2

# 프롬프트 인젝션 탐지 패턴 (정규표현식)
INJECTION_PATTERNS = [
    # 시스템 프롬프트 오버라이드 시도 (영문)
    r"(?i)ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?|rules?)",
    r"(?i)disregard\s+(all\s+)?(previous|above|prior)",
    r"(?i)forget\s+(everything|all|your)\s*(you|instructions?)?",
    r"(?i)you\s+are\s+now\s+(a|an|the)",
    r"(?i)act\s+as\s+(a|an|if)",
    r"(?i)pretend\s+(to\s+be|you\s+are)",
    r"(?i)roleplay\s+as",
    r"(?i)new\s+instructions?:",
    r"(?i)system\s*:\s*",
    r"(?i)assistant\s*:\s*",
    r"(?i)\buser\s*:\s*",
    r"(?i)override\s+(all|previous|system)",
    r"(?i)bypass\s+(all|previous|system|security)",
    r"(?i)jailbreak",
    r"(?i)DAN\s+mode",

    # 프롬프트 누출 시도
    r"(?i)repeat\s+(your|the|all)\s+(instructions?|prompt|system)",
    r"(?i)show\s+(me\s+)?(your|the)\s+(instructions?|prompt|system)",
    r"(?i)what\s+(are|is)\s+your\s+(instructions?|prompt|rules?)",
    r"(?i)print\s+(your\s+)?(system|instructions?|prompt)",
    r"(?i)reveal\s+(your|the)\s+(system|instructions?|prompt)",
    r"(?i)display\s+(your|the)\s+(system|instructions?|prompt)",

    # 코드 실행 시도
    r"(?i)execute\s+(this|the|following)\s+(code|command|script)",
    r"(?i)run\s+(this|the|following)\s+(code|command|script)",
    r"(?i)\beval\s*\(",
    r"(?i)\bexec\s*\(",
    r"(?i)import\s+os",
    r"(?i)subprocess",

    # 구분자 우회 시도
    r"```\s*(system|assistant|user)",
    r"\[\[\s*(system|user|assistant)",
    r"<\|(system|user|assistant|im_start|im_end)",
    r"<<\s*(SYS|INST)",

    # 한글 인젝션 패턴
    r"이전\s*(지시|명령|규칙|프롬프트).*(무시|잊어|삭제|취소)",
    r"새로운\s*(역할|지시|명령|규칙)",
    r"너는\s*이제\s*(부터)?",
    r"시스템\s*프롬프트",
    r"역할\s*(을|를)?\s*(바꿔|변경|수정)",
    r"(모든|전체)\s*(규칙|지시).*(무시|삭제)",
    r"(지시|명령).*(따르지\s*마|무시해)",

    # 위험한 의료 관련 요청
    r"(?i)(lethal|fatal|deadly)\s+dose",
    r"(?i)how\s+to\s+(overdose|kill|harm)",
    r"(?i)(자살|자해)\s*(방법|약물)",
    r"(?i)과다\s*복용\s*(방법|양)",
]

# 금지 시퀀스
FORBIDDEN_SEQUENCES = [
    "\x00",           # Null byte
    "\x1b",           # Escape sequence
    "\r\n\r\n",       # HTTP header injection
    "{{",             # Template injection
    "}}",
    "${",             # Variable injection
    "$(",
    "`",              # Command substitution
    "\\u00",          # Unicode escape
    "\\x",            # Hex escape
]

# API 검색어에 금지된 문자
API_FORBIDDEN_CHARS = [
    ";",              # SQL injection
    "--",
    "/*",
    "*/",
    "<script",        # XSS
    "</script",
    "&&",             # Command injection
    "||",
    "|",
    "$(",
    "$()",
]

# 허용된 카테고리 목록
VALID_CATEGORIES = {"brand_name", "generic_name", "indication"}

# 안전한 폴백 검색어 (JSON 파싱 실패 시)
SAFE_FALLBACK_KEYWORD = "pain relief"
SAFE_FALLBACK_CATEGORY = "indication"
