"""OpenFDA API 클라이언트 - 실시간 API 호출"""
import re
import requests
from urllib.parse import quote
from src.config import OPENFDA_BASE_URL, OPENFDA_API_KEY, OPENFDA_LABEL_ENDPOINT, SEARCH_LIMIT


class OpenFDAClient:
    """OpenFDA API 호출을 담당하는 클라이언트 클래스"""

    def __init__(self):
        self.base_url = OPENFDA_BASE_URL
        self.api_key = OPENFDA_API_KEY
        self.timeout = 30

    def _build_url(self, endpoint: str, search_query: str, limit: int = SEARCH_LIMIT) -> str:
        """API 요청 URL 생성"""
        url = f"{self.base_url}{endpoint}"
        params = f"?search={search_query}&limit={limit}"
        if self.api_key:
            params += f"&api_key={self.api_key}"
        return url + params

    def _make_request(self, url: str) -> dict:
        """API 요청 실행 및 응답 반환"""
        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 404:
                return {"error": "No results found", "results": []}
            return {"error": str(e), "results": []}
        except requests.RequestException as e:
            return {"error": str(e), "results": []}

    def _sanitize_search_term(self, term: str) -> str:
        """검색어 정화 - 위험한 문자 제거"""
        if not term or not isinstance(term, str):
            return ""

        # 길이 제한
        term = term[:100].strip()

        # 허용 문자만 유지 (영문, 숫자, 공백, 일부 안전한 특수문자)
        term = re.sub(r'[^a-zA-Z0-9\s\-\.,\'\"]', '', term)

        # 연속 공백 정리
        term = re.sub(r'\s+', ' ', term).strip()

        return term

    def search_drug_label(self, field: str, term: str) -> list[dict]:
        """
        의약품 라벨 정보 검색 (보안 강화)
        - field: 검색 필드 (openfda.brand_name, openfda.generic_name, indications_and_usage 등)
        - term: 검색어
        """
        # 검색어 정화
        safe_term = self._sanitize_search_term(term)
        if not safe_term:
            return []

        # URL 인코딩
        encoded_term = quote(safe_term, safe='')

        # 검색어에 공백이 있으면 따옴표로 감싸기
        if " " in safe_term:
            search_query = f'{field}:"{encoded_term}"'
        else:
            search_query = f"{field}:{encoded_term}"

        url = self._build_url(OPENFDA_LABEL_ENDPOINT, search_query)
        data = self._make_request(url)
        results = data.get("results", [])

        # Homeopathy 필터링
        filtered_results = []
        for result in results:
            is_homeopathic = False
            
            # 1. openfda.product_type 확인
            openfda = result.get("openfda", {})
            if not openfda:
                # OpenFDA 메타데이터가 없는 경우 (매칭되지 않은 비승인 약물 등)
                is_homeopathic = True
            
            if not is_homeopathic:
                product_types = openfda.get("product_type", [])
                for pt in product_types:
                    pt_lower = pt.lower()
                    if "homeopathic" in pt_lower or "unapproved homeopathic" in pt_lower:
                        is_homeopathic = True
                        break
            
            # 2. unapproved_pharmaceutical 필드 확인 (OpenFDA flag)
            # 및 Application Number 부재 확인 (Sabal Serrulata 등 비승인 약물 필터링)
            if not is_homeopathic:
                # HUMAN OTC DRUG 또는 HUMAN PRESCRIPTION DRUG인데 application_number가 없으면 승인받지 않은(unapproved) 제품일 확률 높음
                is_drug = any("human" in pt.lower() and "drug" in pt.lower() for pt in product_types)
                if is_drug and not openfda.get("application_number"):
                     is_homeopathic = True

            # 3. spl_product_data_elements 확인
            if not is_homeopathic:
                spl_elements = result.get("spl_product_data_elements", [])
                if isinstance(spl_elements, list):
                    for elem in spl_elements:
                        elem_lower = elem.lower()
                        if "homeopathic" in elem_lower or "unapproved homeopathic" in elem_lower:
                            is_homeopathic = True
                            break
            
            if not is_homeopathic:
                filtered_results.append(result)

        return filtered_results


def search_by_brand_name(brand_name: str) -> list[dict]:
    """브랜드명으로 검색"""
    client = OpenFDAClient()
    return client.search_drug_label("openfda.brand_name", brand_name)


def search_by_generic_name(generic_name: str) -> list[dict]:
    """일반명(성분명)으로 검색"""
    client = OpenFDAClient()
    return client.search_drug_label("openfda.generic_name", generic_name)


def search_by_indication(indication: str) -> list[dict]:
    """적응증(효능)으로 검색"""
    client = OpenFDAClient()
    return client.search_drug_label("indications_and_usage", indication)
