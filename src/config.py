"""환경 변수 및 설정"""
import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")

# Search (향후 벡터/RAG 검색 시 사용)
SEARCH_LIMIT = 20

# LLM Configuration
CLASSIFIER_MODEL = "gpt-5-nano"
LLM_MODEL = "gpt-4.1-mini"
LLM_TEMPERATURE = 0.0

# 필수 환경 변수 검증
REQUIRED_ENV_VARS = ["OPENAI_API_KEY"]


def validate_env():
    """필수 환경 변수 존재 여부 확인"""
    missing = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
    if missing:
        raise EnvironmentError(
            f"필수 환경 변수가 설정되지 않았습니다: {', '.join(missing)}\n"
            f".env 파일을 확인하세요."
        )


validate_env()

# LangSmith Tracing (선택)
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"] = LANGSMITH_API_KEY or ""
os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGCHAIN_PROJECT", "japantour")
