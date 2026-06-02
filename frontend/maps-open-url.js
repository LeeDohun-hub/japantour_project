/**
 * Google Maps 外部リンク — place_id / cid / 座標 / 地域付き検索の優先順位
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

  function disambiguatedSearchQuery(name, place, opts) {
    const n = String(name || "").trim();
    if (!n) return "";
    const hint = locationHint(place, opts);
    const parts = [n];
    if (hint && hint !== "韓国" && !n.includes(hint)) parts.push(hint);
    const joined = parts.join(" ");
    if (!/韓国|대한민국|Korea|South Korea/i.test(joined)) parts.push("韓国");
    return parts.join(" ");
  }

  function naverSearchUrl(query) {
    const q = String(query || "").trim();
    return q ? `https://map.naver.com/p/search/${encodeURIComponent(q)}` : "https://map.naver.com/";
  }

  function naverCoordUrl(name, lat, lng) {
    const q = encodeURIComponent(String(name || `${lat},${lng}`).trim());
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

    const pid = extractPlaceId(place, raw);
    if (/map\.naver\.com/i.test(raw)) return raw;

    const preferNaver =
      opts?.provider === "naver" ||
      place?.source === "naver_maps_geocode" ||
      place?.source === "naver_maps_search_url";
    if (preferNaver) {
      if (lat != null && lng != null && !Number.isNaN(lat) && !Number.isNaN(lng) && isKoreanCoords(lat, lng)) {
        return naverCoordUrl(name, lat, lng);
      }
      const q = disambiguatedSearchQuery(name, place, opts);
      return naverSearchUrl(q);
    }

    if (pid) {
      const q = disambiguatedSearchQuery(name || "place", place, opts);
      return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(q)}&query_place_id=${encodeURIComponent(pid)}`;
    }

    const cid = extractCid(raw);
    if (cid) {
      return `https://www.google.com/maps?cid=${cid}`;
    }

    if (raw && !isCoordOnlyPlaceUrl(raw) && /maps\.google|google\.com\/maps/i.test(raw)) {
      return raw;
    }

    if (lat != null && lng != null && !Number.isNaN(lat) && !Number.isNaN(lng) && isKoreanCoords(lat, lng)) {
      return `https://www.google.com/maps?q=${lat},${lng}&z=17`;
    }

    const fromUrl = parseCoordsFromUrl(raw);
    if (fromUrl && isKoreanCoords(fromUrl.lat, fromUrl.lng)) {
      return `https://www.google.com/maps?q=${fromUrl.lat},${fromUrl.lng}&z=17`;
    }

    if (name) {
      const q = disambiguatedSearchQuery(name, place, opts);
      return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(q)}`;
    }

    return raw || "#";
  }

  global.MapsOpenUrl = { build, extractCid, extractPlaceId, disambiguatedSearchQuery };
})(typeof window !== "undefined" ? window : globalThis);
