from dotenv import load_dotenv
load_dotenv()

from src.api.visitkorea_client import VisitKoreaClient
import json

# JpnService2 contentTypeId (KorService2와 다름)
CTYPE_ATTRACTION = "76"   # 관광지·명소
CTYPE_FOOD       = "82"   # 음식점·카페
CTYPE_FESTIVAL   = "85"   # 축제·행사

BUSAN_AREA_CODE = "6"

client = VisitKoreaClient()

def fetch_all(area_code: str, content_type_id: str) -> list:
    items, page = [], 1
    while True:
        batch, _, _, total = client.search_attractions(
            area_code=area_code,
            content_type_id=content_type_id,
            page_no=page,
            num_of_rows=100,
        )
        items.extend(i.to_dict() for i in batch)
        if len(items) >= total or not batch:
            break
        page += 1
    return items

festivals   = fetch_all(BUSAN_AREA_CODE, CTYPE_FESTIVAL)    # 7건
attractions = fetch_all(BUSAN_AREA_CODE, CTYPE_ATTRACTION)  # 133건
cultures    = fetch_all(BUSAN_AREA_CODE, CTYPE_FOOD)        # 10건

result = {
    "area": "부산 (areaCode=6)",
    "festival":   {"total": len(festivals),   "items": festivals},
    "attraction": {"total": len(attractions), "items": attractions},
    "culture":    {"total": len(cultures),    "items": cultures},
}

print(json.dumps(result, ensure_ascii=False, indent=2))
