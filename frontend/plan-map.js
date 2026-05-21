/**
 * 旅行プラン — Google Maps + Dayタブ + スポットカード（Triple風）
 */
(function (global) {
  "use strict";

  const MAPS_URL_RE = /^https?:\/\/(?:maps\.google\.com|www\.google\.com\/maps)\/\S+/i;
  const DAY_HEADER_RE =
    /^(?:#{1,3}\s*)?(?:【\s*)?(?:Day\s*)?(\d+)\s*日目|^(?:#{1,3}\s*)?第\s*(\d+)\s*日|^(?:#{1,3}\s*)?Day\s*(\d+)\b|最終日|帰国日|最終\s*日/i;
  const GMAPS_CALLBACK = "__planMapGmapsReady";

  let _mapsApiKey = null;
  let _mapsLoadPromise = null;
  let _mapInstance = null;
  let _markers = [];
  let _polyline = null;
  let _infoWindow = null;
  let _planDays = [];
  let _activeDay = 1;

  function esc(s) {
    return String(s || "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
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
    const m = String(url).match(/[?&]cid=(\d+)/);
    return m ? `cid:${m[1]}` : String(url).split("&g_mp=")[0].split("&")[0];
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
    if (/最終日|帰国日|最終\s*日/.test(t)) return -1;
    const m = t.match(/(\d+)\s*日目|第\s*(\d+)\s*日|Day\s*(\d+)/i);
    if (m) return parseInt(m[1] || m[2] || m[3], 10);
    return null;
  }

  function parsePlanDays(reply, placeIndex, fallbackDayCount) {
    const lines = reply.split(/\r?\n/);
    const days = [];
    let current = null;
    let orphanStops = [];

    const pushStop = (dayObj, url, lineIdx) => {
      const trimmed = lines[lineIdx].trim();
      const urlOnly = trimmed.split(/\s/)[0];
      const place = placeIndex[mapsUrlKey(urlOnly)] || null;
      const label = labelBeforeUrl(lines, urlOnly) || place?.name || "スポット";
      const rec = {
        url: urlOnly,
        place,
        label,
        line: trimmed,
        lat: place?.latitude != null ? Number(place.latitude) : null,
        lng: place?.longitude != null ? Number(place.longitude) : null,
      };
      if (dayObj) dayObj.stops.push(rec);
      else orphanStops.push(rec);
    };

    for (let i = 0; i < lines.length; i++) {
      const t = lines[i].trim();
      if (!t) continue;
      const dayNum = parseDayNumber(t);
      if (
        dayNum !== null &&
        (/日目|Day\s*\d|第\s*\d+\s*日|最終日|帰国日/i.test(t) || /^【\s*\d+/.test(t))
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

    days.sort((a, b) => a.day - b.day);
    return days.filter((d) => d.stops.length > 0 || days.length === 1);
  }

  async function fetchMapsConfig() {
    const res = await fetch("/api/maps/config/");
    if (!res.ok) return { enabled: false };
    return res.json();
  }

  function mapsReady() {
    return Boolean(global.google?.maps?.Map);
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

  function refreshMapLayout() {
    if (!_mapInstance || !global.google?.maps?.event) return;
    global.google.maps.event.trigger(_mapInstance, "resize");
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

  function renderMapForDay(day) {
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
        const link = stop.place?.google_maps_uri || stop.url;
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

  function renderDayStops(day) {
    const el = document.getElementById("planDayStops");
    if (!el) return;
    const colors = markerColors();
    el.innerHTML = day.stops
      .map((stop, idx) => {
        const p = stop.place || {};
        const name = esc(p.name || stop.label);
        const cat = esc(p.primary_type || p.types?.[0] || "観光スポット");
        const thumb = p.photo_name
          ? `<img src="/api/photo/?name=${encodeURIComponent(p.photo_name)}" alt="" loading="lazy" />`
          : `<span class="plan-day-stop__fallback">📍</span>`;
        const mapsUri = esc(p.google_maps_uri || p.maps_url || stop.url || "#");
        const tip = stop.line && !MAPS_URL_RE.test(stop.line) ? esc(stop.line) : "";
        return `<article class="plan-day-stop">
          <span class="plan-day-stop__num" style="background:${colors[idx % colors.length]}">${idx + 1}</span>
          <a class="plan-day-stop__thumb" href="${mapsUri}" target="_blank" rel="noopener">${thumb}</a>
          <div class="plan-day-stop__body">
            <h4 class="plan-day-stop__name">${name}</h4>
            <p class="plan-day-stop__meta">${cat}</p>
            ${tip ? `<p class="plan-day-stop__tip"><span class="plan-day-stop__rec">おすすめ</span> ${tip}</p>` : ""}
          </div>
        </article>`;
      })
      .join("");
  }

  async function geocodeMissingStops(days) {
    for (const day of days) {
      for (const stop of day.stops) {
        if (stop.lat != null) continue;
        const q = stop.place?.name || stop.label;
        if (!q || q.length < 2) continue;
        try {
          const res = await fetch(
            `/api/places/search/?q=${encodeURIComponent(q + " 韓国")}&limit=1`
          );
          const body = await res.json();
          const p = body.places?.[0];
          if (p?.latitude != null) {
            stop.lat = Number(p.latitude);
            stop.lng = Number(p.longitude);
            stop.place = { ...stop.place, ...p, google_maps_uri: p.maps_url || stop.url };
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
    await loadGoogleMaps(apiKey);

    if (!_mapInstance && canvas) {
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
    setTimeout(refreshMapLayout, 500);
    setTimeout(refreshMapLayout, 1200);
  }

  async function render(reply, placeIndex, meta) {
    const shell = document.getElementById("planMapShell");
    if (!shell) return;

    _planDays = parsePlanDays(reply, placeIndex, meta?.days || meta?.nights + 1);

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
        fallback.innerHTML = `<p class="plan-map-fallback-msg">地図APIキー未設定です。.env に <code>GOOGLE_MAPS_API_KEY</code> を設定しサーバーを再起動してください。${pts ? `<br><a href="https://www.google.com/maps/dir/${pts}" target="_blank" rel="noopener">Google Mapsでルートを開く</a>` : ""}</p>`;
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
    };
  }
})(typeof window !== "undefined" ? window : globalThis);
