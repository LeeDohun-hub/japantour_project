/**
 * Naver Map 外部リンク — 座標 / 地域付き検索の優先順位
 */
(function (global) {
  "use strict";

  const KR_LAT_MIN = 33.0;
  const KR_LAT_MAX = 39.5;
  const KR_LNG_MIN = 124.0;
  const KR_LNG_MAX = 132.0;

  const REGION_LABEL = {
    gangwon: "江原",
    busan: "釜山",
    jeju: "済州",
    gyeonggi: "京畿",
    seoul: "ソウル",
    incheon: "仁川",
    chungcheong: "大田",
    jeolla: "全州",
    gyeongsang: "大邱",
  };

  const ADDR_CITY_RE =
    /(인천|仁川|Incheon|서울|Seoul|부산|Busan|대전|Daejeon|제주|Jeju|고양|Goyang|강릉|Gangneung|속초|Sokcho|춘천|Chuncheon|수원|Suwon|경주|Gyeongju|광주|Gwangju|전주|Jeonju|청주|Cheongju|천안|Cheonan)/i;

  function extractCid(url) {
    const m = String(url || "").match(/[?&]cid=(\d+)/);
    return m ? m[1] : null;
  }

  function extractPlaceId(place, url) {
    const fromField = place?.place_id || place?.placeId;
    if (fromField) {
      const pid = String(fromField).replace(/^places\//, "");
      if (pid) return pid;
    }
    const raw = place?.google_maps_uri || place?.maps_url || url || "";
    let m = raw.match(/[?&]place_id=([A-Za-z0-9_-]+)/i);
    if (m) return m[1];
    m = raw.match(/place_id[=:]([A-Za-z0-9_-]+)/i);
    if (m) return m[1];
    m = raw.match(/(ChIJ[A-Za-z0-9_-]{10,})/);
    return m ? m[1] : null;
  }

  function isCoordOnlyPlaceUrl(url) {
    return /\/maps\/place\/@/i.test(url || "");
  }

  function isKoreanCoords(lat, lng) {
    return (
      lat >= KR_LAT_MIN &&
      lat <= KR_LAT_MAX &&
      lng >= KR_LNG_MIN &&
      lng <= KR_LNG_MAX
    );
  }

  function parseCoordsFromUrl(url) {
    const m = String(url || "").match(/@(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)/);
    if (!m) return null;
    const lat = parseFloat(m[1]);
    const lng = parseFloat(m[2]);
    if (Number.isNaN(lat) || Number.isNaN(lng)) return null;
    return { lat, lng };
  }

  function locationHint(place, opts) {
    const addr = String(place?.address || "");
    const am = addr.match(ADDR_CITY_RE);
    if (am) return am[1];
    const area = String(place?.search_area || "").trim();
    if (area) return area;
    const cities = String(opts?.regionCities || opts?.region_cities || "").trim();
    if (cities) {
      const first = cities.split(/[,、·/\s]+/).map((s) => s.trim()).find((s) => s.length >= 2);
      if (first) return first;
    }
    const regions = opts?.regions || [];
    if (regions.length === 1 && REGION_LABEL[regions[0]]) {
      return REGION_LABEL[regions[0]];
    }
    return "韓国";
  }

  function _hasKana(str) {
    return /[぀-ゟ゠-ヿ]/.test(String(str || ""));
  }

  // CJK 한자만 있고 한글이 없으면 일본어 한자로 간주 (上道門石垣村 등 VK 일본어 타이틀)
  function _hasJapanese(str) {
    const s = String(str || "");
    if (_hasKana(s)) return true;
    return /[一-鿿㐀-䶿]/.test(s) && !/[가-힣]/.test(s);
  }

  function _extractKoreanFromParens(str) {
    const m = String(str || "").match(/[（(]([가-힣][가-힣\s·]{0,40})[)）]/);
    return m ? m[1].trim() : null;
  }

  function _koreanSearchName(name, place) {
    if (!_hasJapanese(name)) return name;
    const koFromParens = _extractKoreanFromParens(name);
    if (koFromParens) return koFromParens;
    const korAddr = String(place?.address || "").trim();
    if (korAddr) return korAddr;
    return name;
  }

  function disambiguatedSearchQuery(name, place, opts) {
    const n = String(name || "").trim();
    if (!n) return "";
    const searchBase = _koreanSearchName(n, place);
    const hint = locationHint(place, opts);
    const parts = [searchBase];
    if (hint && hint !== "韓国" && !searchBase.includes(hint)) parts.push(hint);
    const joined = parts.join(" ");
    if (!/韓国|대한민국|Korea|South Korea/i.test(joined)) parts.push("韓国");
    return parts.join(" ");
  }

  function naverSearchUrl(query) {
    const q = String(query || "").trim();
    return q ? `https://map.naver.com/p/search/${encodeURIComponent(q)}` : "https://map.naver.com/";
  }

  function naverCoordUrl(name, lat, lng) {
    const displayName = _koreanSearchName(name, null);
    // 한국어로 변환 실패 시(일본어 한자 잔류 등) 좌표만 검색어로 사용
    const searchTerm = _hasJapanese(displayName) ? `${lat},${lng}` : (displayName || `${lat},${lng}`);
    const q = encodeURIComponent(searchTerm.trim());
    return `https://map.naver.com/p/search/${q}?c=${lng},${lat},16,0,0,0,dh`;
  }

  /**
   * @param {object} place — name, address, latitude, place_id, google_maps_uri …
   * @param {object} [opts] — url, label, regions, regionCities
   */
  function build(place, opts) {
    opts = opts || {};
    const name = String(place?.name || opts.label || "").trim();
    const raw = String(place?.google_maps_uri || place?.maps_url || opts.url || "");
    const lat =
      place?.latitude != null && place?.latitude !== ""
        ? Number(place.latitude)
        : null;
    const lng =
      place?.longitude != null && place?.longitude !== ""
        ? Number(place.longitude)
        : null;

    if (/map\.naver\.com/i.test(raw)) {
      // Naver URL 검색어가 일본어인 경우: name 필드로 판정 (URL은 퍼센트인코딩이라 직접 판정 불가)
      if (_hasJapanese(name)) {
        // ① 괄호 안 한국어명이 있으면 그걸로 검색 (景福宮（경복궁）→ 경복궁)
        const koFromParens = _extractKoreanFromParens(name);
        if (koFromParens) {
          return naverSearchUrl(disambiguatedSearchQuery(koFromParens, place, opts));
        }
        // ② 한국어명 추출 불가(上道門石垣村 등) → 좌표로 정확한 위치 직접 오픈
        if (lat != null && lng != null && !Number.isNaN(lat) && !Number.isNaN(lng) && isKoreanCoords(lat, lng)) {
          return `https://map.naver.com/p/search/${lat},${lng}?c=${lng},${lat},16,0,0,0,dh`;
        }
      }
      return raw;
    }

    if (lat != null && lng != null && !Number.isNaN(lat) && !Number.isNaN(lng) && isKoreanCoords(lat, lng)) {
      return naverCoordUrl(name, lat, lng);
    }

    const fromUrl = parseCoordsFromUrl(raw);
    if (fromUrl && isKoreanCoords(fromUrl.lat, fromUrl.lng)) {
      return naverCoordUrl(name, fromUrl.lat, fromUrl.lng);
    }

    if (name) {
      const q = disambiguatedSearchQuery(name, place, opts);
      return naverSearchUrl(q);
    }

    return raw || "#";
  }

  global.MapsOpenUrl = { build, extractCid, extractPlaceId, disambiguatedSearchQuery };
})(typeof window !== "undefined" ? window : globalThis);
