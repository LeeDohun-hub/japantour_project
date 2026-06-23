/**
 * 旅行プラン — Naver Map + Dayタブ + スポットカード（Triple風）
 */
(function (global) {
  "use strict";

  const MAPS_URL_RE = /^https?:\/\/(?:maps\.google\.com|www\.google\.com\/maps|goo\.gl\/maps|maps\.app\.goo\.gl|map\.naver\.com)\/\S+/i;
  const MARKDOWN_MAPS_URL_RE = /\[[^\]]+\]\((https?:\/\/(?:maps\.google\.com|www\.google\.com\/maps|goo\.gl\/maps|maps\.app\.goo\.gl|map\.naver\.com)\/[^)\s]+)\)/i;
  const DAY_HEADER_RE =
    /^(?:#{1,3}\s*)?(?:【\s*)?(?:Day\s*)?(\d+)\s*日目|^(?:#{1,3}\s*)?第\s*(\d+)\s*日|^(?:#{1,3}\s*)?Day\s*(\d+)\b|最終日|帰国日|最終\s*日|^첫날|^(?:둘째|두\s*번째|셋째|세\s*번째|넷째|네\s*번째|다섯째|다섯\s*번째|여섯째|여섯\s*번째)\s*날(?=$|\s|[:：\-])|^(\d+)\s*(?:일째|일차|일\s*차)|^최종일|^마지막\s*날/i;
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
  let _routeRenderSeq = 0;
  let _routeDisplayMode = "shortest"; // "shortest" | "off"
  const _lockedStops = new Map();
  const _drivingRouteCache = new Map();
  const _transitRouteCache = new Map();
  const _naverResolveCache = new Map();

  function esc(s) {
    return String(s || "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  function _koTokens(s) {
    return String(s || "").match(/[가-힣]{2,}/g) || [];
  }

  function _compactText(s) {
    return String(s || "").toLowerCase().replace(/[^0-9a-z가-힣ぁ-んァ-ヶ一-龥]+/gi, "");
  }

  function _placeNameMatchesLabel(placeName, label) {
    const pn = _compactText(placeName);
    const ln = _compactText(label);
    if (!pn || !ln) return true;
    if (pn === ln || pn.includes(ln) || ln.includes(pn)) return true;
    const pTokens = new Set(_koTokens(placeName));
    const lTokens = _koTokens(label);
    return lTokens.some((t) => pTokens.has(t));
  }

  function _stopSearchName(stop) {
    const label = String(stop?.label || "").replace(/^[①②③④⑤⑥⑦⑧⑨⑩]\s*/, "").trim();
    if (label) return label;
    return String(stop?.place?.name || "").trim();
  }

  function _stopSearchUrl(stop) {
    const q = _stopSearchName(stop);
    return q ? `https://map.naver.com/p/search/${encodeURIComponent(q)}` : "#";
  }

  function _landmarkSearchAliases(name) {
    const value = String(name || "").replace(/\s+/g, "").trim();
    const out = [];
    const parkStripped = value.replace(/(?:국립|도립|군립|시립|자연|생태|광역시립)공원$/, "");
    if (parkStripped && parkStripped !== value && parkStripped.length >= 2) out.push(parkStripped);
    const landmarkSuffixes = ["언덕", "고개", "마을", "거리", "골목", "계단", "폭포", "호수", "계곡", "봉", "령", "재", "협곡", "절벽"];
    if (/^[가-힣]{6,}$/.test(value)) {
      const stripped2 = value.slice(2);
      if (stripped2.length >= 3 && landmarkSuffixes.some((s) => stripped2.endsWith(s))) out.push(stripped2);
    }
    return out.filter((q, idx, arr) => q && arr.indexOf(q) === idx);
  }

  function _isFoodLikeText(text) {
    return /미분당|육통령|육회|연어|홍콩반점|반점|짜장|짬뽕|중화|중식|고기|갈비|삼겹|국밥|순대|칼국수|쌀국수|라멘|라면|냉면|곰탕|설렁탕|해장|찌개|탕|비빔|곱창|막창|횟집|식당|맛집|레스토랑|고깃집|고기집|포차|술집|호프/i
      .test(String(text || ""));
  }

  function _isCafeLikeText(text) {
    return /카페|커피|베이커리|케이크|디저트|브런치|베이글|빵집|빵/i
      .test(String(text || ""));
  }

  function _nearbyAreaTokens(area) {
    const a = String(area || "").trim();
    if (!a) return [];
    const groups = {
      "홍대": ["홍대", "마포", "상수", "합정", "연남", "망원", "신촌", "서대문"],
      "弘大": ["홍대", "마포", "상수", "합정", "연남", "망원", "신촌", "서대문"],
      "hongdae": ["홍대", "마포", "상수", "합정", "연남", "망원", "신촌", "서대문"],
      "신촌": ["신촌", "서대문", "홍대", "마포", "연세로", "이대"],
    };
    return groups[a] || [a];
  }

  function _extractMapsUrl(line) {
    const t = String(line || "").trim();
    const md = t.match(MARKDOWN_MAPS_URL_RE);
    if (md) return md[1];
    const raw = t.match(/https?:\/\/(?:maps\.google\.com|www\.google\.com\/maps|goo\.gl\/maps|maps\.app\.goo\.gl|map\.naver\.com)\/\S+/i);
    return raw ? raw[0].replace(/[)\]}>、。.,]+$/, "") : "";
  }

  function _isMapsUrlLine(line) {
    return !!_extractMapsUrl(line);
  }

  function _isAnyUrlLine(line) {
    return /https?:\/\//i.test(String(line || ""));
  }

  function _knownKoreanSearchName(name) {
    const compact = _compactText(name);
    // 특수 케이스 (긴 정식명)
    if (/弘益.*現代美術館|홍익.*현대미술관/i.test(compact)) return "홍익대학교 현대미술관";
    if (/dynamicmaze|다이나믹메이즈/i.test(compact)) return "다이나믹메이즈 서울 인사동";
    if (/명동성당|명동대성당|myeongdong.*cathedral/i.test(compact)) return "천주교 서울대교구 주교좌명동대성당";
    if (/명동.*메인|명동.*스트리트|meongdong.*main|meongdong.*street/i.test(compact)) return "명동거리";
    if (/덕수궁.*돌담|徳寿宮.*石垣|石垣道/i.test(compact)) return "덕수궁 돌담길";
    // 일본어 한자 → 한국어 (광범위 매핑)
    if (/ソウルN?タワー|Nタワー|南山.*タワー|남산.*타워/.test(compact)) return "남산서울타워";
    if (/仁寺洞通り|인사동통り/.test(compact)) return "인사동길";
    if (/仁寺洞/.test(compact)) return "인사동길";
    if (/サムジキル/.test(compact)) return "쌈지길";
    if (/三清洞通り|三清洞/.test(compact)) return "삼청동 카페거리";
    if (/北村韓屋村|北村/.test(compact)) return "북촌한옥마을";
    if (/益善洞/.test(compact)) return "익선동 한옥거리";
    if (/景福宮/.test(compact)) return "경복궁";
    if (/昌徳宮|창덕궁/.test(compact)) return "창덕궁";
    if (/徳寿宮/.test(compact)) return "덕수궁";
    if (/明洞通り|明洞/.test(compact)) return "명동거리";
    if (/光化門広場|光化門/.test(compact)) return "광화문광장";
    if (/清渓川/.test(compact)) return "청계천";
    if (/東大門.*デザイン|東大門.*Design|DDP/.test(compact)) return "동대문디자인플라자";
    if (/東大門市場|東大門/.test(compact)) return "동대문시장";
    if (/南大門市場|南大門/.test(compact)) return "남대문시장";
    if (/南山公園|南山.*공원/.test(compact)) return "남산공원";
    if (/弘大入口|弘大/.test(compact)) return "홍대입구역";
    if (/梨泰院/.test(compact)) return "이태원";
    if (/江南/.test(compact)) return "강남역";
    if (/漢江.*公園|漢江/.test(compact)) return "한강공원";
    if (/ロッテワールドタワー|롯데월드타워/.test(compact)) return "롯데월드타워";
    if (/COEX|コエックス/.test(compact)) return "코엑스";
    if (/東廟.*市場|東廟/.test(compact)) return "동묘 벼룩시장";
    if (/ソウルランタン|ソウル灯籠|등불축제|연등/.test(compact)) return "서울빛초롱축제";
    if (/ソウル旧ベルギー|旧ベルギー|서울시립미술관/.test(compact)) return "서울시립미술관";
    return "";
  }

  async function _resolveNaverCanonical(rawName) {
    if (!rawName || rawName.length < 2) return null;
    if (_naverResolveCache.has(rawName)) return _naverResolveCache.get(rawName);
    const pending = fetch(`/api/naver-resolve/?q=${encodeURIComponent(rawName)}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        const result = data?.canonical ? data : null;
        _naverResolveCache.set(rawName, result);
        return result;
      })
      .catch(() => {
        _naverResolveCache.set(rawName, null);
        return null;
      });
    // 이미 promise를 캐시에 넣어 중복 요청 방지
    _naverResolveCache.set(rawName, pending);
    return pending;
  }

  function _naverCanonicalUrl(resolved) {
    const canonical = resolved?.canonical;
    if (!canonical) return null;
    const lat = resolved.lat;
    const lng = resolved.lng;
    if (lat && lng && lat > 10 && lng > 100) {
      return `https://map.naver.com/p/search/${encodeURIComponent(canonical)}?c=${lng},${lat},16,0,0,0,dh`;
    }
    return `https://map.naver.com/p/search/${encodeURIComponent(canonical)}`;
  }

  async function _prefetchNaverResolveForEl(containerEl, day) {
    const links = containerEl.querySelectorAll("a[data-raw-name]");
    let mapNeedsRefresh = false;
    const resolvePromises = [];
    for (const link of links) {
      const rawName = link.dataset.rawName;
      if (!rawName) continue;
      // 일본어 이름 → 한국어 변환 우선순위:
      // 1) 괄호 안 한국어 "徳寿宮石垣道（덕수궁 돌담길）"
      // 2) _knownKoreanSearchName 매핑 "仁寺洞通り" → "인사동길"
      // 3) rawName 그대로 (이미 한국어거나 매핑 없음)
      const parenKo = rawName.match(/[（(]([가-힣][가-힣\s·]{0,30})[）)]/);
      const knownKo = !parenKo ? _knownKoreanSearchName(rawName) : "";
      const resolveQuery = parenKo ? parenKo[1].trim() : (knownKo || rawName);
      const p = _resolveNaverCanonical(resolveQuery).then((resolved) => {
        const url = _naverCanonicalUrl(resolved);
        if (url && link.dataset.rawName === rawName) {
          link.href = url;
        }
        // resolve 결과 좌표로 stop lat/lng 업데이트 (map pin 복원)
        const lat = resolved?.lat;
        const lng = resolved?.lng;
        if (lat && lng && lat > 10 && lng > 100 && day?.stops) {
          const article = link.closest("[data-stop-index]");
          const stopIdx = article ? parseInt(article.dataset.stopIndex, 10) : -1;
          const stop = stopIdx >= 0 ? day.stops[stopIdx] : null;
          if (stop && stop.lat == null) {
            stop.lat = lat;
            stop.lng = lng;
            mapNeedsRefresh = true;
          }
        }
      });
      resolvePromises.push(p);
    }
    // 모든 resolve 완료 후 한 번만 지도 재렌더링
    if (resolvePromises.length) {
      Promise.all(resolvePromises).then(() => {
        if (mapNeedsRefresh && day && day.day === _activeDay) {
          renderMapForDay(day);
        }
      });
    }
  }

  function mapsOpenUrl(stop) {
    const p = stop?.place || {};
    const label = _stopSearchName(stop);
    const knownSearch = _knownKoreanSearchName(p.name || label);
    if (knownSearch) {
      return `https://map.naver.com/p/search/${encodeURIComponent(knownSearch)}`;
    }
    if (p.name && /[가-힣]/.test(label) && !_placeNameMatchesLabel(p.name, label)) {
      return _stopSearchUrl(stop);
    }
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
    const rawUrl = p.maps_url || p.google_maps_uri || stop?.url || "";
    if (/map\.naver\.com/i.test(rawUrl)) {
      return rawUrl;
    }
    if (stop?.lat != null && stop?.lng != null) {
      const q = encodeURIComponent(p.name || stop?.label || `${stop.lat},${stop.lng}`);
      return `https://map.naver.com/p/search/${q}?c=${stop.lng},${stop.lat},16,0,0,0,dh`;
    }
    const q = p.name || stop?.label;
    return q ? `https://map.naver.com/p/search/${encodeURIComponent(q)}` : "#";
  }

  function stopPhotoUrl(stop) {
    const p = stop?.place || {};
    if (stop?.isAirport) return "";
    if (p.photo_name) return `/api/photo/?name=${encodeURIComponent(p.photo_name)}`;
    const stopLabel = String(stop?.label || "").trim();
    const placeNameNorm = (p.name || "").replace(/\s+/g, "").toLowerCase();
    const labelNorm = stopLabel.replace(/\s+/g, "").toLowerCase();
    // Only trust p.photo_url when the place name matches the stop label —
    // mismatched Naver results cause the wrong place's photo to appear.
    const nameMatchesLabel = !placeNameNorm || !labelNorm ||
      placeNameNorm === labelNorm ||
      labelNorm.startsWith(placeNameNorm) ||
      placeNameNorm.startsWith(labelNorm);
    if (nameMatchesLabel && (p.photo_url || p.naver_photo_url)) return p.photo_url || p.naver_photo_url;
    // Build photo URL from the stop label, preferring Korean p.name when the
    // label is a generic Japanese activity description (e.g. "カフェ巡り") with
    // no Korean — Naver photo search fails on Japanese text.
    const processedLabel = stopLabel.replace(/^[①②③④⑤⑥⑦⑧⑨⑩]\s*/, "").replace(/^[-・*]\s*/, "").trim();
    const labelHasKorean = /[가-힣]/.test(processedLabel);
    const nameHasKorean = /[가-힣]/.test(p.name || "");
    const photoQuery = (!labelHasKorean && nameHasKorean ? String(p.name) : processedLabel)
      || p.address || String(p.name || "").trim();
    if (!photoQuery) return "";
    const coord = stop?.lat != null && stop?.lng != null
      ? `&lat=${encodeURIComponent(stop.lat)}&lng=${encodeURIComponent(stop.lng)}`
      : "";
    const mapUrl = p.name && /[가-힣]/.test(stopLabel) && !_placeNameMatchesLabel(p.name, stopLabel)
      ? (stop?.url || "")
      : (p.maps_url || p.google_maps_uri || stop?.url || "");
    if (/map\.naver\.com/i.test(mapUrl)) {
      return `/api/naver-photo/?url=${encodeURIComponent(mapUrl)}&q=${encodeURIComponent(photoQuery)}${coord}&image_fallback=1`;
    }
    return `/api/naver-photo/?q=${encodeURIComponent(photoQuery)}${coord}&image_fallback=1`;
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

  const _NMAP_APPNAME = "japantourtravel.com";

  function _naverRouteWebUrl(from, to, mode = "transit") {
    const routeMode = mode === "car" ? "car" : mode === "walk" ? "walk" : mode === "bicycle" ? "bicycle" : "transit";
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
      `${to.lng},${to.lat},${toName},PLACE_POI/-/${routeMode}` +
      `?c=${midLng},${midLat},10,0,0,0,dh`
    );
  }

  function _naverRouteNmapUrl(from, to, mode = "transit") {
    // nmap:// URL Scheme — 네이버 지도 앱으로 직접 연결 (모바일 앱 설치 시)
    if (!_hasRouteCoords(from) || !_hasRouteCoords(to)) return null;
    const actionMap = { transit: "public", car: "car", walk: "walk", bicycle: "bicycle" };
    const action = actionMap[mode] || "public";
    const sname = encodeURIComponent(_routeStopName(from, "출발지"));
    const dname = encodeURIComponent(_routeStopName(to, "도착지"));
    return (
      `nmap://route/${action}` +
      `?slat=${from.lat}&slng=${from.lng}&sname=${sname}` +
      `&dlat=${to.lat}&dlng=${to.lng}&dname=${dname}` +
      `&appname=${_NMAP_APPNAME}`
    );
  }

  function _naverRouteUrl(from, to, mode = "transit") {
    // 모바일: nmap:// 앱 스킴 우선, 데스크탑/앱 미설치: 웹 URL 폴백
    return _naverRouteNmapUrl(from, to, mode) || _naverRouteWebUrl(from, to, mode);
  }

  function _airportTransferRouteModes() {
    const transport = Array.isArray(_mapMeta?.transport) ? _mapMeta.transport : [];
    const selected = new Set(transport.map((t) => String(t || "").toLowerCase()));
    const hasAny = (...keys) => keys.some((k) => selected.has(k));
    const modes = [];
    if (hasAny("rail", "arex", "subway", "bus")) {
      const transitLabel = hasAny("bus") && !hasAny("rail", "arex", "subway")
        ? "Naverバス経路"
        : hasAny("rail", "arex", "subway") && !hasAny("bus")
          ? "Naver鉄道経路"
          : "Naver公共交通";
      modes.push({
        mode: "transit",
        label: transitLabel,
      });
    }
    if (hasAny("taxi", "rental")) {
      modes.push({
        mode: "car",
        label: hasAny("rental") ? "Naver車経路" : "Naverタクシー経路",
      });
    }
    if (!modes.length) modes.push({ mode: "transit", label: "Naver経路" });
    return modes;
  }

  function _selectedTransportHasCarRoute() {
    return _routeDisplayMode === "shortest";
  }

  function _selectedTransportHasTransitRoute() {
    return false;
  }

  function _selectedTransportIsWalk() {
    return _routeDisplayMode === "off";
  }


  function _fmtRouteDistance(meters) {
    const n = Number(meters);
    if (!Number.isFinite(n) || n <= 0) return "";
    return n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}km` : `${Math.round(n)}m`;
  }

  function _fmtRouteDuration(ms) {
    const n = Number(ms);
    if (!Number.isFinite(n) || n <= 0) return "";
    const min = Math.max(1, Math.round(n / 60000));
    if (min < 60) return `約${min}分`;
    const h = Math.floor(min / 60);
    const rest = min % 60;
    return rest ? `約${h}時間${rest}分` : `約${h}時間`;
  }

  function _fmtKrw(value) {
    const n = Number(value);
    if (!Number.isFinite(n) || n <= 0) return "";
    return `${Math.round(n).toLocaleString("ko-KR")}ウォン`;
  }

  function _airportDrivingRouteMeta(day) {
    const summary = day?._airportDrivingRoute?.summary || null;
    if (!summary || !_selectedTransportHasCarRoute()) return "";
    const parts = [
      _fmtRouteDuration(summary.duration),
      _fmtRouteDistance(summary.distance),
      summary.taxiFare ? `タクシー目安 ${_fmtKrw(summary.taxiFare)}` : "",
    ].filter(Boolean);
    return parts.length ? parts.join(" ・ ") : "";
  }

  function _drivingRouteCacheKey(from, to) {
    return [
      Number(from.lng).toFixed(5),
      Number(from.lat).toFixed(5),
      Number(to.lng).toFixed(5),
      Number(to.lat).toFixed(5),
    ].join(",");
  }

  async function _fetchAirportDrivingRoute(segment) {
    const from = segment?.from;
    const to = segment?.to;
    if (!_selectedTransportHasCarRoute() || !_hasRouteCoords(from) || !_hasRouteCoords(to)) return null;
    const key = _drivingRouteCacheKey(from, to);
    if (_drivingRouteCache.has(key)) return _drivingRouteCache.get(key);
    const qs = new URLSearchParams({
      start_lng: String(from.lng),
      start_lat: String(from.lat),
      goal_lng: String(to.lng),
      goal_lat: String(to.lat),
      option: "traoptimal",
      lang: "ja",
    });
    try {
      const res = await fetch(`/api/maps/driving-route/?${qs}`);
      const data = await res.json();
      const route = res.ok && data?.ok && Array.isArray(data.route?.path) ? data.route : null;
      _drivingRouteCache.set(key, route);
      return route;
    } catch (err) {
      console.warn("airport driving route failed", err);
      _drivingRouteCache.set(key, null);
      return null;
    }
  }

  async function _fetchTransitRoute(from, to) {
    if (!_hasRouteCoords(from) || !_hasRouteCoords(to)) return null;
    const key = [
      Number(from.lng).toFixed(4), Number(from.lat).toFixed(4),
      Number(to.lng).toFixed(4), Number(to.lat).toFixed(4),
    ].join(",");
    if (_transitRouteCache.has(key)) return _transitRouteCache.get(key);
    const qs = new URLSearchParams({
      start_lat: String(from.lat), start_lng: String(from.lng),
      goal_lat: String(to.lat),   goal_lng: String(to.lng),
    });
    try {
      const res = await fetch(`/api/maps/transit-route/?${qs}`);
      const data = await res.json();
      const route = res.ok && data?.ok && Array.isArray(data.route?.path) ? data.route : null;
      _transitRouteCache.set(key, route);
      return route;
    } catch (err) {
      console.warn("transit route failed", err);
      _transitRouteCache.set(key, null);
      return null;
    }
  }

  // Fetch Naver Directions 5 route for all daily tourist stops (start + up to 5 waypoints + goal).
  // Returns stitched path [{lat, lng}, ...] or null on failure.
  async function _fetchDayStopsRoute(stops) {
    const geo = stops.filter((s) => s.lat != null && s.lng != null);
    if (geo.length < 2) return null;
    const start = geo[0];
    const goal = geo[geo.length - 1];
    // Up to 5 intermediate waypoints (Direction 5 limit)
    const viaStops = geo.slice(1, geo.length - 1).slice(0, 5);
    const cacheKey = geo.map((s) => `${Number(s.lat).toFixed(4)},${Number(s.lng).toFixed(4)}`).join("|");
    if (_drivingRouteCache.has(cacheKey)) return _drivingRouteCache.get(cacheKey);
    const qs = new URLSearchParams({
      start_lng: String(start.lng),
      start_lat: String(start.lat),
      goal_lng: String(goal.lng),
      goal_lat: String(goal.lat),
      option: "traoptimal",
      lang: "ja",
    });
    if (viaStops.length) {
      qs.set("waypoints", viaStops.map((s) => `${s.lng},${s.lat}`).join("|"));
    }
    try {
      const res = await fetch(`/api/maps/driving-route/?${qs}`);
      const data = await res.json();
      if (!res.ok || !data?.ok) {
        const err = data?.error || `HTTP ${res.status}`;
        console.warn("day stops route failed:", err, data);
        _drivingRouteCache.set(cacheKey, null);
        return null;
      }
      const path = Array.isArray(data.route?.path) ? data.route.path : null;
      _drivingRouteCache.set(cacheKey, path);
      return path;
    } catch (err) {
      console.warn("day stops route failed", err);
      _drivingRouteCache.set(cacheKey, null);
      return null;
    }
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
    const kakaoUrl = esc(_kakaoRouteUrl(from, to));
    const drivingMeta = _airportDrivingRouteMeta(day);
    const naverActions = _airportTransferRouteModes()
      .map(({ mode, label }) => {
        const nmapUrl = _naverRouteNmapUrl(from, to, mode);
        const webUrl = _naverRouteWebUrl(from, to, mode);
        // href = 웹 URL (데스크탑/앱 미설치 폴백), data-nmap = 앱 스킴 (모바일 앱)
        return (
          `<a href="${esc(webUrl)}" target="_blank" rel="noopener"` +
          (nmapUrl ? ` data-nmap="${esc(nmapUrl)}"` : "") +
          ` class="plan-naver-route-btn">${esc(label)}</a>`
        );
      })
      .join("");
    return `<article class="plan-transfer-card">
      <div class="plan-transfer-card__icon">⇄</div>
      <div class="plan-transfer-card__body">
        <div class="plan-transfer-card__title">${title}</div>
        <div class="plan-transfer-card__route">
          <span>${esc(_routeStopName(from, "出発地"))}</span>
          <span class="plan-transfer-card__arrow">→</span>
          <span>${esc(_routeStopName(to, "到着地"))}</span>
        </div>
        ${drivingMeta ? `<div class="plan-transfer-card__meta">${esc(drivingMeta)}</div>` : ""}
      </div>
      <div class="plan-transfer-card__actions">
        ${naverActions}
        <a href="${kakaoUrl}" target="_blank" rel="noopener">Kakao経路</a>
      </div>
    </article>`;
  }

  function _longDistanceDepartureDay() {
    const regionCities = String(_mapMeta.regionCities || _mapMeta.region_cities || "").trim();
    if (!regionCities) return null;
    const accAddr = String(_mapMeta.accommodation?.address || _mapMeta.accommodation?.region || "").toLowerCase();
    const cities = regionCities.split(/[,·\/\s]+/).filter((s) => s.length >= 2).map((s) => s.toLowerCase());
    if (cities.some((c) => accAddr.includes(c))) return null;
    for (let i = 0; i < _planDays.length - 1; i++) {
      const seg = _airportAccommodationSegment(_planDays[i]);
      if (seg?.from?.stop?.isAirport) {
        const next = _planDays[i + 1];
        if (next && !_airportAccommodationSegment(next)) return next;
      }
    }
    return null;
  }

  function _longDistanceReturnDay() {
    const regionCities = String(_mapMeta.regionCities || _mapMeta.region_cities || "").trim();
    if (!regionCities) return null;
    const accAddr = String(_mapMeta.accommodation?.address || _mapMeta.accommodation?.region || "").toLowerCase();
    const cities = regionCities.split(/[,·\/\s]+/).filter((s) => s.length >= 2).map((s) => s.toLowerCase());
    if (cities.some((c) => accAddr.includes(c))) return null;
    for (let i = _planDays.length - 1; i >= 1; i--) {
      const seg = _airportAccommodationSegment(_planDays[i]);
      if (seg?.to?.stop?.isAirport) {
        const prev = _planDays[i - 1];
        if (prev && !_airportAccommodationSegment(prev)) return prev;
      }
    }
    return null;
  }

  function _renderTransitLegCard(from, to, title) {
    if (!from || !to) return "";
    const naverWebUrl = _naverRouteWebUrl(from, to, "transit");
    const naverNmapUrl = _naverRouteNmapUrl(from, to, "transit");
    const kakaoUrl = _kakaoRouteUrl(from, to);
    return `<article class="plan-transfer-card">
      <div class="plan-transfer-card__icon">🚇</div>
      <div class="plan-transfer-card__body">
        <div class="plan-transfer-card__title">${esc(title)}</div>
        <div class="plan-transfer-card__route">
          <span>${esc(_routeStopName(from, "出発地"))}</span>
          <span class="plan-transfer-card__arrow">→</span>
          <span>${esc(_routeStopName(to, "到着地"))}</span>
        </div>
      </div>
      <div class="plan-transfer-card__actions">
        <a href="${esc(naverWebUrl)}" target="_blank" rel="noopener"${naverNmapUrl ? ` data-nmap="${esc(naverNmapUrl)}"` : ""} class="plan-naver-route-btn">Naver公共交通</a>
        <a href="${esc(kakaoUrl)}" target="_blank" rel="noopener">Kakao経路</a>
      </div>
    </article>`;
  }

  function renderLongDistanceTransitCard(day) {
    if (!day) return "";
    const regionCity = String(_mapMeta.regionCities || _mapMeta.region_cities || "")
      .split(/[,·\/\s]+/).filter((s) => s.length >= 2)[0] || "";
    if (!regionCity) return "";
    const accommodation = buildAccommodationStop(_mapMeta);
    const accPoint = _routePoint(accommodation);
    if (!accPoint) return "";
    const stops = (day.stops || []).filter((s) => !s.isAirport && !s.isAccommodation);
    if (!stops.length) return "";
    let html = "";
    const depDay = _longDistanceDepartureDay();
    if (depDay && depDay.day === day.day) {
      const firstStop = stops.find((s) => _routePoint(s));
      if (firstStop) html += _renderTransitLegCard(accPoint, _routePoint(firstStop), `宿泊先 → ${regionCity} ルート`);
    }
    const retDay = _longDistanceReturnDay();
    if (retDay && retDay.day === day.day) {
      const lastStop = [...stops].reverse().find((s) => _routePoint(s));
      if (lastStop) html += _renderTransitLegCard(_routePoint(lastStop), accPoint, `${regionCity} → 宿泊先 ルート`);
    }
    return html;
  }

  function _normStopText(s) {
    return String(s || "")
      .toLowerCase()
      .replace(/^(?:おすすめ|推薦|推奨|추천|권장)\s*[:：-]?\s*/i, "")
      .replace(/^[①②③④⑤⑥⑦⑧⑨⑩]\s*/, "")
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

  // 앵커(지도 스톱)에서 강제 제외할 장소. 관광 앵커로 부적절하거나 오매칭이 잦은 곳.
  // 교보문고: 청계천/광화문 인근의 고(高)리뷰 서점이 관광지로 오매칭되어 반복 노출됨.
  const _ANCHOR_STOP_BLOCK_RE = /교보문고|kyobo\s*book/i;

  // "서울 인사동점"처럼 지역명만으로 만들어진 가짜 "○○점" 카드를 차단.
  // 실제 지점명은 브랜드명으로 시작하지만(예: 올리브영 명동점), 환각 카드는
  // 광역시/관광 에리어 이름으로 시작하고 "점"으로 끝난다. 실존 장소가 아니다.
  const _MAJOR_MART_STOP_RE = /이마트(?!\s*24)|e-?\s*mart|emart|홈플러스|home\s*plus|homeplus|롯데마트|lotte\s*mart|lottemart|코스트코|costco|트레이더스|traders|노브랜드(?!\s*버거)|no\s*brand(?!\s*burger)/i;

  function _mapHasShoppingIntent() {
    const acts = Array.isArray(_mapMeta?.activities) ? _mapMeta.activities : [];
    const styles = Array.isArray(_mapMeta?.travelStyles) ? _mapMeta.travelStyles : [];
    return [...acts, ...styles].some((x) =>
      /^(shopping|shop_hard|쇼핑|買い物|ショッピング)$/i.test(String(x || ""))
    );
  }

  const _AREA_PREFIX_NAMES = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "제주",
    "경기", "강원", "충청", "충북", "충남", "전라", "전북", "전남", "경상", "경북", "경남",
    "인사동", "명동", "홍대", "강남", "성수", "이태원", "북촌", "삼청동", "익선동",
    "서면", "해운대", "광안리", "여의도", "잠실", "동대문", "가로수길", "압구정",
  ];
  const _AREA_NAME_SET = new Set(_AREA_PREFIX_NAMES);
  function _isFakeAreaBranch(name) {
    const t = String(name || "").trim();
    if (!/[가-힣]점$/.test(t)) return false;        // "…한글점"으로 끝나야
    const first = t.split(/\s+/)[0];                 // 첫 토큰(=브랜드 자리)
    // 첫 토큰이 지역명이거나, 첫 토큰 자체가 "에리어+점"이면 브랜드가 없는 가짜.
    return _AREA_NAME_SET.has(first) || _AREA_NAME_SET.has(first.replace(/점$/, ""));
  }

  function _isBlockedAnchorStop(stop) {
    const p = stop?.place || {};
    if (_ANCHOR_STOP_BLOCK_RE.test(`${p.name || ""} ${stop?.label || ""}`)) return true;
    if (!_mapHasShoppingIntent() && _MAJOR_MART_STOP_RE.test(`${p.name || ""} ${p.category || ""} ${p.address || ""} ${stop?.label || ""}`)) return true;
    // place.name 또는 plan-text label 어느 쪽이 가짜 지역+점이어도 차단.
    return _isFakeAreaBranch(p.name) || _isFakeAreaBranch(stop?.label);
  }

  // 스톱이 화면에 표시할 한국어 이름(place.name → 한국어 label → 알려진 매핑)을
  // 정규화해 반환. URL이 달라 _sameStop을 빠져나가도 같은 장소면 같은 키가 된다.
  function _stopKoName(stop) {
    const p = stop?.place || {};
    const pName = String(p.name || "").trim();
    if (pName && /[가-힣]/.test(pName)) return _normStopText(pName);
    const label = String(stop?.label || "").trim();
    if (label && /[가-힣]/.test(label)) return _normStopText(label);
    const known = _knownKoreanSearchName(label || pName);
    return known ? _normStopText(known) : "";
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
        // 강제 차단 장소(교보문고 등)는 앵커에서 제거
        if (_isBlockedAnchorStop(stop)) continue;
        const dupIdx = deduped.findIndex((existing) => {
          if (_sameStop(existing, stop)) return true;
          // 같은 한국어 표시명이면 중복 (예: 명동대성당이 venue URL과 경로/설명줄에서
          // 각각 매칭돼 두 번 들어온 경우). 공항·숙박은 제외.
          if (stop.isAirport || stop.isAccommodation || existing.isAirport || existing.isAccommodation) return false;
          const a = _stopKoName(existing);
          const b = _stopKoName(stop);
          return !!a && a === b;
        });
        if (dupIdx === -1) {
          deduped.push(stop);
        } else if (stop.lat != null && deduped[dupIdx].lat == null) {
          // 좌표 있는 stop이 나중에 오면 기존 좌표 없는 항목을 교체
          deduped[dupIdx] = stop;
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

  // 슬롯 레이블 판별 (wizard.js _PLAN_SLOT_RE와 동기화 유지)
  const _SLOT_LABEL_LINE_RE = /^(?:\[(?:午前|午後|昼食|夕食|夜|朝食|朝|ランチ|ディナー|カフェ|오전|오후|점심|저녁|밤|아침|카페)\]|(?:午前|午後|昼食|夕食|夜|朝食|朝|ランチ|ディナー|モーニング|カフェ|夜食|深夜|오전|오후|점심|저녁|밤|아침|카페|야식|간식|브런치|런치|디너)(?=$|\s|[:：]))/u;

  function _isSlotLabelLine(line) {
    return _SLOT_LABEL_LINE_RE.test(String(line || "").trim());
  }

  function _isTransitOrAnchorLine(line) {
    return /(?:入国|出国|チェックイン|ホテル|宿泊|空港|移動|休息|休憩|到着|出発|手荷物|審査|税関|AREX|乗換|下車|徒歩|タクシー|リムジン|コンビニ|軽食|입국|출국|체크인|호텔|숙박|공항|이동|휴식|휴게|도착|출발|수하물|심사|세관|환승|하차|도보|택시|리무진|편의점|경의중앙선|귀환|귀국|숙박지|숙박처|KTX|SRT|고속버스|KORAIL)/i.test(line || "");
  }

  function _isRecommendationLine(line) {
    return /^(?:おすすめ|推薦|推奨|추천|권장)\s*[:：-]?/i.test(String(line || "").trim());
  }

  function _isPlanNoiseLine(line) {
    const t = String(line || "").trim();
    if (!t) return true;
    if (/^(?:外観写真|写真|外観\s*写真|외관\s*사진|사진|地図|経路|ルート|지도|통로|Map|Directions)$/i.test(t)) return true;
    if (/^【(?:予算|旅行|全体|注意|参考|移動|ポイント|チェックリスト)/.test(t)) return true;
    if (/^\[(?:予算|旅行|全体|注意|参考|移動|ポイント)/.test(t)) return true;
    if (/^(?:예산|여행의\s*포인트|전체\s*포인트|주의|참고)\b/.test(t)) return true;
    if (_isAnyUrlLine(t) && !_isMapsUrlLine(t)) return true;
    if (/^\[[^\]]+\]\(https?:\/\//i.test(t) && !_isMapsUrlLine(t)) return true;
    if (/^★\s*\d/.test(t) || /^(?:営業中|営業終了|영업\s*중|영업\s*종료|¥+|₩+)/.test(t)) return true;
    if (/(?:Google|グーグル|평점|評価|口コミ|件|메뉴|メニュー)/i.test(t)) return true;
    // Korean naver-score lines like "Naver 70.0 Blog 24,592" or "네이버 54.8 Blog 7"
    if (/^(?:Naver|네이버)\s+\d/.test(t)) return true;
    if (/(?:この日|이 날|当日).*(?:候補|動線|移動経路|식사|동선|경로)/.test(t)) return true;
    if (/(?:이 날의|この日の).*(?:참조|参照|확인된|確認済|조합|내장|들르)/.test(t)) return true;
    if (/(?:外観|写真|カード|本文で引用|본문에서 인용)/.test(t)) return true;
    if (/(?:쇼핑과\s*사진|买い物と写真|스팟|スポット.*들르|立ち寄り)/i.test(t)) return true;
    if (/(?:食事候補リスト|식사\s*후보|レストラン情報がありません|現地で|현지에서|探す|찾으|利用してください|이용해)/i.test(t)) return true;
    if (/^(?:午前|午後|昼食|夕食|朝食|夜|ランチ|ディナー|朝|昼|食事|오전|오후|점심|저녁|아침)\s*$/.test(t)) return true;
    // Ticket event metadata lines — period/date/ticket-link lines are noise
    if (/^(?:기간|期間|회기|会期)\s*[:：]/.test(t)) return true;
    if (/^INTERPARK\s+TICKET/i.test(t)) return true;
    // 순수 일자 헤더(뒤에 장소명 없음)만 noise — "2日目 (북한산)"처럼 뒤에 내용 있으면 noise 아님
    if (/^(?:\d+\s*日目|第\s*\d+\s*日|Day\s*\d+|최종일|첫날|\d+\s*(?:일째|일차|일\s*차)|마지막\s*날)\s*$/.test(t)) return true;
    if (/^(?:観光\s*スポット|관광\s*스팟?)\s*[·・]/i.test(t)) return true;
    // 가성비/형용사 설명 텍스트 단독 라인 — "コスパ抜群", "ボリューム満点、伝統な韓国料理" 등
    if (/^(?:コスパ抜群|コスパ|ボリューム満点|ボリューム\s*[満가-힣]|伝統な|香ばしい|絶品|格別|素晴らし|大人気|人気の|有名な|雰囲気|美味しい|おいしい)/.test(t)) return true;
    // 장소명+일본어 설명 혼합 — "북서울꿈의숲 전망대からソウルの街並み" 등
    if (/(?:から(?:ソウル|서울|釜山|부산|見渡)|を散策|の街並み|の夜景を|を楽しむ)/i.test(t)) return true;
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

    // Extract venue name from “회장:XXX”, “장소:XXX”, “会場:XXX” patterns (ticket events)
    const venueM = t.match(/^(?:회장|장소|venue|会場|場所)\s*[:：]\s*(.+)/i);
    if (venueM) {
      add(venueM[1]);
      return out; // venue lines → only return the extracted venue name
    }
    for (const m of t.matchAll(/[（(]([^）)]{2,60})[）)]/g)) {
      add(m[1]);
    }
    add(t);
    for (const part of t.split(/[·・]/)) add(part);
    const quoteHead = t.split(/[「『'””<]/)[0];
    if (quoteHead !== t) add(quoteHead);
    const venueTail = t.match(/(?:\d{4}[-./]\d{1,2}[-./]\d{1,2}[^·・]*[·・]\s*)(.+)$/);
    if (venueTail) add(venueTail[1]);
    return out;
  }

  function _explicitPlaceFromLine(line, placeIndex) {
    if (!placeIndex?.byName) return null;
    if (_isTransitOrAnchorLine(line)) return null;
    if (_isRecommendationLine(line) || _isPlanNoiseLine(line)) return null;
    if (/[가-힣A-Za-z0-9）)]에서\s+.{4,}/.test(String(line || ""))) return null;
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
        if (norm.length >= 4 && key.startsWith(norm)) return p;
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
    let start = -1;
    const planHeadIdx = lines.findIndex((line) =>
      /(?:テキスト詳細計画|텍스트\s*상세\s*계획|詳細計画|상세\s*계획)/i.test(line)
    );
    if (planHeadIdx >= 0) {
      start = planHeadIdx + 1;
    } else {
      // Fall back to first day header — skip any LLM intro text before "1日目"
      const firstDayIdx = lines.findIndex((line) => {
        const t = line.trim();
        return isDayHeaderLine(t);
      });
      start = firstDayIdx >= 0 ? firstDayIdx : 0;
    }
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
      const mapsUrl = _extractMapsUrl(t);
      if (mapsUrl) {
        const url = mapsUrl;
        const place = byUrl[mapsUrlKey(url)] || null;
        // Always allow the raw Maps URL itself so URL-matched stops are never filtered
        allowed.add(`url:${mapsUrlKey(url)}`);
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
        cleaned.length > 54 ||
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
    const uris = [
      stop?.place?.google_maps_uri,
      stop?.place?.maps_url,
      stop?.url,
      stop?.sourceUrl,
    ].filter(Boolean);
    for (const uri of uris) {
      if (allowedKeys.has(`url:${mapsUrlKey(uri)}`)) return true;
    }
    const names = [stop?.place?.name, stop?.label]
      .map((s) => _normStopText(s))
      .filter(Boolean);
    return names.some((n) => allowedKeys.has(`name:${n}`));
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
    const s = String(url || "");
    const naverPlaceM = /map\.naver\.com/i.test(s) && s.match(/\/place\/(\d{6,})/i);
    if (naverPlaceM) return `naver-place:${naverPlaceM[1]}`;
    if (/map\.naver\.com/i.test(s)) {
      const base = s.split("?")[0].replace(/\/$/, "");
      try { return decodeURIComponent(base.replace(/\+/g, " ")); } catch { return base; }
    }
    const m = s.match(/[?&]cid=(\d+)/);
    return m ? `cid:${m[1]}` : s.split("&g_mp=")[0].split("&")[0];
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
      slot: stop?.slot || "",
      name: p.name || stop?.label || "",
      category: stop?.isAirport
        ? "空港"
        : stop?.isAccommodation
        ? "宿泊先"
        : p.primary_type || p.types?.[0] || "スポット",
      address: p.address || "",
      url: p.google_maps_uri || p.maps_url || stop?.url || "",
      note: stop?.line && !_isMapsUrlLine(stop.line) && !_isAnyUrlLine(stop.line) ? stop.line : "",
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
      if (!t) continue;
      // 다른 stop의 URL을 만나면 거기서 검색 중단 — continue로 넘으면 그 위 stop의 label을 잘못 가져옴
      if (_isMapsUrlLine(t) || _isAnyUrlLine(t)) break;
      if (_isPlanNoiseLine(t) || _isRecommendationLine(t)) continue;
      if (DAY_HEADER_RE.test(t)) {
        // "2日目 (북한산)" 형식 — 괄호 안 한국어 장소명 추출
        const dayParen = t.match(/[（(]([가-힣][가-힣\s·]{1,25})[）)]/);
        if (dayParen) return dayParen[1].trim();
        return "";
      }
      if (_isSlotLabelLine(t)) continue; // 슬롯 레이블(午前/점심 등)은 장소명 아님
      // "観光スポット · 설명" 형식 설명줄은 장소명 아님
      if (/^(?:観光\s*スポット|관광\s*스팟?)\s*[·・]/i.test(t)) continue;
      let label = t
        .replace(/^\[[\d:〜~\-]+\]\s*/, "")
        .replace(/^[-・*①②③④⑤⑥⑦⑧⑨⑩]\s*/, "")
        .trim();
      // Extract 「place name」 or 『place name』 if the line wraps the name in brackets
      const qm = label.match(/[「『]([^」』]{1,40})[」』]/);
      if (qm) return qm[1].trim();
      // Strip "Name：description" or "Name:description" — only keep part before colon
      label = label.replace(/[：:].+$/, "").trim();
      // If label has no Korean but full-width parens contain Korean, use that Korean instead
      // e.g. "外雪岳（설악산 국립공원 (외설악)）" → "설악산 국립공원"
      if (!/[가-힣]/.test(label)) {
        const koInParens = label.match(/（([^）]*[가-힣][^）]*)）/);
        if (koInParens) {
          label = koInParens[1].replace(/\s*\([^)]{1,30}\)\s*$/, "").trim();
        } else {
          label = label.replace(/（[^）]{1,60}）/g, "").trim();
        }
      } else {
        label = label.replace(/（[^）]{1,60}）/g, "").trim();
      }
      // Strip half-width trailing parentheticals
      label = label.replace(/\s*\([^)]{1,40}\)\s*$/, "").trim();
      // Strip orphaned outer parens left by nested paren removal (e.g. "八公山国立公園）" → "八公山国立公園")
      label = label.replace(/^[（(]+/, "").replace(/[）)]+$/, "").trim();
      // Strip Japanese activity descriptions after particles (で, を, に, は, が + verb)
      label = label.replace(/\s*[でをにはが].+$/, "").trim();
      // Strip Korean activity descriptions after 에서 + space (location-action pattern)
      label = label.replace(/\s*에서\s+.+$/, "").trim();
      // 긴 설명 문장은 장소명이 아님 (문장 종결 기호 포함 + 20자 이상)
      if (label.length > 20 && /[。！？.!?]/.test(label)) continue;
      return label;
    }
    return "";
  }

  function parseDayNumber(line) {
    const t = line.trim();
    if (/^(?:#{1,3}\s*)?(?:【\s*)?(?:最終日|帰国日|最終\s*日|최종일|마지막\s*날)\s*(?:[】\]:：\-].*)?$/.test(t)) return -1;
    if (/^첫날/.test(t)) return 1;
    const koOrdinal = t.match(/^(둘째|두\s*번째|셋째|세\s*번째|넷째|네\s*번째|다섯째|다섯\s*번째|여섯째|여섯\s*번째)\s*날(?=$|\s|[:：\-])/);
    if (koOrdinal) {
      const compact = koOrdinal[1].replace(/\s+/g, "");
      const map = {
        "둘째": 2, "두번째": 2,
        "셋째": 3, "세번째": 3,
        "넷째": 4, "네번째": 4,
        "다섯째": 5, "다섯번째": 5,
        "여섯째": 6, "여섯번째": 6,
      };
      return map[compact] || null;
    }
    const m = t.match(/(\d+)\s*日目|第\s*(\d+)\s*日|Day\s*(\d+)|(\d+)\s*(?:일째|일차|일\s*차)/i);
    if (m) return parseInt(m[1] || m[2] || m[3] || m[4], 10);
    return null;
  }

  function isDayHeaderLine(line) {
    const t = String(line || "").trim();
    if (parseDayNumber(t) === null) return false;
    return /^(?:#{1,3}\s*)?(?:【\s*)?(?:\d+\s*日目|第\s*\d+\s*日|Day\s*\d+\b|\d+\s*(?:일째|일차|일\s*차)|첫날(?=$|\s|[:：\-])|(?:둘째|두\s*번째|셋째|세\s*번째|넷째|네\s*번째|다섯째|다섯\s*번째|여섯째|여섯\s*번째)\s*날(?=$|\s|[:：\-])|最終日|帰国日|最終\s*日|최종일|마지막\s*날)/i.test(t);
  }

  function findPlaceForLine(line, placeIndex) {
    return _explicitPlaceFromLine(line, placeIndex);
  }

  function _placeMatchedParenthetical(line, place) {
    if (!place?.name) return "";
    for (const m of String(line || "").matchAll(/[（(]([^）)]{2,60})[）)]/g)) {
      const inside = m[1].trim();
      if (inside && _placeNameMatchesLabel(place.name, inside)) return inside;
    }
    return "";
  }

  function rawLineBeforeUrl(lines, url) {
    const i = lines.findIndex((ln) => ln.trim().startsWith(url) || ln.includes(url));
    if (i <= 0) return "";
    for (let j = i - 1; j >= 0; j--) {
      const t = lines[j].trim();
      if (!t || _isMapsUrlLine(t) || _isAnyUrlLine(t)) continue;
      if (_isPlanNoiseLine(t) || _isRecommendationLine(t) || _isSlotLabelLine(t)) continue;
      if (DAY_HEADER_RE.test(t)) return "";
      return t;
    }
    return "";
  }

  function placeToStop(place, line, sourceLineIdx = null) {
    if (!place) return null;
    // Prefer the plan-text line as label so that Naver search mismatch
    // (e.g. wrong POI returned for a query) doesn't replace the correct name.
    const parenVenue = _placeMatchedParenthetical(line, place);
    const label = parenVenue ? (place.name || parenVenue) : (line || place.name || "スポット");
    return {
      url: place.google_maps_uri || place.maps_url || "",
      place,
      label,
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
    let _currentSlot = ""; // 현재 시간대 슬롯 (夜/午後/昼食 등) — lock payload에 포함

    const pushStop = (dayObj, url, lineIdx) => {
      const trimmed = lines[lineIdx].trim();
      const urlOnly = trimmed.split(/\s/)[0];
      let place = (placeIndex.byUrl || placeIndex || {})[mapsUrlKey(urlOnly)] || null;
      // cafe-anchor: = カフェ巡り synthetic search query — skip (no specific venue)
      // anchor: = real venue with no Naver coords (e.g. event hall) — allow, shown as grey pin
      const pid = place?.place_id || "";
      if (pid.startsWith("cafe-anchor:")) return;
      const rawBefore = rawLineBeforeUrl(lines, urlOnly);
      const labelText = labelBeforeUrl(lines, urlOnly);
      // 플랜 텍스트의 venue가 source of truth. venue가 명시적으로 한국어 장소를
      // 가리키는데(예: "清渓川（청계천）") byUrl로 매칭된 place가 그와 전혀 다르면
      // (LLM이 청계천 venue 아래에 교보문고 광화문점 URL을 잘못 붙인 경우), 그 place를
      // 버려 앵커 리스트가 상세 플랜과 일치하도록 한다. 한국어명이 없는 일본어 전용
      // venue(예: "明洞聖堂")는 koVenue가 비어 가드를 통과하므로 영향 없음.
      const koVenueM = String(rawBefore || "").match(/[（(]([가-힣][가-힣\s·]{0,40})[）)]/);
      let koVenue = koVenueM ? koVenueM[1].trim() : (/[가-힣]/.test(labelText) ? labelText : "");
      // 한국어 괄호가 없는 일본어 전용 venue(예: "清渓川")도 알려진 매핑으로 한국어명을
      // 유도해 가드를 적용 (清渓川→청계천이면 byUrl 교보문고와 불일치 → 드롭)
      if (!koVenue && labelText) {
        const knownKo = _knownKoreanSearchName(labelText);
        if (knownKo) koVenue = knownKo;
      }
      let venueMismatch = false;
      if (place?.name && koVenue && !_placeNameMatchesLabel(place.name, koVenue)) {
        place = null;
        venueMismatch = true;
      }
      let label = labelText || place?.name || "スポット";
      const parenVenue = _placeMatchedParenthetical(rawBefore || label, place);
      if (parenVenue) label = place?.name || parenVenue;
      // byUrl 매칭 실패(LLM이 /p/search/ URL을 생성했지만 API 결과는 /p/place/ URL인 경우)
      // 또는 venue 불일치로 place를 버린 경우 → venue 한국어명으로 byName 재시도
      if (!place && placeIndex.byName) {
        const nk = _normStopText(koVenue || label);
        if (nk) place = placeIndex.byName[nk] || null;
      }
      // label이 일본어(漢字)라 byName 미스 → Naver search URL 쿼리 텀으로 재시도
      // e.g. label="明洞聖堂", URL="/p/search/명동성당"
      //   → "명동성당" 시도, 또 _knownKoreanSearchName("명동성당")="천주교서울대교구주교좌명동대성당" 시도
      // venue 불일치(venueMismatch)인 경우 URL 검색어는 잘못된 장소를 가리키므로 신뢰하지 않음
      if (!place && !venueMismatch && placeIndex.byName) {
        const searchMatch = urlOnly.match(/\/search\/([^?&/#]+)/);
        if (searchMatch) {
          const decoded = (() => { try { return decodeURIComponent(searchMatch[1]); } catch (_) { return searchMatch[1]; } })();
          const qk = _normStopText(decoded);
          if (qk) place = placeIndex.byName[qk] || null;
          if (!place) {
            const knownFull = _knownKoreanSearchName(decoded);
            if (knownFull) {
              const kk = _normStopText(knownFull);
              if (kk) place = placeIndex.byName[kk] || null;
            }
          }
        }
      }
      const rec = {
        url: urlOnly,
        place,
        label,
        line: trimmed,
        slot: _currentSlot,
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
      if (dayNum !== null && isDayHeaderLine(t)) {
        const num = dayNum === -1 ? (fallbackDayCount || days.length + 1 || 99) : dayNum;
        current = { day: num, title: t.replace(/^#+\s*/, ""), stops: [] };
        _currentSlot = "";
        days.push(current);
        continue;
      }
      if (_SLOT_LABEL_LINE_RE.test(t)) {
        const _sm = t.match(/(午前|午後|昼食|夕食|夜|朝食|ランチ|ディナー|カフェ|오전|오후|점심|저녁|밤|아침|카페)/u);
        if (_sm) _currentSlot = _sm[1];
        continue;
      }
      const mapsUrl = _extractMapsUrl(t);
      if (mapsUrl) {
        const url = mapsUrl;
        if (current) pushStop(current, url, i);
        else pushStop(null, url, i);
        continue;
      }
      // Only Naver/Google Maps URLs create stops — name-matching prose lines
      // caused stops to bleed into wrong days (e.g. Day-1 overview mentioning
      // Day-3 place names being incorrectly pinned to Day 1).
    }

    // Orphan stops (Maps URLs before the first day header) are discarded.
    // With the day-header fallback in _routeRelevantText they should be rare;
    // merging them into Day 1 caused intro-text places to pollute the arrival day.
    if (!days.length && fallbackDayCount) {
      const n = Math.max(1, fallbackDayCount);
      for (let d = 1; d <= n; d++) {
        days.push({ day: d, title: `${d}日目`, stops: [] });
      }
    }

    // Second pass: add byName-matched stops for places mentioned without a Maps URL.
    // byName is populated by wizard.js _enrichUnlinkedAttractions before render() is called.
    // Scoped per day section to avoid cross-day bleeding.
    if (placeIndex?.byName && Object.keys(placeIndex.byName).length) {
      const resolvedDayNum = (day) => {
        // 最終日 has parseDayNumber() == -1; day.day was set to fallbackDayCount
        return day.day;
      };
      for (const day of days) {
        const target = resolvedDayNum(day);
        const dayHeaderIdx = lines.findIndex((l) => {
          const t = l.trim();
          if (!isDayHeaderLine(t)) return false;
          const dn = parseDayNumber(t);
          if (dn === target) return true;
          // 最終日/마지막 날 (parseDayNumber == -1)
          if (dn === -1) {
            return (fallbackDayCount || days.length + 1 || 99) === target;
          }
          return false;
        });
        if (dayHeaderIdx < 0) continue;
        const nextHdrIdx = lines.findIndex((l, idx) => {
          if (idx <= dayHeaderIdx) return false;
          return parseDayNumber(l.trim()) !== null && isDayHeaderLine(l.trim());
        });
        const sectionEnd = nextHdrIdx < 0 ? lines.length : nextHdrIdx;

        for (let i = dayHeaderIdx + 1; i < sectionEnd; i++) {
          const t = lines[i].trim();
          if (!t || _isMapsUrlLine(t) || _isAnyUrlLine(t)) continue;
          if (_isSlotLabelLine(t) || _isPlanNoiseLine(t) || _isTransitOrAnchorLine(t) || _isRecommendationLine(t)) continue;
          if (DAY_HEADER_RE.test(t)) continue; // "2日目 (북한산)" 같은 날짜 헤더 패턴 건너뜀
          const place = _explicitPlaceFromLine(t, placeIndex);
          if (!place) continue;
          const label = t
            .replace(/^[-・*①②③④⑤⑥⑦⑧⑨⑩]\s*/, "")
            .replace(/^\[[^\]]+\]\s*/, "")
            .replace(/^【[^】]+】\s*/, "")
            .replace(/[（(][^）)]*[）)]/g, " ")
            .replace(/[：:].+$/, "")
            .trim();
          const stop = placeToStop(place, label || place.name, i);
          if (stop && !day.stops.some((s) => _sameStop(s, stop))) {
            day.stops.push(stop);
          }
        }
      }
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
    return Promise.reject(new Error("GOOGLE_MAPS_DISABLED"));
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

  function markerDisplayStops(stops) {
    const threshold = 0.0005;
    const groups = [];
    const out = new Array(stops.length);
    stops.forEach((stop, idx) => {
      const lat = Number(stop.lat);
      const lng = Number(stop.lng);
      let group = groups.find((g) =>
        Math.abs(g.lat - lat) <= threshold && Math.abs(g.lng - lng) <= threshold
      );
      if (!group) {
        group = { lat, lng, items: [] };
        groups.push(group);
      }
      group.items.push({ stop, idx, lat, lng });
    });
    groups.forEach((group) => {
      const count = group.items.length;
      if (count === 1) {
        const item = group.items[0];
        out[item.idx] = item;
        return;
      }
      const radius = 0.00042 + Math.min(count, 6) * 0.00004;
      group.items.forEach((item, pos) => {
        const angle = -Math.PI / 2 + (Math.PI * 2 * pos) / count;
        out[item.idx] = {
          ...item,
          lat: group.lat + Math.sin(angle) * radius,
          lng: group.lng + Math.cos(angle) * radius,
        };
      });
    });
    return out;
  }

  function materializeNaverStopCoord(stop) {
    if (!stop || (stop.lat != null && stop.lng != null)) return stop;
    const p = stop.place || {};
    const x = p.mapx ?? p.naver_mapx;
    const y = p.mapy ?? p.naver_mapy;
    if (x == null || y == null || !global.naver?.maps?.TransCoord) return stop;
    const nx = Number(x), ny = Number(y);
    if (!Number.isFinite(nx) || !Number.isFinite(ny)) return stop;
    // TM128 유효 범위 검증 (한국 TM128: X≈60000~700000, Y≈120000~700000)
    // WGS84×10^7 값(수억 단위)이 잘못 들어오면 TM128로 해석 시 쓰레기 좌표 발생
    if (nx < 60000 || nx > 700000 || ny < 120000 || ny > 700000) return stop;
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
    const stops = (day.stops || [])
      .map((s, i) => s.lat != null && s.lng != null ? { ...s, _seqNum: i + 1 } : null)
      .filter(Boolean);
    if (!stops.length) {
      showMapStatus("この日の地図表示可能なスポットがありません。", true);
      return;
    }
    showMapStatus("");

    const bounds = new global.google.maps.LatLngBounds();
    const path = [];
    const colors = markerColors();

    stops.forEach((stop) => {
      const pos = { lat: Number(stop.lat), lng: Number(stop.lng) };
      path.push(pos);
      bounds.extend(pos);
    });

    markerDisplayStops(stops).forEach(({ stop, idx, lat, lng }) => {
      const pos = { lat, lng };
      bounds.extend(pos);
      const seqN = stop._seqNum ?? (idx + 1);
      const marker = new global.google.maps.Marker({
        position: pos,
        map: _mapInstance,
        label: { text: String(seqN), color: "#fff", fontWeight: "700" },
        title: stop.place?.name || stop.label,
        icon: {
          path: global.google.maps.SymbolPath.CIRCLE,
          fillColor: colors[(seqN - 1) % colors.length],
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
          `<div class="plan-map-infowin"><strong>${name}</strong>${addr}<br><a href="${esc(link)}" target="_blank" rel="noopener">Naver Map</a></div>`
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

  async function renderNaverMapForDay(day) {
    if (!_mapInstance || !global.naver?.maps) return;
    const renderSeq = ++_routeRenderSeq;
    clearMapOverlays();
    (day.stops || []).forEach(materializeNaverStopCoord);
    // Preserve original day.stops index as _seqNum so map pin numbers match anchor list
    const stops = (day.stops || [])
      .map((s, i) => s.lat != null && s.lng != null ? { ...s, _seqNum: i + 1 } : null)
      .filter(Boolean);
    if (!stops.length) {
      showMapStatus("이 날짜에는 지도에 표시할 좌표가 있는 장소가 아직 없습니다.", true);
      return;
    }
    showMapStatus("");

    const nmap = global.naver.maps;
    const bounds = new nmap.LatLngBounds();
    const path = [];
    const colors = markerColors();

    // Build path first, then render markers in reverse so stop 1 is on top when overlapping
    stops.forEach((stop) => {
      const pos = new nmap.LatLng(Number(stop.lat), Number(stop.lng));
      path.push(pos);
      bounds.extend(pos);
    });

    [...markerDisplayStops(stops)].reverse().forEach(({ stop, idx, lat, lng }) => {
      const pos = new nmap.LatLng(lat, lng);
      const seqN = stop._seqNum ?? (idx + 1);
      const color = colors[(seqN - 1) % colors.length];
      const marker = new nmap.Marker({
        position: pos,
        map: _mapInstance,
        title: stop.place?.name || stop.label,
        zIndex: stops.length - idx,
        icon: {
          content:
            `<span style="display:flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:50%;background:${color};color:#fff;border:2px solid #fff;font-size:13px;font-weight:700;box-shadow:0 2px 8px rgba(0,0,0,.25)">${seqN}</span>`,
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

    const segment = _airportAccommodationSegment(day);
    let routePath = path;
    let routeStroke = "#2B6CB0";

    console.debug("[PlanMap] day", day.day, "| geoStops:", stops.length, "| segment:", segment ? `${segment.from?.name}→${segment.to?.name}` : "null", "| transport:", _mapMeta?.transport);

    if (segment && _hasRouteCoords(segment.from) && _hasRouteCoords(segment.to)) {
      if (_selectedTransportHasTransitRoute()) {
        showMapStatus("公共交通ルートを読み込み中…");
        const route = await _fetchTransitRoute(segment.from, segment.to);
        if (renderSeq !== _routeRenderSeq) return;
        if (route?.path?.length >= 2) {
          const transitPath = route.path
            .map((p) => {
              const lat = Number(p.lat);
              const lng = Number(p.lng);
              if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
              const pos = new nmap.LatLng(lat, lng);
              bounds.extend(pos);
              return pos;
            })
            .filter(Boolean);
          if (transitPath.length >= 2) {
            routePath = transitPath;
            routeStroke = "#7C3AED";
            renderDayStops(day);
            showMapStatus("");
          }
        } else {
          showMapStatus("");
          routePath = [];
        }
      } else if (_selectedTransportHasCarRoute()) {
        showMapStatus("車ルートを読み込み中…");
        const route = await _fetchAirportDrivingRoute(segment);
        if (renderSeq !== _routeRenderSeq) return;
        if (route?.path?.length >= 2) {
          day._airportDrivingRoute = route;
          const drivingPath = route.path
            .map((p) => {
              const lat = Number(p.lat);
              const lng = Number(p.lng);
              if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
              const pos = new nmap.LatLng(lat, lng);
              bounds.extend(pos);
              return pos;
            })
            .filter(Boolean);
          if (drivingPath.length >= 2) {
            routePath = drivingPath;
            routeStroke = "#12A150";
            renderDayStops(day);
            showMapStatus("");
          }
        } else {
          day._airportDrivingRoute = null;
          showMapStatus("車ルートを取得できないため、地点間の目安線を表示しています。", true);
        }
      } else {
        // 도보 — straight dashed line
        showMapStatus("");
        routeStroke = "#6B7280";
      }
    } else if (stops.length >= 2) {
      if (_selectedTransportIsWalk()) {
        // 도보: 직선 표시
        routeStroke = "#6B7280";
        showMapStatus("");
      } else if (_selectedTransportHasTransitRoute()) {
        showMapStatus("");
        routePath = [];
      } else {
        // 자동차: Naver Directions 5 실제 도로 경로
        showMapStatus("ルートを読み込み中…");
        const routePoints = await _fetchDayStopsRoute(stops);
        if (renderSeq !== _routeRenderSeq) return;
        if (routePoints && routePoints.length >= 2) {
          const drivingPath = routePoints
            .map((p) => {
              const lat = Number(p.lat);
              const lng = Number(p.lng);
              if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
              const pos = new nmap.LatLng(lat, lng);
              bounds.extend(pos);
              return pos;
            })
            .filter(Boolean);
          if (drivingPath.length >= 2) {
            routePath = drivingPath;
            routeStroke = "#2B6CB0";
          }
        }
        showMapStatus("");
      }
    }

    if (routePath.length >= 2) {
      const isRouteData = routePath.length > path.length;
      const isWalk = _selectedTransportIsWalk();
      const isTransit = _selectedTransportHasTransitRoute();
      _polyline = new nmap.Polyline({
        map: _mapInstance,
        path: routePath,
        strokeColor: routeStroke,
        strokeOpacity: isRouteData ? 0.92 : 0.70,
        strokeWeight: isRouteData ? 5 : 3,
        strokeStyle: (isWalk || (isTransit && routePath.length === path.length)) ? "shortdash" : isRouteData ? "solid" : "shortdash",
      });
    }

    _mapInstance.fitBounds(bounds);
    if (stops.length === 1) _mapInstance.setZoom(14);
    requestAnimationFrame(refreshMapLayout);
    setTimeout(refreshMapLayout, 350);
  }

  function _dayTabLabel(d) {
    // Extract short label from parsed title (e.g. "3日目 — 松島" → "3日目")
    const raw = String(d.title || "").replace(/^#+\s*/, "").replace(/\s*[:\-–—]\s*.*$/, "").trim();
    if (/\d+日目/.test(raw)) return raw.match(/\d+日目/)[0];
    return `${d.day}日目`;
  }

  function renderDayTabs(days) {
    const el = document.getElementById("planDayTabs");
    if (!el) return;
    el.innerHTML = days
      .map(
        (d) =>
          `<button type="button" class="plan-day-tab${d.day === _activeDay ? " active" : ""}" data-day="${d.day}">${_dayTabLabel(d)}</button>`
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
    if (_isMapsUrlLine(lines[idx] || "") && idx - 1 >= dayStart) {
      const prev = String(lines[idx - 1] || "").trim();
      if (prev && !_isMapsUrlLine(prev) && !DAY_HEADER_RE.test(prev)) start = idx - 1;
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
      if (DAY_HEADER_RE.test(t) || _isMapsUrlLine(t) || _isAnyUrlLine(t) || _isSlotLine(t)) break;
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
      if (dayNum !== null && isDayHeaderLine(t)) {
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
    const _STOP_CAT_JA = {
      tourist_attraction: "観光スポット", point_of_interest: "観光スポット",
      park: "公園", museum: "博物館", art_gallery: "美術館",
      aquarium: "水族館", amusement_park: "遊園地", zoo: "動物園",
      natural_feature: "自然", stadium: "スタジアム", campground: "キャンプ場",
      lodging: "ホテル", restaurant: "レストラン", cafe: "カフェ",
      food: "飲食店", shopping_mall: "ショッピングモール", establishment: "施設",
    };
    function _stopCatLabel(stop) {
      if (stop.isAirport) return "空港";
      if (stop.isAccommodation) return "宿泊先";
      const p = stop.place || {};
      const rawKey = (p.primary_type || p.types?.[0] || "").toLowerCase().replace(/\s+/g, "_");
      if (_STOP_CAT_JA[rawKey]) return _STOP_CAT_JA[rawKey];
      const catRaw = String(p.category || "");
      // Also try the category field as an English key (Naver/VK places store "tourist_attraction" etc.)
      const catKey = catRaw.toLowerCase().replace(/\s+/g, "_").trim();
      if (_STOP_CAT_JA[catKey]) return _STOP_CAT_JA[catKey];
      const catKo = catRaw.toLowerCase();
      if (/음식점|식당|맛집|분식|한식|중식|일식|양식|육류|곱창|막창|삼겹/.test(catKo)) return "飲食店";
      if (/카페|커피|베이커리|디저트|빙수/.test(catKo)) return "カフェ";
      // Korean Naver category with ">" hierarchy (e.g. "스포츠,오락>월드컵경기장")
      if (catKo.includes(">")) {
        const top = catKo.split(">")[0].replace(/[,\s]+/g, "");
        if (/스포츠|레저|경기장/.test(top)) return "スポーツ";
        if (/쇼핑/.test(top)) return "ショッピング";
        if (/음식점|식당|음식/.test(top)) return "飲食店";
        if (/카페/.test(top)) return "カフェ";
        if (/문화|예술|전시/.test(top)) return "文化施設";
        if (/숙박/.test(top)) return "ホテル";
      }
      // place 데이터 없을 때(place=null) 이름으로 카테고리 추론
      // 카테고리 없으면 무조건 "観光スポット"이 되는 것 방지
      const labelLower = String(stop.label || p.name || "").toLowerCase();
      if (_isFoodLikeText(labelLower)) return "飲食店";
      if (_isCafeLikeText(labelLower)) return "カフェ";
      return esc(catRaw || "観光スポット");
    }

    const colors = markerColors();
    let mapNum = 0; // 지도 마커 번호 (좌표 있는 stop만 카운트, 맵 핀 번호용)
    // 렌더 단계 안전망: 강제 차단(교보문고 등) + 표시명 중복 제거.
    // normalizePlanDays에서 이미 처리하지만, 어떤 경로로든 남아도 여기서 확실히 거른다.
    const _seenStopKo = new Set();
    const stopCards = (day.stops || [])
      .filter((stop) => {
        if (_isBlockedAnchorStop(stop)) return false;
        if (stop.isAirport || stop.isAccommodation) return true;
        const ko = _stopKoName(stop);
        if (ko && _seenStopKo.has(ko)) return false;
        if (ko) _seenStopKo.add(ko);
        return true;
      })
      .map((stop, stopIdx) => {
        const hasCoords = stop.lat != null && stop.lng != null;
        const p = stop.place || {};
        // Prefer plan-text label over DB place name to avoid wrong Naver match
        // (e.g. "대한민국 고기왕" overwriting "국립아시아문화전당 광주").
        // Exception: when label is a generic Japanese activity description with no
        // Korean chars (e.g. "カフェ巡り") but p.name is a real Korean place name
        // ("마이알레") — prefer p.name so the actual place name is displayed.
        const _labelStripped = (stop.label || "").replace(/^[①②③④⑤⑥⑦⑧⑨⑩]\s*/, "").trim();
        const _pName = String(p.name || "").trim();
        const _labelHasKo = /[가-힣]/.test(_labelStripped);
        const _pNameHasKo = /[가-힣]/.test(_pName);
        const rawLabel = (!_labelHasKo && _pNameHasKo) ? _pName : (_labelStripped || _pName);
        // LLM 활동 묘사가 stop name으로 파싱된 케이스 제거
        // e.g. "ベーグル", "伝統工芸や雑貨ショップ" — 좌표도 없고, 매칭된 place도 없고, 한국어도 없으면 제외
        // 단, Maps URL에서 직접 생성된 stop(축제명 등)은 일본어라도 유지
        if (!hasCoords && !p.name && !stop.sourceUrl && !/[가-힣]/.test(rawLabel)) return null;
        const _dispLabel = rawLabel || stop.label || p.name || "";
        // 일본어로만 된 이름 → 한국어 이름 병기 (e.g. "仁寺洞通り" → "仁寺洞通り\n인사동길")
        const _isJaOnly = /[぀-ヿ一-鿿]/.test(_dispLabel) && !/[가-힣]/.test(_dispLabel);
        const _koSub = _isJaOnly ? _knownKoreanSearchName(_dispLabel) : "";
        const name = _koSub
          ? `${esc(_dispLabel)}<span class="plan-day-stop__name-ko">${esc(_koSub)}</span>`
          : esc(_dispLabel);
        // 공항·숙박 외에 이름이 없는 stop은 빈 카드가 되므로 제거
        if (!_dispLabel && !stop.isAirport && !stop.isAccommodation) return null;
        const lockable = !stop.isAirport && !stop.isAccommodation;
        const lockKey = stopLockKey(stop, day.day);
        const isLocked = _lockedStops.has(lockKey);
        const lockBtn = lockable
          ? `<button type="button" class="plan-day-stop__lock${isLocked ? " is-locked" : ""}" data-lock-key="${esc(lockKey)}" aria-pressed="${isLocked ? "true" : "false"}">${isLocked ? "固定中" : "固定"}</button>`
          : "";
        const cat = _stopCatLabel(stop);
        const thumb = stopThumbHtml(stop);
        const mapsUri = esc(mapsOpenUrl(stop));
        // Hide tip when it's a Maps URL or duplicates the stop label.
        const tipRaw = stop.line && !_isMapsUrlLine(stop.line) && !_isAnyUrlLine(stop.line) ? stop.line : "";
        const tip = tipRaw && tipRaw !== stop.label ? esc(tipRaw) : "";
        const dragAttrs = `draggable="false" data-draggable="false"`;
        const dragHandle = `<span class="plan-day-stop__drag plan-day-stop__drag--fixed" aria-hidden="true">•</span>`;
        // 카드 리스트 표시 순번: 좌표 유무 관계없이 day 내 통합 순번 (1, 2, 3...)
        const seqNum = stopIdx + 1;
        const resolveAttr = (!stop.isAirport && !stop.isAccommodation && rawLabel)
          ? ` data-raw-name="${esc(rawLabel)}"`
          : "";
        if (hasCoords) {
          mapNum++;
          const color = colors[stopIdx % colors.length]; // seqNum-1 = stopIdx → matches map pin color
          return `<article class="plan-day-stop plan-day-stop--fixed" ${dragAttrs} data-stop-index="${stopIdx}">
            <span class="plan-day-stop__num" style="background:${color}">${seqNum}</span>
            ${dragHandle}
            <a class="plan-day-stop__thumb" href="${mapsUri}"${resolveAttr} target="_blank" rel="noopener">${thumb}</a>
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
          // 좌표 없는 stop — 지도 마커 없음, 통합 순번 유지
          return `<article class="plan-day-stop plan-day-stop--no-map plan-day-stop--fixed" ${dragAttrs} data-stop-index="${stopIdx}">
            <span class="plan-day-stop__num" style="background:#aaa">${seqNum}</span>
            ${dragHandle}
            <a class="plan-day-stop__thumb" href="${mapsUri}"${resolveAttr} target="_blank" rel="noopener">${thumb}</a>
            <div class="plan-day-stop__body">
              <div class="plan-day-stop__head">
                <h4 class="plan-day-stop__name">${name}</h4>
                ${lockBtn}
              </div>
              <p class="plan-day-stop__meta">${cat}<span style="color:#888;font-size:.78em;margin-left:.4em">地図で開く</span></p>
              ${tip ? `<p class="plan-day-stop__tip"><span class="plan-day-stop__rec">おすすめ</span> ${tip}</p>` : ""}
            </div>
          </article>`;
        }
      })
      .filter(Boolean)
      .join("");
    el.innerHTML = `${renderAirportTransferCard(day)}${renderLongDistanceTransitCard(day)}${stopCards}`;
    _prefetchNaverResolveForEl(el, day);
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

    // sessionStorage 캐시 — 같은 세션에서 재생성 시 geocoding 재시도 방지
    const _CACHE_NS = "gc2_";
    function _cacheGet(key) {
      try {
        const v = sessionStorage.getItem(_CACHE_NS + key);
        return v ? JSON.parse(v) : null;
      } catch (_) { return null; }
    }
    function _cacheSet(key, val) {
      try { sessionStorage.setItem(_CACHE_NS + key, JSON.stringify(val)); } catch (_) {}
    }

    function queriesForStop(stop) {
      const label = _stopSearchName(stop);
      const placeName = String(stop.place?.name || "").trim();
      const preferLabel = !stop.isAccommodation
        && placeName
        && /[가-힣]/.test(label)
        && !_placeNameMatchesLabel(placeName, label);
      const raw = stop.isAccommodation
        ? (stop.place?.address || stop.line || stop.label)
        : preferLabel
          ? label
        : (stop.place?.address || stop.place?.name || stop.label);
      const base = String(raw || "").replace(/^[①②③④⑤⑥⑦⑧⑨⑩]\s*/, "").trim();
      if (!base || base.length < 2) return [];
      const noParen = base.replace(/\([^)]*\)/g, " ").replace(/\s+/g, " ").trim();
      const spacedRoadQuery = noParen.replace(/([\uac00-\ud7a3])(\d)/g, "$1 $2");
      // \uc9c0\uc5ed\uba85 \ud3ec\ud568 \ucffc\ub9ac \uc6b0\uc120 \uc2dc\ub3c4 \u2014 "\ud0dc\uc885\ub300 \ubd80\uc0b0" / "\uba85\ub3d9\uce7c\uad6d\uc218 \ubd80\uc0b0" \ucc98\ub7fc
      // \ub3d9\uba85 \uc7a5\uc18c\uac00 \uc5ec\ub7ec \ub3c4\uc2dc\uc5d0 \uc788\uc744 \ub54c \uc9c0\uc5ed hint \uc5c6\uc73c\uba74 \uc5c9\ub6b1\ud55c \uacf3\uc774 \ubc18\ud658\ub428
      const regionHint = String(_mapMeta.regionCities || _mapMeta.region_cities || "")
        .split(/[,\u00b7\/\s]+/).map((s) => s.trim()).filter((s) => s.length >= 2)[0] || "";
      const withRegion = regionHint && !noParen.includes(regionHint) ? `${noParen} ${regionHint}` : "";
      const aliasQueries = _landmarkSearchAliases(noParen);
      const aliasWithRegion = aliasQueries
        .map((q) => regionHint && !q.includes(regionHint) ? `${q} ${regionHint}` : q);

      // URL search query 추출 — label이 한자/일본어인 경우 URL에서 한국어 이름 보완
      // 예: label="北漢山国立公園", url=".../search/북한산국립공원" → urlKo="북한산국립공원"
      const urlSearchQuery = (() => {
        const m = (stop.url || "").match(/\/search\/([^?&/#\s]+)/);
        if (!m) return "";
        try { return decodeURIComponent(m[1].replace(/\+/g, " ")).trim(); } catch (_) { return ""; }
      })();
      const urlKo = urlSearchQuery && /[가-힣]/.test(urlSearchQuery) && urlSearchQuery !== base
        ? urlSearchQuery : "";

      // ── 복합 지명 분해 쿼리 생성 ─────────────────────────────────────────
      // 1) 공원 접미사 제거: "팔공산국립공원" / "北漢山国立公園" → "팔공산" / "北漢山"
      //    Naver Places API는 국립공원을 직접 인덱싱 안 함 → 산 이름 단독으로 재시도
      const noParkSuffix = noParen
        .replace(/\s*(?:국립|도립|군립|시립|자연|생태|광역시립|国立|道立|郡立|市立|自然|生態)?\s*(?:공원|公園)$/, "")
        .trim();
      const parkStripped = noParkSuffix !== noParen && noParkSuffix.length >= 2 ? noParkSuffix : "";
      // URL 한국어에서도 공원 접미사 제거
      const urlKoPark = urlKo
        ? urlKo.replace(/\s*(?:국립|도립|군립|시립|자연|생태|광역시립)?\s*공원$/, "").trim()
        : "";
      const urlKoParkStripped = urlKoPark && urlKoPark !== urlKo && urlKoPark.length >= 2 ? urlKoPark : "";

      // 2) 2·3글자 접두어 제거: "동산청라언덕" → "청라언덕"
      //    한국어 복합 지명에서 동네명(2글자) + 실제 명소명 패턴
      const strip2 = noParen.length >= 6 ? noParen.slice(2) : "";
      const strip3 = noParen.length >= 7 ? noParen.slice(3) : "";
      const addRegion = (q) =>
        (regionHint && q && !q.includes(regionHint) ? `${q} ${regionHint}` : "");

      const extras = [
        parkStripped && addRegion(parkStripped),
        parkStripped,
        strip2 && addRegion(strip2),
        strip2,
        strip3 && addRegion(strip3),
        strip3,
      ].filter(Boolean);

      // URL 한국어 검색어를 우선순위 높게 배치 (한자 label보다 Naver API 매칭률 높음)
      const urlQueries = [
        urlKo && regionHint && !urlKo.includes(regionHint) ? `${urlKo} ${regionHint}` : "",
        urlKo,
        urlKoParkStripped && regionHint ? `${urlKoParkStripped} ${regionHint}` : "",
        urlKoParkStripped,
      ].filter(Boolean);

      return [...urlQueries, ...aliasWithRegion, ...aliasQueries, withRegion, base, noParen, ...extras, spacedRoadQuery, `${noParen} South Korea`, `South Korea ${noParen}`]
        .map((q) => q.trim())
        .filter((q, idx, arr) => q && arr.indexOf(q) === idx);
    }

    // Naver Local Search — 관광지·박물관·자연지형에 적합 (캐시 적용)
    async function searchOne(query) {
      const ck = "s:" + query;
      if (seenQueries.has(ck)) return null;
      seenQueries.add(ck);
      const cached = _cacheGet(ck);
      if (cached !== null) return cached;
      try {
        const res = await fetch(`/api/places/search/?q=${encodeURIComponent(query)}&limit=1&type=general`);
        const body = await res.json();
        const place = body.places?.[0] || null;
        _cacheSet(ck, place);
        return place;
      } catch (_) { return null; }
    }

    // Naver 주소 지오코더 — 숙박·도로명 주소에 적합 (캐시 적용)
    async function geocodeOne(query) {
      const ck = "g:" + query;
      if (seenQueries.has(ck)) return null;
      seenQueries.add(ck);
      const cached = _cacheGet(ck);
      if (cached !== null) return cached;
      try {
        const res = await fetch(`/api/places/geocode/?q=${encodeURIComponent(query)}&limit=1`);
        const body = await res.json();
        const place = body.places?.[0] || null;
        _cacheSet(ck, place);
        return place;
      } catch (_) { return null; }
    }

    function _resultMatchesStop(stop, place, candidate) {
      const label = _stopSearchName(stop);
      const name = String(place?.name || "").trim();
      if (!/[가-힣]/.test(`${label} ${candidate}`)) return true;
      if (!name) return false;
      if (_placeNameMatchesLabel(name, candidate) || _placeNameMatchesLabel(name, label)) return true;
      // URL search query로도 비교 — label이 한자인 경우 URL에서 한국어 이름 추출
      const urlQ = (() => {
        const m = (stop.url || "").match(/\/search\/([^?&/#\s]+)/);
        if (!m) return "";
        try { return decodeURIComponent(m[1].replace(/\+/g, " ")).trim(); } catch (_) { return ""; }
      })();
      if (urlQ && /[가-힣]/.test(urlQ) && _placeNameMatchesLabel(name, urlQ)) return true;
      for (const alias of _landmarkSearchAliases(label)) {
        if (_placeNameMatchesLabel(name, alias)) return true;
      }
      const target = _compactText(`${label} ${candidate}`);
      const cat = String(place?.category || "").toLowerCase();
      if (/(공원|산|언덕|관광|명소|계곡|폭포|호수)/.test(target) && /(협회|단체|기관|사무소|회사|기업|법인)/.test(cat)) {
        return false;
      }
      // 이름과 쿼리/레이블 간 3글자 이상 한국어 공통 부분문자열이 있으면 허용
      // (예: "광주중외공원" ↔ "중외공원광주" — _placeNameMatchesLabel이 잡지 못한 케이스)
      if (name && !_isFoodLikeText(label) && !_isCafeLikeText(label)) {
        const nc = _compactText(name), cc = _compactText(candidate), lc = _compactText(label);
        for (let len = 3; len <= Math.min(nc.length, 6); len++) {
          for (let i = 0; i <= nc.length - len; i++) {
            const sub = nc.slice(i, i + len);
            if (/[가-힣]{3}/.test(sub) && (cc.includes(sub) || lc.includes(sub))) return true;
          }
        }
      }
      return false;
    }

    function _foodPlaceMatchesTripArea(stop, place) {
      const label = _stopSearchName(stop);
      if (!_isFoodLikeText(label) && !_isCafeLikeText(label)) return true;
      const regionHint = String(_mapMeta.regionCities || _mapMeta.region_cities || "")
        .split(/[,\u00b7\/\s]+/).map((s) => s.trim()).filter((s) => s.length >= 2)[0] || "";
      const tokens = _nearbyAreaTokens(regionHint);
      if (!tokens.length) return true;
      const hay = `${place?.name || ""} ${place?.address || ""} ${place?.search_area || ""}`;
      return tokens.some((t) => hay.includes(t));
    }

    function _applyCoords(stop, p) {
      const lat = Number(p.latitude), lng = Number(p.longitude);
      if (!_isKoreanCoords(lat, lng)) return false;
      stop.lat = lat;
      stop.lng = lng;
      if (stop.isAccommodation) {
        stop.place = {
          ...stop.place,
          address: stop.place?.address || p.address || "",
          latitude: lat, longitude: lng,
          google_maps_uri: p.maps_url || stop.url || "",
          maps_url: p.maps_url || stop.url || "",
        };
      } else {
        stop.place = {
          ...p,
          name: stop.place?.name || p.name,
          address: stop.place?.address || p.address,
          latitude: lat, longitude: lng,
          google_maps_uri: stop.place?.google_maps_uri || stop.url || p.maps_url,
          maps_url: stop.place?.maps_url || stop.url || p.maps_url,
        };
      }
      return true;
    }

    // 개별 stop geocoding — Local Search 우선, 주소 geocoder fallback
    async function resolveStop(stop) {
      const label = _stopSearchName(stop);
      const repairingMismatch = !stop.isAccommodation
        && stop.place?.name
        && /[가-힣]/.test(label)
        && !_placeNameMatchesLabel(stop.place.name, label);
      if (stop.lat != null && !repairingMismatch) return;
      const candidates = queriesForStop(stop);
      if (!candidates.length) return;

      // 좌표 없어도 이름 일치 시 보관 — 3차 meta-only fallback용
      // (공공 공원·자연지형 등 Naver Local Search 미인덱싱 장소 대응)
      let bestEffortPlace = null;

      // 1차: 관광지 → Naver Local Search (POI 이름 검색에 적합)
      if (!stop.isAccommodation) {
        for (const candidate of candidates) {
          const p = await searchOne(candidate);
          if (!p) continue;
          if (p.latitude != null && _resultMatchesStop(stop, p, candidate) && _foodPlaceMatchesTripArea(stop, p) && _applyCoords(stop, p)) return;
          if (!bestEffortPlace && _resultMatchesStop(stop, p, candidate)) bestEffortPlace = p;
        }
        // 1.5차: Places 검색 이름 매칭됐지만 좌표 없음 → Naver Local Search로 좌표 보완
        // 예: "강북구립미술관"이 Places API에선 name만 반환하고 좌표 없는 경우
        if (bestEffortPlace && bestEffortPlace.latitude == null) {
          const namesToTry = [bestEffortPlace.name, ...candidates.slice(0, 2)].filter((n, i, a) => n && n.length >= 2 && a.indexOf(n) === i);
          for (const name of namesToTry) {
            const resolved = await _resolveNaverCanonical(name);
            if (resolved?.lat && resolved?.lng && _isKoreanCoords(resolved.lat, resolved.lng)) {
              const merged = { ...bestEffortPlace, latitude: resolved.lat, longitude: resolved.lng };
              if (_applyCoords(stop, merged)) return;
            }
          }
        }
      }
      // 2차: 주소 geocoder (숙박은 여기가 첫 시도, 관광지는 fallback)
      for (const candidate of candidates) {
        const p = await geocodeOne(candidate);
        if (
          p?.latitude != null &&
          (stop.isAccommodation || (_resultMatchesStop(stop, p, candidate) && _foodPlaceMatchesTripArea(stop, p))) &&
          _applyCoords(stop, p)
        ) return;
      }
      if (repairingMismatch) {
        stop.lat = null;
        stop.lng = null;
        stop.place = null;
        return;
      }
      // 3차: /api/naver-resolve/ fallback — Naver Local Search 미인덱싱 관광지(소규모 지역시설 등) 대응
      // geocodeMissingStops가 await 완료 후 카드를 렌더링하므로 여기서 좌표를 채우면 번호까지 표시됨
      if (!stop.isAccommodation) {
        // URL search query에서 한국어 이름 추출 — label이 한자/일본어인 경우 Naver API 매칭 향상
        const urlQ = (() => {
          const m = (stop.url || "").match(/\/search\/([^?&/#\s]+)/);
          if (!m) return "";
          try { return decodeURIComponent(m[1].replace(/\+/g, " ")).trim(); } catch (_) { return ""; }
        })();
        const _rRegionHint = String(_mapMeta.regionCities || _mapMeta.region_cities || "")
          .split(/[,·\/\s]+/).map((s) => s.trim()).filter((s) => s.length >= 2)[0] || "";
        const _addWithRegion = (base) =>
          _rRegionHint && base && !base.includes(_rRegionHint) ? `${base} ${_rRegionHint}` : "";
        const resolveNames = [
          urlQ && /[가-힣]/.test(urlQ) ? urlQ : "",
          urlQ && /[가-힣]/.test(urlQ) ? _addWithRegion(urlQ) : "",
          label,
          _addWithRegion(label),
        ].filter((n, i, a) => n && a.indexOf(n) === i);
        for (const name of resolveNames) {
          const resolved = await _resolveNaverCanonical(name);
          if (resolved?.lat && resolved?.lng && _isKoreanCoords(resolved.lat, resolved.lng)) {
            stop.lat = resolved.lat;
            stop.lng = resolved.lng;
            if (!stop.place) {
              const canonical = resolved.canonical || name;
              stop.place = {
                name: canonical,
                latitude: resolved.lat,
                longitude: resolved.lng,
                google_maps_uri: stop.url || `https://map.naver.com/p/search/${encodeURIComponent(canonical)}`,
                maps_url: stop.url || `https://map.naver.com/p/search/${encodeURIComponent(canonical)}`,
              };
            }
            return;
          }
        }
      }
      // 4차: 좌표 확보 실패 시 place 메타만 적용
      // 지도 핀은 없지만 Naver photo_url·naver_local_link를 이용한 카드/사진 렌더링 가능
      if (!stop.place && bestEffortPlace) {
        stop.place = {
          ...bestEffortPlace,
          name: label || bestEffortPlace.name || "",
          google_maps_uri: stop.url || bestEffortPlace.maps_url || bestEffortPlace.google_maps_uri || "",
          maps_url: stop.url || bestEffortPlace.maps_url || "",
          latitude: null,
          longitude: null,
        };
      }
    }

    // 모든 stop을 병렬 처리 — 순차 처리 대비 5~10x 속도 향상
    const allStops = days.flatMap((day) =>
      day.stops.filter((s) => {
        const label = _stopSearchName(s);
        const repairingMismatch = !s.isAccommodation
          && s.place?.name
          && /[가-힣]/.test(label)
          && !_placeNameMatchesLabel(s.place.name, label);
        if (s.lat != null && !repairingMismatch) return false;
        const q = s.isAccommodation
          ? (s.place?.address || s.line || s.label)
          : repairingMismatch
            ? label
          : (s.place?.address || s.place?.name || s.label);
        return q && q.length >= 2;
      })
    );
    await Promise.allSettled(allStops.map((stop) => resolveStop(stop)));
  }

  function authErrorHtml(cfg) {
    const host = esc(global.location.origin);
    const src = cfg?.source ? `（${esc(cfg.source)}）` : "";
    return (
      "<p><strong>地図を表示できません（APIキー認証エラー）</strong></p>" +
      "<ul style='margin:.5rem 0 0 1rem;padding:0;font-size:.82rem;line-height:1.5'>" +
      "<li>Naver Cloud Platform → Maps JavaScript API のブラウザ用キー</li>" +
      "<li><b>アプリケーションの制限</b>: <b>HTTPリファラー</b></li>" +
      `<li>許可例: <code>${host}/*</code> 、 <code>http://localhost:8000/*</code></li>` +
      "<li>NAVER_MAPS_CLIENT_ID が設定されているか確認</li>" +
      "</ul>" +
      `<p style='font-size:.78rem;margin-top:.5rem'>キー出所${src} — 開発者ツール(F12)→Console の Naver Maps エラーも確認してください。</p>`
    );
  }

  async function initMap(canvas, cfg) {
    const apiKey = cfg.api_key;
    showMapStatus("地図を読み込み中…");
    _mapsProvider = "naver";
    await loadNaverMaps(apiKey);

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

    // Shortest-route toggle. Public-transit routing is intentionally not exposed here.
    _routeDisplayMode = "shortest";
    const toggleEl = document.getElementById("routeModeToggle");
    if (toggleEl) {
      toggleEl.innerHTML = `
        <button class="route-mode-btn active" data-mode="shortest" type="button">最短経路 ON</button>
        <button class="route-mode-btn" data-mode="off" type="button">最短経路 OFF</button>
      `;
      toggleEl.style.display = "flex";
      toggleEl.querySelectorAll(".route-mode-btn").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.mode === _routeDisplayMode);
        btn.onclick = () => {
          _routeDisplayMode = btn.dataset.mode;
          toggleEl.querySelectorAll(".route-mode-btn").forEach((b) =>
            b.classList.toggle("active", b.dataset.mode === _routeDisplayMode)
          );
          _drivingRouteCache.clear();
          _transitRouteCache.clear();
          const activeDay = _planDays.find((d) => d.day === _activeDay) || _planDays[0];
          if (activeDay) renderMapForDay(activeDay);
        };
      });
    }

    // Start on the first day that has actual tourist stops (not just airport/accommodation).
    // Arrival days (Day 1) are often empty or have only anchor stops, so skip them.
    const _firstTouristDay =
      _planDays.find((d) =>
        d.stops.some((s) => !s.isAirport && !s.isAccommodation && s.lat != null)
      ) || _planDays[0];
    _activeDay = _firstTouristDay.day;
    renderDayTabs(_planDays);
    renderDayStops(_firstTouristDay);

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
        fallback.innerHTML = `<p class="plan-map-fallback-msg">地図APIキー未設定のためルート地図は表示しません。${naver}</p>`;
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

  // nmap:// URL Scheme click handler — mobile opens Naver Maps app, desktop uses web URL
  (function () {
    var _isMobile = /Android|iPhone|iPad|iPod/i.test(
      (typeof navigator !== "undefined" && navigator.userAgent) || ""
    );
    document.addEventListener("click", function (e) {
      var btn = e.target && e.target.closest && e.target.closest(".plan-naver-route-btn");
      if (!btn) return;
      var nmapUrl = btn.dataset && btn.dataset.nmap;
      var webUrl = btn.href;
      if (!nmapUrl || !_isMobile) return; // desktop: let default href open in new tab
      e.preventDefault();
      var t = Date.now();
      window.location.href = nmapUrl;
      setTimeout(function () {
        if (Date.now() - t < 2000) {
          window.open(webUrl, "_blank", "noopener");
        }
      }, 1200);
    });
  })();

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
