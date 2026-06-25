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
    gangwon: "강원",
    busan: "부산",
    jeju: "제주",
    gyeonggi: "경기",
    seoul: "서울",
    incheon: "인천",
    chungcheong: "대전",
    jeolla: "전주",
    gyeongsang: "대구",
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
    return "대한민국";
  }

  function _hasKana(str) {
    return /[\u3040-\u30ff]/.test(String(str || ""));
  }

  function _hasKorean(str) {
    return /[가-힣]/.test(String(str || ""));
  }

  // CJK 한자만 있고 한글이 없으면 일본어 한자로 간주 (上道門石垣村 등 VK 일본어 타이틀)
  function _hasJapanese(str) {
    const s = String(str || "");
    if (_hasKana(s)) return true;
    return /[\u3400-\u9fff]/.test(s) && !/[가-힣]/.test(s);
  }

  // 한글+한자 혼재 이름에서 CJK 한자 제거 -> Naver 검색 호환성
  function _stripMixedCJK(str) {
    const s = String(str || "");
    if (/[가-힣]/.test(s) && /[㐀-鿿]/.test(s)) {
      return s.replace(/[㐀-鿿]+s*/g, "").replace(/s{2,}/g, " ").trim();
    }
    return s;
  }

  // 알려진 Naver 정확 검색명 (간략 표기 -> 공식 등록명)
  const KNOWN_NAVER_NAMES = {
    "명동성당": "천주교 서울대교구 주교좌명동대성당",
    "명동대성당": "천주교 서울대교구 주교좌명동대성당",
  };
  function _resolveKnownNaverName(name) {
    const compact = (name || "").replace(/s+/g, "");
    for (const [k, v] of Object.entries(KNOWN_NAVER_NAMES)) {
      if (compact === k.replace(/s+/g, "")) return v;
    }
    return "";
  }

    function _extractKoreanFromParens(str) {
    const m = String(str || "").match(/[（(]([가-힣][가-힣\s·]{0,40})[)）]/);
    return m ? m[1].trim() : null;
  }

  function _naverSearchTerm(url) {
    try {
      const m = String(url || "").match(/\/search\/([^?#]+)/i);
      return m ? decodeURIComponent(m[1].replace(/\+/g, " ")).trim() : "";
    } catch {
      return "";
    }
  }

  function _bestKoreanName(place, fallbackName) {
    const name = String(place?.name || "").trim();
    const fromNameParens = _extractKoreanFromParens(name);
    if (fromNameParens) return fromNameParens;
    const jpName = String(place?.name_ja || place?.display_name_ja || "").trim();
    const fromJaParens = _extractKoreanFromParens(jpName);
    if (fromJaParens) return fromJaParens;
    if (name && _hasKorean(name) && !_hasJapanese(name)) return _stripMixedCJK(name);
    const fallbackParens = _extractKoreanFromParens(fallbackName);
    if (fallbackParens) return fallbackParens;
    const fallback = String(fallbackName || "").trim();
    if (fallback && _hasKorean(fallback) && !_hasJapanese(fallback)) return fallback;
    return "";
  }

  function _koreanSearchName(name, place) {
    const knownName = _resolveKnownNaverName(name);
    if (knownName) return knownName;
    const koName = _bestKoreanName(place, name);
    if (koName) return koName;
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
    if (hint && hint !== "대한민국" && !searchBase.includes(hint)) parts.push(hint);
    const joined = parts.join(" ");
    if (!/韓国|대한민국|Korea|South Korea/i.test(joined)) parts.push("대한민국");
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
      const rawSearchTerm = _naverSearchTerm(raw);
      // 표시名이 일본어でも、検証済みURLが韓国語の検索語(例: 서울스카이)を持っていれば
      // それを使う。LLMは韓国語URLを出すが、place.nameが日本語名のとき名前で再生成して
      // 日本語URLになる不具合(例: ソウルスカイ)を防ぐ。
      if (
        _hasJapanese(name) &&
        rawSearchTerm &&
        _hasKorean(rawSearchTerm) &&
        !_hasJapanese(rawSearchTerm)
      ) {
        return naverSearchUrl(disambiguatedSearchQuery(rawSearchTerm, place, opts));
      }
      const koName = _bestKoreanName(place, name || rawSearchTerm);
      if (koName && (_hasJapanese(name) || _hasJapanese(rawSearchTerm))) {
        return naverSearchUrl(disambiguatedSearchQuery(koName, place, opts));
      }
      // Naver URL 검색어가 일본어인데 한국어명을 못 찾으면 좌표로 정확한 위치 직접 오픈
      if (_hasJapanese(name) || _hasJapanese(rawSearchTerm)) {
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
