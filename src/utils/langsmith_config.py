"""LangSmith 추적 설정"""
import os
from src.config import LANGSMITH_API_KEY


def configure_langsmith():
    """LangSmith 추적 활성화"""
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = LANGSMITH_API_KEY or ""
    os.environ["LANGCHAIN_PROJECT"] = "openfda-drug-info-rag"
