"""OpenFDA API 응답을 LLM 컨텍스트용 텍스트로 포맷"""
from typing import Optional


# 라벨 데이터에서 추출할 필드와 라벨 매핑
LABEL_FIELD_MAP = {
    "brand_name": "Brand Name",
    "generic_name": "Generic Name",
    "manufacturer_name": "Manufacturer",
    "purpose": "Purpose",
    "indications_and_usage": "Indications and Usage",
    "dosage_and_administration": "Dosage and Administration",
    "warnings": "Warnings",
    "do_not_use": "Do Not Use",
    "stop_use": "Stop Use When",
    "drug_interactions": "Drug Interactions",
    "contraindications": "Contraindications",
    "pregnancy_or_breast_feeding": "Pregnancy/Breastfeeding",
    "active_ingredient": "Active Ingredients",
    "storage_and_handling": "Storage and Handling",
}


def _extract_value(data: dict, key: str) -> Optional[str]:
    """딕셔너리에서 값 추출 (리스트면 첫 번째 요소, 중첩 openfda 필드 처리)"""
    # openfda 중첩 필드 확인
    if key in ["brand_name", "generic_name", "manufacturer_name"]:
        openfda = data.get("openfda") or {}
        value = openfda.get(key, [])
    else:
        value = data.get(key, [])

    if isinstance(value, list) and value:
        # 리스트의 첫 번째 요소 또는 여러 개 합치기
        if len(value) == 1:
            return value[0]
        else:
            return "; ".join(str(v) for v in value[:3])
    elif isinstance(value, str):
        return value
    return None


def format_drug_label(label: dict) -> str:
    """단일 의약품 라벨 데이터를 포맷"""
    lines = []
    for field, display_name in LABEL_FIELD_MAP.items():
        value = _extract_value(label, field)
        if value:
            # 너무 긴 텍스트는 잘라내기 (토큰 절약)
            if len(value) > 800:
                value = value[:800] + "..."
            lines.append(f"[{display_name}] {value}")
    return "\n".join(lines) if lines else "(No data available)"


def format_label_results(results: list[dict]) -> str:
    """여러 라벨 검색 결과를 하나의 컨텍스트로 포맷"""
    if not results:
        return "(No search results found)"

    parts = []
    for i, label in enumerate(results[:5], 1):  # 최대 5개
        header = f"── Result {i} ──"
        body = format_drug_label(label)
        parts.append(f"{header}\n{body}")
    return "\n\n".join(parts)
