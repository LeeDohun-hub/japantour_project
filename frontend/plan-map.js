/**
 * 旅行プラン — Google Maps + Dayタブ + スポットカード（Triple風）
 */
(function (global) {
  "use strict";

  const MAPS_URL_RE = /^https?:\/\/(?:maps\.google\.com|www\.google\.com\/maps|goo\.gl\/maps|maps\.app\.goo\.gl|map\.naver\.com)\/\S+/i;
  const DAY_HEADER_RE =
    /^(?:#{1,3}\s*)?(?:【\s*)?(?:Day\s*)?(\d+)\s*日目|^(?:#{1,3}\s*)?第\s*(\d+)\s*日|^(?:#{1,3}\s*)?Day\s*(\d+)\b|最終日|帰国日|最終\s*日|^첫날|^(\d+)\s*(?:일째|일차|일\s*차)|^최종일|^마지막\s*날/i;
  const GMAPS_CALLBACK = "__planMapGmapsReady";

  // 한국 영토 바운딩 박스 (geocoding 결과 검증용)
  const KR_LAT_MIN = 33.0, KR_LAT_MAX = 39.5;
  const KR_LNG_MIN = 124.0, KR_LNG_MAX = 132.0;

  // 일본 지명 패턴 — LLM 환각(신오쿠보, 신주쿠 등)으로 생성된 stop 제거
  const JP_LOCATION_RE = /신주쿠|신오쿠보|하라주쿠|아키하바라|시부야|긴자|이케부쿠로|우에노|아사쿠사|롯폰기|히가시|나고야|오사카|교토|후쿠오카|삿포로|요코하마|도쿄|일본|東京|大阪|日本|Japan/i;

  const AIRPORT_GEO = {
    ICN: { lat: 37.4602, lng: 126.4407, name: "仁川国際空港" },
    CJU: { lat: 33.5113, lng: 126.4930, name: "済州国際空港" },
    PUS: { lat: 35.1796, lng: 128.9382, name: "金海国際空港" },
    GMP: { lat: 37.5583, lng: 126.7906, name: "金浦国際空港" },
  };

  const ADDRESS_COORD_FALLBACKS = [
    { re: /고양시\s*덕양구|덕양구|Goyang\s+Deogyang/i, lat: 37.6374, lng: 126.8320 },
    { re: /고양시|Goyang/i, lat: 37.6584, lng: 126.8320 },
  ];

  function fallbackCoordsForAddress(text) {
    const raw = String(text || "");
    const hit = ADDRESS_COORD_FALLBACKS.find((x) => x.re.test(raw));
    return hit ? { lat: hit.lat, lng: hit.lng } : null;
  }

  function _isKoreanCoords(lat, lng) {
    return lat >= KR_LAT_MIN && lat <= KR_LAT_MAX && lng >= KR_LNG_MIN && lng <= KR_LNG_MAX;
  }

  function _isJpLocation(label) {
    return JP_LOCATION_RE.test(label || "");
  }

  let _mapsApiKey = null;
  let _mapsProvider = "google";
  let _mapsLoadPromise = null;
  let _mapInstance = null;
  let _markers = [];
  let _polyline = null;
  let _infoWindow = null;
  let _planDays = [];
  let _activeDay = 1;
  let _mapMeta = {};
  let _originalReply = "";
  const _lockedStops = new Map();

  function esc(s) {
    return String(s || "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  function mapsOpenUrl(stop) {
    const p = stop?.place || {};
    const opts = {
      url: stop?.url,
      label: stop?.label,
      provider: _mapsProvider,
      regions: _mapMeta.regions || [],
      regionCities: _mapMeta.regionCities || _mapMeta.region_cities || "",
    };
    if (global.MapsOpenUrl?.build) {
      return MapsOpenUrl.build(
        { ...p, name: p.name || stop?.label },
        opts
      );
    }
    if (p.google_maps_uri || p.maps_url || stop?.url) {
      return p.google_maps_uri || p.maps_url || stop?.url;
    }
    if (stop?.lat != null && stop?.lng != null) {
      return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${stop.lat},${stop.lng}`)}`;
    }
    const q = p.name || stop?.label;
    return q ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(q)}` : "#";
  }

  function stopPhotoUrl(stop) {
    const p = stop?.place || {};
    if (stop?.isAirport) return "";
    if (p.photo_url || p.naver_photo_url) return p.photo_url || p.naver_photo_url;
    if (p.photo_name) return `/api/photo/?name=${encodeURIComponent(p.photo_name)}`;
    const mapUrl = p.maps_url || p.google_maps_uri || stop?.url || "";
    const name = String(p.name || "").trim();
    const address = String(p.address || "").trim();
    const label = String(stop?.label || "").trim();
    const line = String(stop?.line || "").trim();
    if (!name && !address && !label && !line) return "";
    const q = [...new Set([p.name, p.address, stop?.label, stop?.line].filter(Boolean))]
      .join(" ")
      .replace(/\s+/g, " ")
      .trim();
    if (!q) return "";
    const coord = stop?.lat != null && stop?.lng != null
      ? `&lat=${encodeURIComponent(stop.lat)}&lng=${encodeURIComponent(stop.lng)}`
      : "";
    if (/map\.naver\.com/i.test(mapUrl)) {
      return `/api/naver-photo/?url=${encodeURIComponent(mapUrl)}&q=${encodeURIComponent(q)}${coord}&image_fallback=1`;
    }
    return `/api/naver-photo/?q=${encodeURIComponent(q)}${coord}&image_fallback=1`;
  }

  function stopThumbHtml(stop) {
    if (stop.isAirport) return `<span class="plan-day-stop__fallback">✈️</span>`;
    const fallbackIcon = stop.isAccommodation ? "🏨" : "📍";
    const photoUrl = stopPhotoUrl(stop);
    if (!photoUrl) return `<span class="plan-day-stop__fallback">${fallbackIcon}</span>`;
    return `<img src="${esc(photoUrl)}" alt="" loading="lazy" onerror="this.outerHTML='<span class=&quot;plan-day-stop__fallback&quot;>${fallbackIcon}</span>'" />`;
  }

  function _coordStop(stop) {
    if (!stop || stop.lat == null || stop.lng == null) return null;
    const lat = Number(stop.lat);
    const lng = Number(stop.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
    return {
      lat,
      lng,
      name: stop.place?.name || stop.label || "",
      stop,
    };
  }

  function _routePoint(stop) {
    const coord = _coordStop(stop);
    if (coord) return coord;
    if (!stop) return null;
    const p = stop.place || {};
    const name = p.name || stop.label || "";
    const address = p.address || stop.line || "";
    if (!name && !address) return null;
    return {
      lat: null,
      lng: null,
      name,
      address,
      stop,
    };
  }

  function _routeStopName(point, fallback) {
    return String(point?.name || point?.address || fallback || "").trim() || fallback;
  }

  function _routeSearchText(from, to) {
    return `${_routeStopName(from, "start")} ${_routeStopName(to, "destination")} 경로`;
  }

  function _hasRouteCoords(point) {
    return point?.lat != null && point?.lng != null;
  }

  function _naverTransitRouteUrl(from, to) {
    if (!_hasRouteCoords(from) || !_hasRouteCoords(to)) {
      return `https://map.naver.com/p/search/${encodeURIComponent(_routeSearchText(from, to))}`;
    }
    const fromName = encodeURIComponent(_routeStopName(from, "start"));
    const toName = encodeURIComponent(_routeStopName(to, "destination"));
    const midLat = ((from.lat + to.lat) / 2).toFixed(6);
    const midLng = ((from.lng + to.lng) / 2).toFixed(6);
    return (
      `https://map.naver.com/p/directions/` +
      `${from.lng},${from.lat},${fromName},PLACE_POI/` +
      `${to.lng},${to.lat},${toName},PLACE_POI/-/transit` +
      `?c=${midLng},${midLat},10,0,0,0,dh`
    );
  }

  function _kakaoRouteUrl(from, to) {
    if (!_hasRouteCoords(from) || !_hasRouteCoords(to)) {
      return `https://map.kakao.com/?q=${encodeURIComponent(_routeSearchText(from, to))}`;
    }
    const fromName = encodeURIComponent(_routeStopName(from, "start"));
    const toName = encodeURIComponent(_routeStopName(to, "destination"));
    return `https://map.kakao.com/link/from/${fromName},${from.lat},${from.lng}/to/${toName},${to.lat},${to.lng}`;
  }

  function _airportAccommodationSegment(day) {
    const stops = day?.stops || [];
    for (let i = 0; i < stops.length - 1; i++) {
      const a = stops[i], b = stops[i + 1];
      if ((a.isAirport && b.isAccommodation) || (a.isAccommodation && b.isAirport)) {
        const from = _routePoint(a);
        const to = _routePoint(b);
        if (from && to) return { from, to };
      }
    }
    const airport = _routePoint(stops.find((s) => s.isAirport));
    const accommodation = _routePoint(stops.find((s) => s.isAccommodation));
    if (!airport || !accommodation) return null;
    const airportIdx = stops.findIndex((s) => s.isAirport);
    const accommodationIdx = stops.findIndex((s) => s.isAccommodation);
    return airportIdx <= accommodationIdx
      ? { from: airport, to: accommodation }
      : { from: accommodation, to: airport };
  }

  function renderAirportTransferCard(day) {
    const segment = _airportAccommodationSegment(day);
    if (!segment) return "";
    const { from, to } = segment;
    const fromIsAirport = Boolean(from.stop?.isAirport);
    const title = fromIsAirport ? "空港 → 宿泊先ルート" : "宿泊先 → 空港ルート";
    const naverUrl = esc(_naverTransitRouteUrl(from, to));
    const kakaoUrl = esc(_kakaoRouteUrl(from, to));
    return `<article class="plan-transfer-card">
      <div class="plan-transfer-card__icon">⇄</div>
      <div class="plan-transfer-card__body">
        <div class="plan-transfer-card__title">${title}</div>
        <div class="plan-transfer-card__route">
          <span>${esc(_routeStopName(from, "出発地"))}</span>
          <span class="plan-transfer-card__arrow">→</span>
          <span>${esc(_routeStopName(to, "到着地"))}</span>
        </div>
      </div>
      <div class="plan-transfer-card__actions">
        <a href="${naverUrl}" target="_blank" rel="noopener">Naver経路</a>
        <a href="${kakaoUrl}" target="_blank" rel="noopener">Kakao経路</a>
      </div>
    </article>`;
  }

  function _normStopText(s) {
    return String(s || "")
      .toLowerCase()
      .replace(/^(?:おすすめ|推薦|推奨|추천|권장)\s*[:：-]?\s*/i, "")
      .replace(/[（(][^）)]*[）)]/g, "")
      .replace(/\s+/g, "")
      .trim();
  }

  function _sameStop(a, b) {
    if (!a || !b) return false;
    if (a.isAirport && b.isAirport) return true;
    if (a.isAccommodation && b.isAccommodation) return true;
    const aUrl = a.place?.google_maps_uri || a.place?.maps_url || a.url || "";
    const bUrl = b.place?.google_maps_uri || b.place?.maps_url || b.url || "";
    if (aUrl && bUrl && mapsUrlKey(aUrl) === mapsUrlKey(bUrl)) return true;
    const an = _normStopText(a.place?.name || a.label);
    const bn = _normStopText(b.place?.name || b.label);
    if (an && bn && (an === bn || (an.length >= 4 && bn.includes(an)) || (bn.length >= 4 && an.includes(bn)))) {
      return true;
    }
    if (a.lat != null && a.lng != null && b.lat != null && b.lng != null) {
      return Math.abs(Number(a.lat) - Number(b.lat)) < 0.0005 &&
        Math.abs(Number(a.lng) - Number(b.lng)) < 0.0005;
    }
    return false;
  }

  function buildAirportStop(iata) {
    const geo = AIRPORT_GEO[String(iata || "").toUpperCase()];
    if (!geo) return null;
    return {
      url: "",
      place: { name: geo.name, latitude: geo.lat, longitude: geo.lng },
      label: geo.name,
      line: geo.name,
      lat: geo.lat,
      lng: geo.lng,
      isAirport: true,
    };
  }

  function buildAccommodationStop(meta) {
    const a = meta?.accommodation || {};
    const selected = a.selectedHotel || a.selectedPlace || {};
    const isPrivateStay = a.type === "friend";
    const lat = a.latitude ?? selected.latitude ?? null;
    const lng = a.longitude ?? selected.longitude ?? null;
    const rawName = isPrivateStay ? "友人・家族宅" : (a.name || selected.name || a.address || a.region || "");
    const address = a.address || selected.address || a.detail || a.region || "";
    const fallbackCoord = fallbackCoordsForAddress(`${address} ${rawName}`);
    const resolvedLat = lat ?? fallbackCoord?.lat ?? null;
    const resolvedLng = lng ?? fallbackCoord?.lng ?? null;
    if (!rawName && !address && resolvedLat == null) return null;
    const name = rawName || "宿泊先";
    return {
      url: selected.google_maps_uri || selected.maps_url || "",
      place: {
        ...(isPrivateStay ? {} : selected),
        name,
        address,
        latitude: resolvedLat,
        longitude: resolvedLng,
        primary_type: "宿泊先",
      },
      label: name,
      line: address || "宿泊先",
      lat: resolvedLat != null ? Number(resolvedLat) : null,
      lng: resolvedLng != null ? Number(resolvedLng) : null,
      isAccommodation: true,
    };
  }

  function ensureDay(days, dayNum, title) {
    let day = days.find((d) => d.day === dayNum);
    if (!day) {
      day = { day: dayNum, title, stops: [] };
      days.push(day);
      days.sort((a, b) => a.day - b.day);
    }
    return day;
  }

  function ensureFallbackDays(days, fallbackDayCount) {
    const n = Number(fallbackDayCount || 0);
    if (!Number.isFinite(n) || n <= 0) return days;
    for (let d = 1; d <= n; d++) {
      ensureDay(days, d, `Day ${d}`);
    }
    days.sort((a, b) => a.day - b.day);
    return days;
  }

  function normalizePlanDays(days, fallbackDayCount) {
    const n = Number(fallbackDayCount || 0);
    const hasCap = Number.isFinite(n) && n > 0;
    const byDay = new Map();
    for (const src of days || []) {
      const dayNum = Number(src?.day || 0);
      if (!Number.isFinite(dayNum) || dayNum <= 0) continue;
      if (hasCap && dayNum > n) continue;
      const existing = byDay.get(dayNum);
      if (existing) {
        existing.stops.push(...(src.stops || []));
        if (!existing.title || /^Day\s+\d+$/i.test(existing.title)) {
          existing.title = src.title || existing.title;
        }
      } else {
        byDay.set(dayNum, {
          day: dayNum,
          title: src.title || `Day ${dayNum}`,
          stops: [...(src.stops || [])],
        });
      }
    }
    const out = [...byDay.values()].sort((a, b) => a.day - b.day);
    out.forEach((day) => {
      const deduped = [];
      for (const stop of day.stops || []) {
        if (!deduped.some((existing) => _sameStop(existing, stop))) {
          deduped.push(stop);
        }
      }
      day.stops = deduped;
    });
    ensureFallbackDays(out, fallbackDayCount);
    return out;
  }

  function _textHasAny(text, words) {
    const s = String(text || "").toLowerCase();
    return words.some((w) => s.includes(String(w).toLowerCase()));
  }

  function _isSudogwonAccommodation(meta) {
    const a = meta?.accommodation || {};
    const text = [
      a.name,
      a.address,
      a.detail,
      a.region,
      a.selectedHotel?.address,
      a.selectedPlace?.address,
    ].filter(Boolean).join(" ");
    return _textHasAny(text, [
      "서울", "ソウル", "seoul",
      "경기", "京畿", "gyeonggi",
      "인천", "仁川", "incheon",
      "고양", "高陽", "goyang",
      "수원", "水原", "suwon",
    ]);
  }

  function _isLongDistanceFromAccommodation(meta) {
    if (!_isSudogwonAccommodation(meta)) return false;
    const regions = meta?.regions || [];
    if (regions.some((r) => ["gangwon", "chungcheong", "jeolla", "gyeongsang", "jeju"].includes(r))) {
      return true;
    }
    const targetText = [
      ...(Array.isArray(regions) ? regions : [regions]),
      meta?.regionCities,
      meta?.region_cities,
      meta?.title,
    ].filter(Boolean).join(" ");
    return _textHasAny(targetText, [
      "부산", "釜山", "busan",
      "광주", "光州", "gwangju",
      "강릉", "江陵", "gangneung",
      "속초", "束草", "sokcho",
      "제주", "済州", "jeju",
      "대구", "大邱", "daegu",
      "전주", "全州", "jeonju",
      "여수", "麗水", "yeosu",
    ]);
  }

  function _isTransitOrAnchorLine(line) {
    return /(?:入国|出国|チェックイン|ホテル|宿泊|空港|移動|休息|休憩|到着|出発|手荷物|審査|税関|AREX|乗換|下車|徒歩|タクシー|リムジン|コンビニ|軽食)/i.test(line || "");
  }

  function _isRecommendationLine(line) {
    return /^(?:おすすめ|推薦|推奨|추천|권장)\s*[:：-]?/i.test(String(line || "").trim());
  }

  function _isPlanNoiseLine(line) {
    const t = String(line || "").trim();
    if (!t) return true;
    if (/^(?:外観写真|写真|地図|経路|ルート|지도|통로|Map|Directions)$/i.test(t)) return true;
    if (/^【(?:予算|旅行|全体|注意|参考|移動|ポイント|チェックリスト)/.test(t)) return true;
    if (/^\[(?:予算|旅行|全体|注意|参考|移動|ポイント)/.test(t)) return true;
    if (/^(?:예산|여행의\s*포인트|전체\s*포인트|주의|참고)\b/.test(t)) return true;
    if (/^★\s*\d/.test(t) || /^(?:営業中|営業終了|영업\s*중|영업\s*종료|¥+|₩+)/.test(t)) return true;
    if (/(?:Google|グーグル|평점|評価|口コミ|件|메뉴|メニュー)/i.test(t)) return true;
    if (/(?:この日|이 날|当日).*(?:候補|動線|移動経路|식사|동선|경로)/.test(t)) return true;
    if (/(?:外観|写真|カード|本文で引用|본문에서 인용)/.test(t)) return true;
    if (/(?:食事候補リスト|식사\s*후보|レストラン情報がありません|現地で|현지에서|探す|찾으|利用してください|이용해)/i.test(t)) return true;
    if (/^(?:午前|午後|昼食|夕食|朝食|夜|ランチ|ディナー|朝|昼|食事|오전|오후|점심|저녁|아침)\s*$/.test(t)) return true;
    return false;
  }

  function _candidateVenueTexts(line) {
    const t = String(line || "").trim();
    if (!t) return [];
    const out = [];
    const add = (s) => {
      s = String(s || "")
        .replace(/^[-・*①②③④⑤⑥⑦⑧⑨⑩]\s*/, "")
        .replace(/^\[[^\]]+\]\s*/, "")
        .replace(/^【[^】]+】\s*/, "")
        .replace(/^(?:午前|午後|昼食|夕食|朝食|夜|ランチ|ディナー|朝|昼|食事)[:：\s]+/, "")
        .replace(/[（(][^）)]*[）)]/g, " ")
        .trim();
      if (s && !out.includes(s)) out.push(s);
    };

    add(t);
    for (const part of t.split(/[·・]/)) add(part);
    const quoteHead = t.split(/[「『'“"<]/)[0];
    if (quoteHead !== t) add(quoteHead);
    const venueTail = t.match(/(?:\d{4}[-./]\d{1,2}[-./]\d{1,2}[^·・]*[·・]\s*)(.+)$/);
    if (venueTail) add(venueTail[1]);
    return out;
  }

  function _explicitPlaceFromLine(line, placeIndex) {
    if (!placeIndex?.byName) return null;
    if (_isTransitOrAnchorLine(line)) return null;
    if (_isRecommendationLine(line) || _isPlanNoiseLine(line)) return null;
    for (const text of _candidateVenueTexts(line)) {
      if (
        !text ||
        text.length > 54 ||
        /[。.!?！？]/.test(text) ||
        /(?:おすすめ|人気|地元|現地|代表|確認|利用|楽し|撮影|散策|移動|候補|動線|経路|전망|시가지|현지|추천|인기|대표|확인|이용|즐기|후보|동선|경로|없습니다|찾)/i.test(text)
      ) {
        continue;
      }
      const norm = _normStopText(text);
      if (!norm) continue;
      if (placeIndex.byName[norm]) return placeIndex.byName[norm];
      for (const [key, p] of Object.entries(placeIndex.byName)) {
        if (!key || key.length < 4) continue;
        if (norm === key) return p;
        if (norm.startsWith(key)) {
          const original = text.replace(/\s+/g, "");
          const keyLenApprox = (p?.name || "").replace(/\s+/g, "").length || key.length;
          const next = original.slice(keyLenApprox, keyLenApprox + 1);
          if (!next || /[\s'’"“”「」『』<＜(（·・:：-]/.test(next)) return p;
        }
      }
    }
    return null;
  }

  function _isRouteTailSection(line) {
    const t = String(line || "").trim();
    if (!t) return false;
    return /^(?:旅行チェックリスト|旅のチェックリスト|여행\s*체크리스트|チェックリスト|체크리스트)$/i.test(t) ||
      /^🔗/.test(t) ||
      /^🎫/.test(t) ||
      /(?:参照データ|Reference Data|지역\s*주변\s*명소|旅行地周辺|旅行地\s*周辺|スポーツ・イベント・観光|チケット・公演)/i.test(t);
  }

  function _routeRelevantText(reply) {
    const lines = String(reply || "").split(/\r?\n/);
    const startIdx = lines.findIndex((line) =>
      /(?:テキスト詳細計画|텍스트\s*상세\s*계획|詳細計画|상세\s*계획)/i.test(line)
    );
    const start = startIdx >= 0 ? startIdx + 1 : 0;
    const out = [];
    for (let i = start; i < lines.length; i++) {
      if (_isRouteTailSection(lines[i])) break;
      out.push(lines[i]);
    }
    return out.join("\n");
  }

  function _allowedStopKeysFromReply(reply, placeIndex) {
    const text = _routeRelevantText(reply);
    const lines = text.split(/\r?\n/);
    const allowed = new Set();
    const byUrl = placeIndex?.byUrl || placeIndex || {};
    const byName = placeIndex?.byName || {};

    const addPlace = (place, fallbackLabel) => {
      if (!place && !fallbackLabel) return;
      const uri = place?.google_maps_uri || place?.maps_url || "";
      if (uri) allowed.add(`url:${mapsUrlKey(uri)}`);
      const name = _normStopText(place?.name || fallbackLabel || "");
      if (name) allowed.add(`name:${name}`);
    };

    for (let i = 0; i < lines.length; i++) {
      const t = lines[i].trim();
      if (!t) continue;
      if (MAPS_URL_RE.test(t)) {
        const url = t.split(/\s/)[0];
        const place = byUrl[mapsUrlKey(url)] || null;
        addPlace(place, labelBeforeUrl(lines, url));
        continue;
      }
      if (_isRecommendationLine(t) || _isPlanNoiseLine(t) || _isTransitOrAnchorLine(t)) {
        continue;
      }
      const cleaned = t
        .replace(/^[-・*①②③④⑤⑥⑦⑧⑨⑩]\s*/, "")
        .replace(/^\[[^\]]+\]\s*/, "")
        .replace(/^【[^】]+】\s*/, "")
        .replace(/^(?:午前|午後|昼食|夕食|朝食|夜|ランチ|ディナー|朝|昼|食事)[:：\s]+/, "")
        .replace(/[（(][^）)]*[）)]/g, " ")
        .trim();
      if (
        !cleaned ||
        cleaned.length > 36 ||
        /[。.!?！？]/.test(cleaned) ||
        /(?:おすすめ|人気|地元|現地|代表|確認|利用|楽し|撮影|散策|移動|候補|動線|経路|전망|시가지|현지|추천|인기|대표|확인|이용|즐기|후보|동선|경로|없습니다|찾)/i.test(cleaned)
      ) {
        continue;
      }
      const place = byName[_normStopText(cleaned)] || _explicitPlaceFromLine(t, placeIndex);
      if (place) addPlace(place, cleaned);
    }
    return allowed;
  }

  function _stopAllowedByReply(stop, allowedKeys) {
    if (stop?.isAirport || stop?.isAccommodation) return true;
    if (!allowedKeys?.size) return true;
    const uri = stop?.place?.google_maps_uri || stop?.place?.maps_url || stop?.url || "";
    if (uri && allowedKeys.has(`url:${mapsUrlKey(uri)}`)) return true;
    const name = _normStopText(stop?.place?.name || stop?.label || "");
    return Boolean(name && allowedKeys.has(`name:${name}`));
  }

  function addRouteAnchors(days, meta) {
    const airportStop = buildAirportStop(meta?.arrivalAirport);
    const departureAirportStop = buildAirportStop(meta?.departureAirport || meta?.arrivalAirport);
    const accommodationStop = buildAccommodationStop(meta);

    if (airportStop || accommodationStop) {
      const day1 = ensureDay(days, 1, "1日目（到着日）");
      if (airportStop && !day1.stops.some((s) => _sameStop(s, airportStop))) {
        day1.stops.unshift({ ...airportStop });
      }
      if (accommodationStop && !day1.stops.some((s) => _sameStop(s, accommodationStop))) {
        const airportIdx = airportStop
          ? day1.stops.findIndex((s) => _sameStop(s, airportStop))
          : -1;
        day1.stops.splice(Math.max(airportIdx + 1, 0), 0, { ...accommodationStop });
      }
    }

    const finalDayNum = Number(meta?.days || 0);
    if (finalDayNum > 1 && (departureAirportStop || accommodationStop)) {
      const finalDay = ensureDay(days, finalDayNum, "最終日");
      if (accommodationStop && !finalDay.stops.some((s) => _sameStop(s, accommodationStop))) {
        finalDay.stops.unshift({ ...accommodationStop });
      }
      if (departureAirportStop && !finalDay.stops.some((s) => _sameStop(s, departureAirportStop))) {
        finalDay.stops.push({ ...departureAirportStop });
      }
    }

  }

  function showMapStatus(msg, isError) {
    const el = document.getElementById("planMapStatus");
    if (!el) return;
    if (!msg) {
      el.style.display = "none";
      el.textContent = "";
      return;
    }
    el.style.display = "block";
    el.className = isError ? "plan-map-status plan-map-status--error" : "plan-map-status";
    el.innerHTML = msg;
  }

  function mapsUrlKey(url) {
    if (/map\.naver\.com/i.test(String(url || ""))) {
      return String(url).split("?")[0].replace(/\/$/, "");
    }
    const m = String(url).match(/[?&]cid=(\d+)/);
    return m ? `cid:${m[1]}` : String(url).split("&g_mp=")[0].split("&")[0];
  }

  function stopLockKey(stop, dayNum) {
    const p = stop?.place || {};
    const uri = p.google_maps_uri || p.maps_url || stop?.url || "";
    if (uri) return `url:${mapsUrlKey(uri)}`;
    const name = _normStopText(p.name || stop?.label);
    const coords = stop?.lat != null && stop?.lng != null
      ? `${Number(stop.lat).toFixed(5)},${Number(stop.lng).toFixed(5)}`
      : "";
    return `day:${dayNum}|name:${name}|coords:${coords}`;
  }

  function stopLockPayload(stop, dayNum) {
    const p = stop?.place || {};
    return {
      key: stopLockKey(stop, dayNum),
      day: dayNum,
      name: p.name || stop?.label || "",
      category: stop?.isAirport
        ? "空港"
        : stop?.isAccommodation
        ? "宿泊先"
        : p.primary_type || p.types?.[0] || "スポット",
      address: p.address || "",
      url: p.google_maps_uri || p.maps_url || stop?.url || "",
      note: stop?.line && !MAPS_URL_RE.test(stop.line) ? stop.line : "",
    };
  }

  function getLockedItems() {
    return [..._lockedStops.values()].filter((it) => it?.name);
  }

  function clearLocks() {
    _lockedStops.clear();
  }

  function buildPlaceIndex(apiPlaces) {
    const idx = {};
    for (const p of apiPlaces || []) {
      const uri = p.google_maps_uri || p.maps_url;
      if (uri) idx[mapsUrlKey(uri)] = p;
    }
    return idx;
  }

  function labelBeforeUrl(lines, url) {
    const i = lines.findIndex((ln) => ln.trim().startsWith(url) || ln.includes(url));
    if (i <= 0) return "";
    for (let j = i - 1; j >= 0; j--) {
      const t = lines[j].trim();
      if (!t || MAPS_URL_RE.test(t) || t.startsWith("http")) continue;
      if (_isPlanNoiseLine(t) || _isRecommendationLine(t)) continue;
      if (DAY_HEADER_RE.test(t)) return "";
      return t
        .replace(/^\[[\d:〜~\-]+\]\s*/, "")
        .replace(/^[-・*]\s*/, "")
        .replace(/（[^）]*）$/g, "")
        .trim();
    }
    return "";
  }

  function parseDayNumber(line) {
    const t = line.trim();
    if (/最終日|帰国日|最終\s*日|최종일|마지막\s*날/.test(t)) return -1;
    if (/^첫날/.test(t)) return 1;
    const m = t.match(/(\d+)\s*日目|第\s*(\d+)\s*日|Day\s*(\d+)|(\d+)\s*(?:일째|일차|일\s*차)/i);
    if (m) return parseInt(m[1] || m[2] || m[3] || m[4], 10);
    return null;
  }

  function findPlaceForLine(line, placeIndex) {
    return _explicitPlaceFromLine(line, placeIndex);
  }

  function placeToStop(place, line, sourceLineIdx = null) {
    if (!place) return null;
    return {
      url: place.google_maps_uri || place.maps_url || "",
      place,
      label: place.name || line || "スポット",
      line: line || place.name || "",
      sourceLineIdx,
      lat: place.latitude != null ? Number(place.latitude) : null,
      lng: place.longitude != null ? Number(place.longitude) : null,
    };
  }

  function parsePlanDays(reply, placeIndex, fallbackDayCount) {
    const lines = _routeRelevantText(reply).split(/\r?\n/);
    const days = [];
    let current = null;
    let orphanStops = [];

    const pushStop = (dayObj, url, lineIdx) => {
      const trimmed = lines[lineIdx].trim();
      const urlOnly = trimmed.split(/\s/)[0];
      const place = (placeIndex.byUrl || placeIndex || {})[mapsUrlKey(urlOnly)] || null;
      const label = labelBeforeUrl(lines, urlOnly) || place?.name || "スポット";
      const rec = {
        url: urlOnly,
        place,
        label,
        line: trimmed,
        sourceLineIdx: lineIdx,
        sourceUrl: urlOnly,
        lat: place?.latitude != null ? Number(place.latitude) : null,
        lng: place?.longitude != null ? Number(place.longitude) : null,
      };
      if (dayObj) {
        if (!dayObj.stops.some((s) => _sameStop(s, rec))) dayObj.stops.push(rec);
      }
      else orphanStops.push(rec);
    };

    for (let i = 0; i < lines.length; i++) {
      const t = lines[i].trim();
      if (!t) continue;
      const dayNum = parseDayNumber(t);
      if (
        dayNum !== null &&
        (/日目|Day\s*\d|第\s*\d+\s*日|最終日|帰国日|일째|일차|일\s*차|첫날|최종일|마지막/i.test(t) || /^【\s*\d+/.test(t))
      ) {
        const num = dayNum === -1 ? (fallbackDayCount || days.length + 1 || 99) : dayNum;
        current = { day: num, title: t.replace(/^#+\s*/, ""), stops: [] };
        days.push(current);
        continue;
      }
      if (MAPS_URL_RE.test(t)) {
        const url = t.split(/\s/)[0];
        if (current) pushStop(current, url, i);
        else pushStop(null, url, i);
        continue;
      }
      if (current) {
        if (_isRecommendationLine(t) || _isPlanNoiseLine(t)) continue;
        // Keep the map route aligned with the detailed plan: only explicit
        // Google Maps URLs or standalone place-name lines in the plan body
        // create stops. Reference-data/prose matches are intentionally ignored.
        const place = findPlaceForLine(t, placeIndex);
        const rec = placeToStop(place, t, i);
        if (rec && !current.stops.some((s) => _sameStop(s, rec))) {
          current.stops.push(rec);
        }
      }
    }

    if (!days.length && orphanStops.length) {
      const n = Math.max(1, fallbackDayCount || 1);
      for (let d = 1; d <= n; d++) {
        days.push({ day: d, title: `${d}日目`, stops: [] });
      }
      orphanStops.forEach((s, idx) => {
        const bucket = days[Math.min(Math.floor(idx / Math.ceil(orphanStops.length / n)), n - 1)];
        bucket.stops.push(s);
      });
    } else if (orphanStops.length && days.length) {
      days[0].stops.unshift(...orphanStops);
    }

    return normalizePlanDays(days, fallbackDayCount);
  }

  async function fetchMapsConfig() {
    const res = await fetch("/api/maps/config/");
    if (!res.ok) return { enabled: false };
    return res.json();
  }

  function mapsReady() {
    return Boolean(global.google?.maps?.Map);
  }

  function naverMapsReady() {
    return Boolean(global.naver?.maps?.Map);
  }

  function loadGoogleMaps(apiKey) {
    if (mapsReady()) return Promise.resolve();
    if (_mapsLoadPromise) return _mapsLoadPromise;

    _mapsLoadPromise = new Promise((resolve, reject) => {
      let settled = false;
      const done = (fn) => (arg) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        fn(arg);
      };

      global.gm_authFailure = done(() => {
        _mapsLoadPromise = null;
        reject(new Error("AUTH_FAILURE"));
      });

      global[GMAPS_CALLBACK] = done(() => {
        if (mapsReady()) resolve();
        else reject(new Error("MAPS_NOT_READY"));
      });

      const timer = setTimeout(() => {
        done(reject)(new Error("TIMEOUT"));
        _mapsLoadPromise = null;
      }, 20000);

      const prev = document.querySelector("script[data-plan-map-gmaps]");
      if (prev) prev.remove();

      const s = document.createElement("script");
      s.dataset.planMapGmaps = "1";
      s.async = true;
      s.defer = true;
      s.src =
        `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}` +
        `&callback=${GMAPS_CALLBACK}&loading=async` +
        `&libraries=geometry&v=weekly&language=ja&region=KR`;
      s.onerror = done(() => {
        _mapsLoadPromise = null;
        reject(new Error("SCRIPT_LOAD"));
      });
      document.head.appendChild(s);
    });

    return _mapsLoadPromise;
  }

  function loadNaverMaps(apiKey) {
    if (naverMapsReady()) return Promise.resolve();
    if (_mapsLoadPromise) return _mapsLoadPromise;

    _mapsLoadPromise = new Promise((resolve, reject) => {
      const prev = document.querySelector("script[data-plan-map-naver]");
      if (prev) prev.remove();

      const timer = setTimeout(() => {
        _mapsLoadPromise = null;
        reject(new Error("TIMEOUT"));
      }, 20000);

      const s = document.createElement("script");
      s.dataset.planMapNaver = "1";
      s.async = true;
      s.src = `https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=${encodeURIComponent(apiKey)}`;
      s.onload = () => {
        clearTimeout(timer);
        if (naverMapsReady()) resolve();
        else {
          _mapsLoadPromise = null;
          reject(new Error("MAPS_NOT_READY"));
        }
      };
      s.onerror = () => {
        clearTimeout(timer);
        _mapsLoadPromise = null;
        reject(new Error("SCRIPT_LOAD"));
      };
      document.head.appendChild(s);
    });

    return _mapsLoadPromise;
  }

  function refreshMapLayout() {
    if (!_mapInstance) return;
    if (_mapsProvider === "naver" && global.naver?.maps?.Event) {
      global.naver.maps.Event.trigger(_mapInstance, "resize");
      return;
    }
    if (global.google?.maps?.event) {
      global.google.maps.event.trigger(_mapInstance, "resize");
    }
  }

  function clearMapOverlays() {
    _markers.forEach((m) => m.setMap(null));
    _markers = [];
    if (_polyline) {
      _polyline.setMap(null);
      _polyline = null;
    }
  }

  function markerColors() {
    return ["#2B6CB0", "#C73E55", "#D4A853", "#38A169", "#805AD5", "#DD6B20"];
  }

  function materializeNaverStopCoord(stop) {
    if (!stop || (stop.lat != null && stop.lng != null)) return stop;
    const p = stop.place || {};
    const x = p.mapx ?? p.naver_mapx;
    const y = p.mapy ?? p.naver_mapy;
    if (x == null || y == null || !global.naver?.maps?.TransCoord) return stop;
    const nx = Number(x), ny = Number(y);
    if (!Number.isFinite(nx) || !Number.isFinite(ny)) return stop;
    try {
      const nmap = global.naver.maps;
      const latLng = nmap.TransCoord.fromTM128ToLatLng(new nmap.Point(nx, ny));
      const lat = typeof latLng.lat === "function" ? latLng.lat() : latLng.y;
      const lng = typeof latLng.lng === "function" ? latLng.lng() : latLng.x;
      if (_isKoreanCoords(lat, lng)) {
        stop.lat = lat;
        stop.lng = lng;
        stop.place = { ...p, latitude: lat, longitude: lng };
      }
    } catch (_) {
      /* keep geocode fallback */
    }
    return stop;
  }

  function renderMapForDay(day) {
    if (_mapsProvider === "naver") return renderNaverMapForDay(day);
    if (!_mapInstance || !global.google?.maps) return;
    clearMapOverlays();
    const stops = (day.stops || []).filter((s) => s.lat != null && s.lng != null);
    if (!stops.length) {
      showMapStatus("この日の地図表示可能なスポットがありません。", true);
      return;
    }
    showMapStatus("");

    const bounds = new global.google.maps.LatLngBounds();
    const path = [];
    const colors = markerColors();

    stops.forEach((stop, idx) => {
      const pos = { lat: stop.lat, lng: stop.lng };
      path.push(pos);
      bounds.extend(pos);
      const marker = new global.google.maps.Marker({
        position: pos,
        map: _mapInstance,
        label: { text: String(idx + 1), color: "#fff", fontWeight: "700" },
        title: stop.place?.name || stop.label,
        icon: {
          path: global.google.maps.SymbolPath.CIRCLE,
          fillColor: colors[idx % colors.length],
          fillOpacity: 1,
          strokeColor: "#fff",
          strokeWeight: 2,
          scale: 14,
        },
      });
      marker.addListener("click", () => {
        const name = esc(stop.place?.name || stop.label);
        const addr = stop.place?.address ? `<br><small>${esc(stop.place.address)}</small>` : "";
        const link = mapsOpenUrl(stop);
        _infoWindow.setContent(
          `<div class="plan-map-infowin"><strong>${name}</strong>${addr}<br><a href="${esc(link)}" target="_blank" rel="noopener">Google Maps</a></div>`
        );
        _infoWindow.open({ map: _mapInstance, anchor: marker });
      });
      _markers.push(marker);
    });

    if (path.length >= 2) {
      _polyline = new global.google.maps.Polyline({
        path,
        geodesic: true,
        strokeColor: "#2B6CB0",
        strokeOpacity: 0.85,
        strokeWeight: 4,
        icons: [
          {
            icon: {
              path: global.google.maps.SymbolPath.FORWARD_CLOSED_ARROW,
              scale: 3,
              strokeColor: "#2B6CB0",
            },
            offset: "50%",
            repeat: "120px",
          },
        ],
        map: _mapInstance,
      });
    }

    _mapInstance.fitBounds(bounds, { top: 48, right: 48, bottom: 48, left: 48 });
    if (stops.length === 1) _mapInstance.setZoom(14);
    requestAnimationFrame(refreshMapLayout);
    setTimeout(refreshMapLayout, 350);
  }

  function renderNaverMapForDay(day) {
    if (!_mapInstance || !global.naver?.maps) return;
    clearMapOverlays();
    (day.stops || []).forEach(materializeNaverStopCoord);
    const stops = (day.stops || []).filter((s) => s.lat != null && s.lng != null);
    if (!stops.length) {
      showMapStatus("이 날짜에는 지도에 표시할 좌표가 있는 장소가 아직 없습니다.", true);
      return;
    }
    showMapStatus("");

    const nmap = global.naver.maps;
    const bounds = new nmap.LatLngBounds();
    const path = [];
    const colors = markerColors();

    stops.forEach((stop, idx) => {
      const pos = new nmap.LatLng(Number(stop.lat), Number(stop.lng));
      path.push(pos);
      bounds.extend(pos);
      const color = colors[idx % colors.length];
      const marker = new nmap.Marker({
        position: pos,
        map: _mapInstance,
        title: stop.place?.name || stop.label,
        icon: {
          content:
            `<span style="display:flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:50%;background:${color};color:#fff;border:2px solid #fff;font-size:13px;font-weight:700;box-shadow:0 2px 8px rgba(0,0,0,.25)">${idx + 1}</span>`,
          anchor: new nmap.Point(14, 14),
        },
      });
      nmap.Event.addListener(marker, "click", () => {
        const name = esc(stop.place?.name || stop.label);
        const addr = stop.place?.address ? `<br><small>${esc(stop.place.address)}</small>` : "";
        const link = mapsOpenUrl(stop);
        _infoWindow.setContent(
          `<div class="plan-map-infowin"><strong>${name}</strong>${addr}<br><a href="${esc(link)}" target="_blank" rel="noopener">Naver Map</a></div>`
        );
        _infoWindow.open(_mapInstance, marker);
      });
      _markers.push(marker);
    });

    if (path.length >= 2) {
      _polyline = new nmap.Polyline({
        map: _mapInstance,
        path,
        strokeColor: "#2B6CB0",
        strokeOpacity: 0.85,
        strokeWeight: 4,
      });
    }

    _mapInstance.fitBounds(bounds);
    if (stops.length === 1) _mapInstance.setZoom(14);
    requestAnimationFrame(refreshMapLayout);
    setTimeout(refreshMapLayout, 350);
  }

  function renderDayTabs(days) {
    const el = document.getElementById("planDayTabs");
    if (!el) return;
    el.innerHTML = days
      .map(
        (d) =>
          `<button type="button" class="plan-day-tab${d.day === _activeDay ? " active" : ""}" data-day="${d.day}">Day ${d.day}</button>`
      )
      .join("");
    el.querySelectorAll(".plan-day-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        _activeDay = parseInt(btn.dataset.day, 10);
        el.querySelectorAll(".plan-day-tab").forEach((b) =>
          b.classList.toggle("active", +b.dataset.day === _activeDay)
        );
        const day = _planDays.find((x) => x.day === _activeDay);
        if (day) {
          renderMapForDay(day);
          renderDayStops(day);
        }
      });
    });
  }

  function _isSlotLine(line) {
    return /^(?:[-・*①②③④⑤⑥⑦⑧⑨⑩]\s*)?(?:午前|午後|昼食|夕食|夜|朝食|ランチ|ディナー)[:：\s]*$/i.test(String(line || "").trim());
  }

  function _isTextBackedStop(stop) {
    return Number.isInteger(stop?.sourceLineIdx) && !stop?.isAirport && !stop?.isAccommodation;
  }

  function _sourceBlockForStop(lines, stop, dayStart, dayEnd) {
    let idx = Number(stop?.sourceLineIdx);
    if (!Number.isInteger(idx) || idx < dayStart || idx >= dayEnd) return null;
    let start = idx;
    if (MAPS_URL_RE.test(lines[idx] || "") && idx - 1 >= dayStart) {
      const prev = String(lines[idx - 1] || "").trim();
      if (prev && !MAPS_URL_RE.test(prev) && !DAY_HEADER_RE.test(prev)) start = idx - 1;
    }
    while (start - 1 >= dayStart) {
      const prev = String(lines[start - 1] || "").trim();
      if (_isSlotLine(prev) || /^[-・*①②③④⑤⑥⑦⑧⑨⑩]\s*$/.test(prev)) {
        start -= 1;
        continue;
      }
      break;
    }

    let end = idx + 1;
    while (end < dayEnd) {
      const t = String(lines[end] || "").trim();
      if (!t) {
        end++;
        break;
      }
      if (DAY_HEADER_RE.test(t) || MAPS_URL_RE.test(t) || _isSlotLine(t)) break;
      if (/^[-・*①②③④⑤⑥⑦⑧⑨⑩]\s+/.test(t)) break;
      end++;
    }
    return { start, end, lines: lines.slice(start, end) };
  }

  function _daySectionsFromReply(lines, fallbackDayCount) {
    const sections = [];
    let current = null;
    for (let i = 0; i < lines.length; i++) {
      const t = String(lines[i] || "").trim();
      const dayNum = parseDayNumber(t);
      if (
        dayNum !== null &&
        (/日目|Day\s*\d|第\s*\d+\s*日|最終日|帰国日|일째|일차|일\s*차|첫날|최종일|마지막/i.test(t) || /^【\s*\d+/.test(t))
      ) {
        if (current) current.end = i;
        const num = dayNum === -1 ? (fallbackDayCount || sections.length + 1 || 99) : dayNum;
        current = { day: num, start: i, end: lines.length };
        sections.push(current);
      }
    }
    return sections;
  }

  function _editedReplyForCurrentOrder() {
    if (!_originalReply || !_planDays.length) return _originalReply || "";
    const lines = _originalReply.split(/\r?\n/);
    const sections = _daySectionsFromReply(lines, _mapMeta?.days || _mapMeta?.nights + 1);
    if (!sections.length) return _originalReply;

    const out = [];
    let cursor = 0;
    for (const section of sections) {
      out.push(...lines.slice(cursor, section.start));
      const day = _planDays.find((d) => Number(d.day) === Number(section.day));
      if (!day) {
        out.push(...lines.slice(section.start, section.end));
        cursor = section.end;
        continue;
      }

      const blocks = [];
      const covered = new Set();
      for (const stop of day.stops || []) {
        if (!_isTextBackedStop(stop)) continue;
        const block = _sourceBlockForStop(lines, stop, section.start + 1, section.end);
        if (!block) continue;
        const key = `${block.start}:${block.end}`;
        if (blocks.some((b) => b.key === key)) continue;
        blocks.push({ ...block, key });
        for (let i = block.start; i < block.end; i++) covered.add(i);
      }
      if (!blocks.length) {
        out.push(...lines.slice(section.start, section.end));
        cursor = section.end;
        continue;
      }

      const first = Math.min(...blocks.map((b) => b.start));
      const last = Math.max(...blocks.map((b) => b.end));
      out.push(...lines.slice(section.start, first));
      for (const block of blocks) out.push(...block.lines);
      for (let i = first; i < last; i++) {
        if (!covered.has(i)) {
          const t = String(lines[i] || "").trim();
          if (t && !_isSlotLine(t)) out.push(lines[i]);
        }
      }
      out.push(...lines.slice(last, section.end));
      cursor = section.end;
    }
    out.push(...lines.slice(cursor));
    return out.join("\n").replace(/\n{4,}/g, "\n\n\n");
  }

  function _notifyRouteEdited() {
    const active = _planDays.find((d) => d.day === _activeDay) || _planDays[0];
    if (active) {
      renderMapForDay(active);
      renderDayStops(active);
    }
    const editedReply = _editedReplyForCurrentOrder();
    if (typeof _mapMeta?.onReorder === "function") {
      _mapMeta.onReorder({
        days: _planDays,
        activeDay: _activeDay,
        reply: editedReply,
      });
    }
  }

  function _moveStopWithinDay(day, fromIdx, toIdx) {
    const stops = day?.stops || [];
    if (
      !Number.isInteger(fromIdx) ||
      !Number.isInteger(toIdx) ||
      fromIdx === toIdx ||
      fromIdx < 0 ||
      toIdx < 0 ||
      fromIdx >= stops.length ||
      toIdx >= stops.length
    ) return false;
    if (!_isTextBackedStop(stops[fromIdx]) || !_isTextBackedStop(stops[toIdx])) return false;
    const [moved] = stops.splice(fromIdx, 1);
    stops.splice(toIdx, 0, moved);
    return true;
  }

  function _bindStopDragHandlers(el, day) {
    let dragFrom = null;
    el.querySelectorAll(".plan-day-stop[data-draggable='true']").forEach((card) => {
      card.addEventListener("dragstart", (ev) => {
        dragFrom = Number(card.dataset.stopIndex);
        card.classList.add("is-dragging");
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", String(dragFrom));
      });
      card.addEventListener("dragend", () => {
        dragFrom = null;
        el.querySelectorAll(".plan-day-stop").forEach((x) =>
          x.classList.remove("is-dragging", "is-drop-target")
        );
      });
      card.addEventListener("dragover", (ev) => {
        ev.preventDefault();
        card.classList.add("is-drop-target");
        ev.dataTransfer.dropEffect = "move";
      });
      card.addEventListener("dragleave", () => {
        card.classList.remove("is-drop-target");
      });
      card.addEventListener("drop", (ev) => {
        ev.preventDefault();
        const from = Number.isInteger(dragFrom) ? dragFrom : Number(ev.dataTransfer.getData("text/plain"));
        const to = Number(card.dataset.stopIndex);
        if (_moveStopWithinDay(day, from, to)) _notifyRouteEdited();
      });
    });
  }

  function renderDayStops(day) {
    const el = document.getElementById("planDayStops");
    if (!el) return;
    if (!day?.stops?.length) {
      el.innerHTML = `<p class="plan-map-fallback-msg">この日の地図表示用スポットはまだありません。テキスト詳細計画を確認してください。</p>`;
      return;
    }
    const colors = markerColors();
    let mapNum = 0; // 지도 마커 번호 (좌표 있는 stop만 카운트)
    const stopCards = (day.stops || [])
      .map((stop, stopIdx) => {
        const hasCoords = stop.lat != null && stop.lng != null;
        const p = stop.place || {};
        const name = esc(p.name || stop.label);
        const lockable = !stop.isAirport && !stop.isAccommodation;
        const lockKey = stopLockKey(stop, day.day);
        const isLocked = _lockedStops.has(lockKey);
        const lockBtn = lockable
          ? `<button type="button" class="plan-day-stop__lock${isLocked ? " is-locked" : ""}" data-lock-key="${esc(lockKey)}" aria-pressed="${isLocked ? "true" : "false"}">${isLocked ? "固定中" : "固定"}</button>`
          : "";
        const cat = stop.isAirport
          ? "空港"
          : stop.isAccommodation
          ? "宿泊先"
          : esc(p.primary_type || p.types?.[0] || "観光スポット");
        const thumb = stopThumbHtml(stop);
        const mapsUri = esc(mapsOpenUrl(stop));
        const tip = stop.line && !MAPS_URL_RE.test(stop.line) ? esc(stop.line) : "";
        const dragAttrs = `draggable="false" data-draggable="false"`;
        const dragHandle = `<span class="plan-day-stop__drag plan-day-stop__drag--fixed" aria-hidden="true">•</span>`;
        if (hasCoords) {
          mapNum++;
          const color = colors[(mapNum - 1) % colors.length];
          return `<article class="plan-day-stop plan-day-stop--fixed" ${dragAttrs} data-stop-index="${stopIdx}">
            <span class="plan-day-stop__num" style="background:${color}">${mapNum}</span>
            ${dragHandle}
            <a class="plan-day-stop__thumb" href="${mapsUri}" target="_blank" rel="noopener">${thumb}</a>
            <div class="plan-day-stop__body">
              <div class="plan-day-stop__head">
                <h4 class="plan-day-stop__name">${name}</h4>
                ${lockBtn}
              </div>
              <p class="plan-day-stop__meta">${cat}</p>
              ${tip ? `<p class="plan-day-stop__tip"><span class="plan-day-stop__rec">おすすめ</span> ${tip}</p>` : ""}
            </div>
          </article>`;
        } else {
          // 좌표 없는 stop — 지도에 표시 안 됨을 시각적으로 구분
          return `<article class="plan-day-stop plan-day-stop--no-map plan-day-stop--fixed" ${dragAttrs} data-stop-index="${stopIdx}">
            <span class="plan-day-stop__num" style="background:#bbb;font-size:.7rem">—</span>
            ${dragHandle}
            <a class="plan-day-stop__thumb" href="${mapsUri}" target="_blank" rel="noopener">${thumb}</a>
            <div class="plan-day-stop__body">
              <div class="plan-day-stop__head">
                <h4 class="plan-day-stop__name">${name}</h4>
                ${lockBtn}
              </div>
              <p class="plan-day-stop__meta" style="color:#2b6cb0">地図で開く</p>
            </div>
          </article>`;
        }
      })
      .join("");
    el.innerHTML = stopCards;
    el.querySelectorAll(".plan-day-stop__lock").forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.dataset.lockKey || "";
        const stop = (day.stops || []).find((s) => stopLockKey(s, day.day) === key);
        if (!stop) return;
        if (_lockedStops.has(key)) {
          _lockedStops.delete(key);
        } else {
          _lockedStops.set(key, stopLockPayload(stop, day.day));
        }
        renderDayStops(day);
      });
    });
  }

  async function geocodeMissingStops(days) {
    const seenQueries = new Set();

    function queriesForStop(stop) {
      const raw = stop.isAccommodation
        ? (stop.place?.address || stop.line || stop.label)
        : (stop.place?.address || stop.place?.name || stop.label);
      const base = String(raw || "").trim();
      if (!base || base.length < 2) return [];
      const noParen = base.replace(/\([^)]*\)/g, " ").replace(/\s+/g, " ").trim();
      const spacedRoadQuery = noParen.replace(/([\uac00-\ud7a3])(\d)/g, "$1 $2");
      return [base, noParen, spacedRoadQuery, `${noParen} South Korea`, `South Korea ${noParen}`]
        .map((q) => q.trim())
        .filter((q, idx, arr) => q && arr.indexOf(q) === idx);
      const spacedRoad = noParen.replace(/([가-힣])(\d)/g, "$1 $2");
      return [base, noParen, spacedRoad, `${noParen} 대한민국`, `대한민국 ${noParen}`]
        .map((q) => q.trim())
        .filter((q, idx, arr) => q && arr.indexOf(q) === idx);
    }

    async function geocodeOne(query) {
      if (seenQueries.has(query)) return null;
      seenQueries.add(query);
      const res = await fetch(
        `/api/places/geocode/?q=${encodeURIComponent(query)}&limit=1`
      );
      const body = await res.json();
      return body.places?.[0] || null;
    }

    for (const day of days) {
      for (const stop of day.stops) {
        if (stop.lat != null) continue;
        const q = stop.isAccommodation
          ? (stop.place?.address || stop.line || stop.label)
          : (stop.place?.address || stop.place?.name || stop.label);
        if (!q || q.length < 2) continue;
        for (const candidate of queriesForStop(stop)) {
          try {
            const p = await geocodeOne(candidate);
            if (p?.latitude == null) continue;
            const lat = Number(p.latitude), lng = Number(p.longitude);
            if (!_isKoreanCoords(lat, lng)) continue;
            stop.lat = lat;
            stop.lng = lng;
            if (stop.isAccommodation) {
              stop.place = {
                ...stop.place,
                address: stop.place?.address || p.address || candidate,
                latitude: lat,
                longitude: lng,
                google_maps_uri: p.maps_url || stop.url || "",
                maps_url: p.maps_url || stop.url || "",
              };
            } else {
              stop.place = { ...stop.place, ...p, google_maps_uri: p.maps_url || stop.url };
            }
            break;
          } catch (_) {
            /* try next candidate */
          }
        }
        if (stop.lat != null) continue;
        try {
          const res = await fetch(
            `/api/places/search/?q=${encodeURIComponent(q + " 대한민국")}&limit=1&type=general`
          );
          const body = await res.json();
          const p = body.places?.[0];
          if (p?.latitude != null) {
            const lat = Number(p.latitude), lng = Number(p.longitude);
            if (_isKoreanCoords(lat, lng)) {
              stop.lat = lat;
              stop.lng = lng;
              if (stop.isAccommodation) {
                stop.place = {
                  ...stop.place,
                  latitude: lat,
                  longitude: lng,
                  google_maps_uri: stop.url || "",
                };
              } else {
                stop.place = { ...stop.place, ...p, google_maps_uri: p.maps_url || stop.url };
              }
            }
            // 한국 영역 밖 좌표(일본 등)는 null 유지
          }
        } catch (_) {
          /* skip */
        }
      }
    }
  }

  function authErrorHtml(cfg) {
    const host = esc(global.location.origin);
    const src = cfg?.source ? `（${esc(cfg.source)}）` : "";
    return (
      "<p><strong>地図を表示できません（APIキー認証エラー）</strong></p>" +
      "<ul style='margin:.5rem 0 0 1rem;padding:0;font-size:.82rem;line-height:1.5'>" +
      "<li>Google Cloud → <b>APIとサービス → 認証情報</b> → ブラウザ用キー</li>" +
      "<li><b>アプリケーションの制限</b>: <b>HTTPリファラー</b>（IPアドレス制限は不可）</li>" +
      `<li>許可例: <code>${host}/*</code> 、 <code>http://localhost:8000/*</code></li>` +
      "<li><b>APIの制限</b>: Maps JavaScript API を含める</li>" +
      "<li>Vertex / Gemini の「サービスアカウントにキーをバインド」は<b>ブラウザ地図には不要</b></li>" +
      "<li>課金（Billing）が有効か確認</li>" +
      "</ul>" +
      `<p style='font-size:.78rem;margin-top:.5rem'>キー出所${src} — 開発者ツール(F12)→Console の Google Maps エラーも確認してください。</p>`
    );
  }

  async function initMap(canvas, cfg) {
    const apiKey = cfg.api_key;
    showMapStatus("地図を読み込み中…");
    _mapsProvider = cfg.provider === "naver" ? "naver" : "google";
    if (_mapsProvider === "naver") await loadNaverMaps(apiKey);
    else await loadGoogleMaps(apiKey);

    if (_mapsProvider === "naver" && !_mapInstance && canvas) {
      _mapInstance = new global.naver.maps.Map(canvas, {
        center: new global.naver.maps.LatLng(37.5665, 126.978),
        zoom: 10,
        scaleControl: false,
        logoControl: true,
        mapDataControl: false,
        zoomControl: true,
      });
      _infoWindow = new global.naver.maps.InfoWindow();
    } else if (!_mapInstance && canvas) {
      _mapInstance = new global.google.maps.Map(canvas, {
        center: { lat: 37.5665, lng: 126.978 },
        zoom: 10,
        mapTypeControl: false,
        streetViewControl: false,
        fullscreenControl: true,
      });
      _infoWindow = new global.google.maps.InfoWindow();
    }

    const active = _planDays.find((d) => d.day === _activeDay) || _planDays[0];
    renderMapForDay(active);
    if (_mapsProvider === "naver" && active) renderDayStops(active);
    setTimeout(refreshMapLayout, 500);
    setTimeout(refreshMapLayout, 1200);
  }

  async function render(reply, placeIndex, meta) {
    const shell = document.getElementById("planMapShell");
    if (!shell) return;

    _mapMeta = meta || {};
    _originalReply = String(reply || "");
    const fullPlaceIndex = meta?.placeIndex || { byUrl: placeIndex || {} };
    const allowedStopKeys = _allowedStopKeysFromReply(reply, fullPlaceIndex);
    _planDays = parsePlanDays(reply, fullPlaceIndex, meta?.days || meta?.nights + 1);

    // 일본 지명이 포함된 LLM 환각 stop 제거 (신오쿠보, 신주쿠 등)
    _planDays.forEach((d) => {
      d.stops = d.stops.filter(
        (s) => !_isJpLocation(s.label) && _stopAllowedByReply(s, allowedStopKeys)
      );
    });
    _planDays = normalizePlanDays(_planDays, meta?.days || meta?.nights + 1);

    addRouteAnchors(_planDays, meta);
    _planDays = normalizePlanDays(_planDays, meta?.days || meta?.nights + 1);

    if (!_planDays.length) {
      shell.style.display = "none";
      showMapStatus("");
      return;
    }

    await geocodeMissingStops(_planDays);

    const hasGeo = _planDays.some((d) => d.stops.some((s) => s.lat != null));
    if (!hasGeo) {
      shell.style.display = "none";
      showMapStatus("");
      return;
    }

    shell.style.display = "block";
    const titleEl = document.getElementById("planMapTitle");
    const subEl = document.getElementById("planMapSubtitle");
    if (titleEl && meta?.title) titleEl.textContent = meta.title;
    if (subEl) subEl.textContent = meta?.subtitle || "マップの番号順にスポットを巡るルートです。";

    _activeDay = _planDays[0].day;
    renderDayTabs(_planDays);
    renderDayStops(_planDays[0]);

    const cfg = await fetchMapsConfig();
    const canvas = document.getElementById("planMapCanvas");
    const fallback = document.getElementById("planMapFallback");

    if (!cfg.enabled || !cfg.api_key) {
      if (canvas) canvas.style.display = "none";
      showMapStatus("");
      if (fallback) {
        fallback.style.display = "block";
        const pts = _planDays
          .flatMap((d) => d.stops)
          .filter((s) => s.lat != null)
          .map((s) => `${s.lat},${s.lng}`)
          .join("/");
        const naver = pts
          ? `<a href="https://map.naver.com/" target="_blank" rel="noopener">ネイバーマップでルート</a> · <a href="https://map.kakao.com/" target="_blank" rel="noopener">カカオマップ</a>`
          : "";
        fallback.innerHTML = `<p class="plan-map-fallback-msg">地図APIキー未設定のためルート地図は表示しません。${naver}${pts ? `<br><small>（参考）<a href="https://www.google.com/maps/dir/${pts}" target="_blank" rel="noopener">Google Maps</a></small>` : ""}</p>`;
      }
      return;
    }

    _mapsApiKey = cfg.api_key;
    if (fallback) fallback.style.display = "none";
    if (canvas) {
      canvas.style.display = "block";
      canvas.innerHTML = "";
    }

    try {
      await initMap(canvas, cfg);
    } catch (e) {
      console.warn("Plan map init failed", e);
      _mapInstance = null;
      _mapsLoadPromise = null;
      if (canvas) canvas.style.display = "none";
      if (fallback) fallback.style.display = "block";
      const err = String(e?.message || e);
      if (err === "AUTH_FAILURE") {
        showMapStatus(authErrorHtml(cfg), true);
      } else {
        showMapStatus(
          `<p><strong>地図の読み込みに失敗しました</strong>（${esc(err)}）</p>` +
            "<p style='font-size:.82rem'>F12 → Console のエラーを確認してください。</p>",
          true
        );
      }
    }
  }

  function destroy() {
    clearMapOverlays();
    _planDays = [];
    _mapInstance = null;
    _infoWindow = null;
    _mapsLoadPromise = null;
    showMapStatus("");
    const shell = document.getElementById("planMapShell");
    if (shell) shell.style.display = "none";
    const canvas = document.getElementById("planMapCanvas");
    if (canvas) canvas.innerHTML = "";
  }

  const root = global || globalThis || window;
  if (root) {
    root.PlanMapView = {
      render,
      destroy,
      refreshMapLayout,
      buildPlaceIndex,
      parsePlanDays,
      getLockedItems,
      clearLocks,
    };
  }
})(typeof window !== "undefined" ? window : globalThis);
