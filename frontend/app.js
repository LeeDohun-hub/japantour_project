/**
 * Django `/api/chat/` と会話。同一オリジン前提（runserver）。
 */
function getCsrfToken() {
  return document.cookie.split(';')
    .map(c => c.trim())
    .find(c => c.startsWith('csrftoken='))
    ?.split('=')[1] ?? '';
}
const chatLog = document.getElementById("chatLog");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const replyLanguage = document.getElementById("replyLanguage");
const btnSend = document.getElementById("btnSend");
const btnReset = document.getElementById("btnReset");
const healthStatus = document.getElementById("healthStatus");

/** @type {{ role: string, content: string }[]} */
let history = [];
let sessionId = null;
let isComposing = false;
let _lastFailedText = null;

const COLLAPSE_HEIGHT = 240;

function formatReplyWithTicketPreviews(text) {
  const LP = window.LinkPreview;
  if (!LP || !text) return escapeHtml(text);
  const urls = LP.extractTicketUrls(text);
  if (!urls.length) return escapeHtml(text);
  const re = new RegExp(LP.TICKET_URL_RE.source, "gi");
  let html = "";
  let last = 0;
  let m;
  while ((m = re.exec(text)) !== null) {
    html += escapeHtml(text.slice(last, m.index));
    html += LP.renderSkeleton(LP.normalizeUrl(m[0]));
    last = m.index + m[0].length;
  }
  html += escapeHtml(text.slice(last));
  return html;
}

function renderTicketPlatformCards(events, lang) {
  const LP = window.LinkPreview;
  if (!LP || !events || !events.length) return "";
  const isJa = lang === "日本語";
  const title = isJa ? "🎫 チケット・公演（インターパーク）" : "🎫 티켓·공연 (인터파크)";
  const cards = events.slice(0, 6).map((ev) => {
    const url = LP.normalizeUrl(ev.ticket_url || "");
    return LP.renderCard(LP.eventToPreview(ev, url));
  }).join("");
  return `<div class="ev-section ticket-platform-section"><h4 class="ev-title">${title}</h4><div class="ticket-platform-grid">${cards}</div></div>`;
}

function appendBubble(role, content, extraHtml = "") {
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  const label = role === "user" ? "You" : "Guide";
  // Guide: 본문만 접기(번역·버튼은 항상 표시). You: 기존과 동일.
  if (role === "assistant") {
    const hasTicketLinks =
      window.LinkPreview && LinkPreview.extractTicketUrls(content || "").length > 0;
    const bodyPart = content
      ? `<div class="bubble-body${hasTicketLinks ? " bubble-body--rich" : ""}">${
          hasTicketLinks ? formatReplyWithTicketPreviews(content) : escapeHtml(content)
        }</div>`
      : "";
    div.innerHTML = `<div class="label">${label}</div>${bodyPart}${extraHtml || ""}`;
  } else {
    div.innerHTML = `<div class="label">${label}</div>${escapeHtml(content)}${extraHtml || ""}`;
  }
  chatLog.appendChild(div);

  if (role === "assistant") {
    const body = div.querySelector(".bubble-body");
    requestAnimationFrame(() => {
      if (body && body.scrollHeight > COLLAPSE_HEIGHT) {
        body.classList.add("collapsed");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "expand-btn";
        const isJaBtn = replyLanguage.value === "日本語";
        const txtMore = isJaBtn ? "もっと見る ▼" : "더 보기 ▼";
        const txtLess = isJaBtn ? "折りたたむ ▲" : "접기 ▲";
        btn.textContent = txtMore;
        const translation = div.querySelector(".translation");
        if (translation) {
          div.insertBefore(btn, translation);
        } else {
          div.appendChild(btn);
        }
        btn.addEventListener("click", () => {
          if (body.classList.contains("collapsed")) {
            body.classList.remove("collapsed");
            btn.textContent = txtLess;
          } else {
            body.classList.add("collapsed");
            btn.textContent = txtMore;
          }
        });
      }
      chatLog.scrollTop = chatLog.scrollHeight;
    });
  } else {
    chatLog.scrollTop = chatLog.scrollHeight;
  }
}

const LOADING_MESSAGES = {
  "日本語": ["旅行のご要望を確認しています", "関連情報を検索しています", "回答を生成しています"],
  "한국어": ["여행 관련 요구사항을 확인중입니다", "관련 정보를 검색하고 있습니다", "답변을 생성중입니다"],
};

function appendLoadingBubble() {
  const div = document.createElement("div");
  div.className = "bubble assistant loading-bubble";
  div.innerHTML = `
    <div class="label">Guide</div>
    <div class="loading-status"></div>
    <div class="loading-bar-wrap">
      <div class="loading-bar-track"><div class="loading-bar"></div></div>
      <span class="loading-pct">0%</span>
    </div>`;
  chatLog.appendChild(div);
  chatLog.scrollTop = chatLog.scrollHeight;

  const statusEl = div.querySelector(".loading-status");
  const barEl = div.querySelector(".loading-bar");
  const pctEl = div.querySelector(".loading-pct");

  let progress = 0;
  let dotCount = 0;

  const timer = setInterval(() => {
    dotCount = (dotCount + 1) % 4;
    const dots = ".".repeat(dotCount);

    if (progress < 40) progress += Math.random() * 4 + 1;
    else if (progress < 75) progress += Math.random() * 2 + 0.5;
    else if (progress < 92) progress += 0.3;
    progress = Math.min(progress, 92);

    const msgs = LOADING_MESSAGES[replyLanguage.value] || LOADING_MESSAGES["한국어"];
    const msgIdx = progress < 35 ? 0 : progress < 70 ? 1 : 2;
    statusEl.textContent = msgs[msgIdx] + dots;
    barEl.style.width = progress + "%";
    pctEl.textContent = Math.floor(progress) + "%";
  }, 250);

  return {
    remove() {
      clearInterval(timer);
      barEl.style.width = "100%";
      pctEl.textContent = "100%";
      statusEl.textContent = replyLanguage.value === "日本語" ? "完了" : "완료";
      setTimeout(() => div.remove(), 300);
    },
  };
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

/** 한국어 조사 선택: 앞 글자 받침 유무에 따라 을/를·이/가·은/는 반환 */
function koreanParticle(word, type) {
  if (!word) return type[1];
  const code = word.charCodeAt(word.length - 1);
  if (code < 0xAC00 || code > 0xD7A3) return type[1];
  return (code - 0xAC00) % 28 !== 0 ? type[0] : type[1];
}

/** keyword("明洞 プール付き ホテル")에서 지역명과 편의시설 분리 */
function parseLodgingKeyword(keyword) {
  const typeWords = ["호텔", "게스트하우스", "모텔", "숙소", "민박", "호스텔",
                     "ホテル", "旅館", "宿", "ゲストハウス", "モーテル", "ホステル"];
  let text = (keyword || "").trim();
  for (const w of typeWords) {
    text = text.replace(new RegExp(w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "g"), "").trim();
  }
  const tokens = text.split(/\s+/).filter(Boolean);
  if (tokens.length === 0) return { area: keyword || "", amenity: "" };
  if (tokens.length === 1) return { area: tokens[0], amenity: "" };
  return { area: tokens[0], amenity: tokens.slice(1).join(" ") };
}

/**
 * Places API 결과를 숙소/장소 카드 HTML로 변환.
 * @param {Array}  places   - NearbyPlace dict 배열
 * @param {string} category - "lodging" | "food" | 기타
 * @param {string} keyword  - 분류기 키워드 (예: "명동 호텔" / "明洞 ホテル")
 * @param {string} lang     - "日本語" | "한국어"
 */
function renderPlaceCards(places, category, keyword, lang) {
  if (!places || places.length === 0) return "";

  const isJa = lang === "日本語";
  const isLodging = category === "lodging";

  // ── 헤더 문장 (언어별) ─────────────────────────────────
  let headerHtml;
  if (isLodging && keyword) {
    const { area, amenity } = parseLodgingKeyword(keyword);
    if (amenity && area) {
      headerHtml = isJa
        ? `<strong>${escapeHtml(area)}</strong>の<strong>${escapeHtml(amenity)}</strong>があるホテルリストです。`
        : `다음은 <strong>${escapeHtml(area)}</strong>의 <strong>${escapeHtml(amenity)}</strong> 포함 추천 숙소 리스트입니다.`;
    } else if (area) {
      headerHtml = isJa
        ? `<strong>${escapeHtml(area)}</strong>周辺のおすすめホテルリストです。`
        : `다음은 <strong>${escapeHtml(area)}</strong>${koreanParticle(area, "을를")} 중심으로 한 추천 숙소 리스트입니다.`;
    } else {
      headerHtml = isJa ? "🏨 おすすめホテル" : "🏨 추천 숙소";
    }
  } else {
    headerHtml = isLodging
      ? (isJa ? "🏨 おすすめホテル" : "🏨 추천 숙소")
      : (isJa ? "📍 周辺スポット"   : "📍 주변 장소");
  }

  const cards = places.slice(0, 5).map((p) => {
    const name = escapeHtml(p.name || "");
    const rating = p.rating ? `★${p.rating.toFixed(1)}` : "";
    const reviews = p.user_rating_count
      ? `<span class="place-reviews">(${p.user_rating_count.toLocaleString()}件)</span>`
      : "";

    let openBadge = "";
    if (p.is_open_now === true) {
      openBadge = `<span class="place-open">${isJa ? "営業中" : "영업중"}</span>`;
    } else if (p.is_open_now === false) {
      openBadge = `<span class="place-closed">${isJa ? "時間外" : "영업종료"}</span>`;
    }

    const priceLabel = p.price_level
      ? `<span class="place-badge price-badge">${escapeHtml(p.price_level)}</span>`
      : "";

    const naverQuery = [p.name, p.address].filter(Boolean).join(" ");
    const naverCoord = p.latitude != null && p.longitude != null
      ? `&lat=${encodeURIComponent(p.latitude)}&lng=${encodeURIComponent(p.longitude)}`
      : "";
    const naverPhotoUrl = p.photo_url || p.naver_photo_url
      || ((p.maps_url || p.google_maps_uri || "").includes("map.naver.com")
        ? `/api/naver-photo/?url=${encodeURIComponent(p.maps_url || p.google_maps_uri)}`
        : "")
      || (naverQuery ? `/api/naver-photo/?q=${encodeURIComponent(naverQuery)}${naverCoord}` : "");
    const thumb = naverPhotoUrl
      ? `<img class="place-thumb" src="${escapeHtml(naverPhotoUrl)}" alt="" loading="lazy" onerror="this.classList.add('place-thumb--fallback')" />`
      : p.photo_name
      ? `<img class="place-thumb" src="/api/photo/?name=${encodeURIComponent(p.photo_name)}" alt="" loading="lazy" onerror="this.classList.add('place-thumb--fallback')" />`
      : `<span class="place-thumb place-thumb--fallback" aria-hidden="true">🏨</span>`;

    const addr = p.address ? `<div class="place-addr">${escapeHtml(p.address)}</div>` : "";
    const mapsHint = p.google_maps_uri ? `<span class="place-maps-hint">Google Maps →</span>` : "";
    const meta = [rating && `<span class="place-rating">${rating} ${reviews}</span>`, openBadge, priceLabel]
      .filter(Boolean)
      .join("");

    const inner = `<div class="place-thumb-wrap">${thumb}</div><div class="place-card-text"><div class="place-name">${name}</div>${meta ? `<div class="place-meta">${meta}</div>` : ""}${addr}${mapsHint}</div>`;
    if (p.google_maps_uri) {
      return `<a class="place-card" href="${escapeHtml(p.google_maps_uri)}" target="_blank" rel="noopener">${inner}</a>`;
    }
    return `<div class="place-card">${inner}</div>`;
  });

  return `<div class="place-cards-section"><div class="place-cards-title">${headerHtml}</div>${cards.join("")}</div>`;
}

/**
 * 한국관광공사 TourAPI (JpnService2) 숙박·축제 카드.
 */
function renderVisitKoreaCards(stays, festivals, attractions, lang) {
  const isJa = lang === "日本語";
  let html = "";

  const buildCards = (items, emoji, showPeriod) => {
    return items.slice(0, 5).map((it) => {
      const name = escapeHtml(it.title || "");
      const addr = it.addr1 ? `<div class="place-addr">${escapeHtml(it.addr1)}</div>` : "";
      const period = showPeriod && it.event_period
        ? `<span class="place-badge">${escapeHtml(it.event_period)}</span>`
        : "";
      const thumb = it.first_image
        ? `<img class="place-thumb" src="${escapeHtml(it.first_image)}" alt="" loading="lazy" onerror="this.classList.add('place-thumb--fallback')" />`
        : `<span class="place-thumb place-thumb--fallback" aria-hidden="true">${emoji}</span>`;
      const uri = it.maps_uri || "";
      const mapsHint = uri ? `<span class="place-maps-hint">Google Maps →</span>` : "";
      const meta = period ? `<div class="place-meta">${period}</div>` : "";
      const inner = `<div class="place-thumb-wrap">${thumb}</div><div class="place-card-text"><div class="place-name">${name}</div>${meta}${addr}${mapsHint}</div>`;
      if (uri) {
        return `<a class="place-card" href="${escapeHtml(uri)}" target="_blank" rel="noopener">${inner}</a>`;
      }
      return `<div class="place-card">${inner}</div>`;
    });
  };

  if (attractions && attractions.length) {
    const title = isJa ? "🗺 観光スポット（韓国観光公社）" : "🗺 관광지 (한국관광공사)";
    html += `<div class="place-cards-section"><div class="place-cards-title">${title}</div>${buildCards(attractions, "🗺", false).join("")}</div>`;
  }
  if (festivals && festivals.length) {
    const title = isJa ? "🎭 イベント・祭り（韓国観光公社）" : "🎭 이벤트·축제 (한국관광공사)";
    html += `<div class="place-cards-section"><div class="place-cards-title">${title}</div>${buildCards(festivals, "🎭", true).join("")}</div>`;
  }
  if (stays && stays.length) {
    const title = isJa ? "🏨 宿泊（韓国観光公社）" : "🏨 숙박 (한국관광공사)";
    html += `<div class="place-cards-section"><div class="place-cards-title">${title}</div>${buildCards(stays, "🏨", false).join("")}</div>`;
  }
  return html;
}

/** 시간 문자열을 HH:MM 형식으로 반환 (HH:MM 직접 또는 ISO 8601 → KST 변환) */
function formatFlightTime(isoStr) {
  if (!isoStr) return "--:--";
  if (/^\d{2}:\d{2}$/.test(isoStr)) return isoStr;
  try {
    const d = new Date(isoStr);
    const utcMs = d.getTime() + d.getTimezoneOffset() * 60000;
    const kst = new Date(utcMs + 9 * 3600000);
    return String(kst.getHours()).padStart(2, "0") + ":" + String(kst.getMinutes()).padStart(2, "0");
  } catch {
    return isoStr.slice(11, 16) || "--:--";
  }
}

const AIRLINE_NAME_JA = {
  "아시아나항공": "アシアナ航空",
  "대한항공": "大韓航空",
  "진에어": "ジンエアー",
  "에어부산": "エアプサン",
  "에어서울": "エアソウル",
  "이스타항공": "イースター航空",
  "제주항공": "チェジュ航空",
  "티웨이항공": "ティーウェイ航空",
  "에어로케이항공": "エアロK",
  "에어프레미아": "エアプレミア",
  "에어프레미아항공": "エアプレミア",
  "플라이강원": "フライ江原",
  "에티오피아항공": "エチオピア航空",
  "파라타항공": "パラタ航空",
  "ZIPAIR": "ZIPAIR",
};

const AIRLINE_CODE_NAME_JA = {
  ET: "エチオピア航空",
};

function displayAirlineName(name, lang = "日本語", code = "") {
  const raw = String(name || "").trim();
  if (lang !== "日本語") return raw;
  const norm = raw.replace(/\s+/g, "");
  return AIRLINE_NAME_JA[raw] || AIRLINE_NAME_JA[norm] || AIRLINE_CODE_NAME_JA[String(code || "").toUpperCase()] || raw;
}

function displayOperatingDays(days, lang = "日本語") {
  let text = String(days || "").trim();
  if (!text || lang !== "日本語") return text;
  const map = { 월: "月", 화: "火", 수: "水", 목: "木", 금: "金", 토: "土", 일: "日" };
  text = text.replace(/[월화수목금토일]/g, (ch) => map[ch] || ch);
  text = text.replace(/매일|매일운항/g, "毎日");
  return text;
}

const FLIGHT_STATUS_LABEL = {
  "日本語": {
    scheduled: "予定", active: "運航中", landed: "到着済み",
    cancelled: "欠航", incident: "事故", diverted: "迂回", unknown: "確認中",
  },
  "한국어": {
    scheduled: "예정", active: "운항중", landed: "도착완료",
    cancelled: "결항", incident: "사고", diverted: "회항", unknown: "확인중",
  },
};

const FLIGHT_STATUS_CLASS = {
  scheduled: "status-scheduled", active: "status-active", landed: "status-landed",
  cancelled: "status-cancelled", incident: "status-incident", diverted: "status-diverted",
};

/**
 * 공연·행사 카드 HTML (gyeonggi_events / KINTEX)
 * @param {Array}  events  - GyeonggiEvent dict 배열
 * @param {string} lang    - "日本語" | "한국어"
 */
function renderGyeonggiEventCards(events, lang) {
  if (!events || !events.length) return "";
  const isJa = lang === "日本語";
  const title = isJa ? "🎪 旅行期間中の公演・行事" : "🎪 여행 기간 중 공연·행사";
  const cards = events.slice(0, 6).map((ev) => {
    const name   = escapeHtml(ev.name || "");
    const period = ev.start_date === ev.end_date
      ? escapeHtml(ev.start_date || "")
      : `${escapeHtml(ev.start_date || "")}〜${escapeHtml(ev.end_date || "")}`;
    const venue  = ev.venue  ? `<div class="ev-venue">${escapeHtml(ev.venue)}</div>` : "";
    const desc   = ev.description
      ? `<div class="ev-desc">${escapeHtml(ev.description.slice(0, 80))}${ev.description.length > 80 ? "…" : ""}</div>`
      : "";
    const _src = ev.source_service || "";
    const source = _src.startsWith("kintex") ? "KINTEX" : _src === "kpop_web" ? "K-pop公演" : "全国イベント";
    const inner  = `<div class="ev-name">${name}</div>
      <div class="ev-meta">${period}${ev.city ? " · " + escapeHtml(ev.city) : ""} <span class="ev-src">${source}</span></div>
      ${venue}${desc}`;
    return ev.url
      ? `<a class="ev-card" href="${escapeHtml(ev.url)}" target="_blank" rel="noopener">${inner}</a>`
      : `<div class="ev-card">${inner}</div>`;
  }).join("");
  return `<div class="ev-section"><h4 class="ev-title">${title}</h4><div class="ev-grid">${cards}</div></div>`;
}

/**
 * 항공편 / 공항 카드 HTML 생성
 * @param {Array}  flights      - FlightInfo dict 배열 (노선/상태)
 * @param {Object} airport      - AirportInfo dict (공항 정보)
 * @param {string} flightSubtype - "route" | "flight_status" | "airport"
 * @param {string} keyword      - 분류기 키워드 (e.g. "route:ICN:NRT")
 * @param {string} lang         - "日本語" | "한국어"
 */
function renderFlightCards(flights, airport, flightSubtype, keyword, lang) {
  const isJa = lang === "日本語";
  const statusLabels = FLIGHT_STATUS_LABEL[lang] || FLIGHT_STATUS_LABEL["한국어"];

  // ── 공항 정보 카드 ──────────────────────────────────────────
  if (flightSubtype === "airport" && airport) {
    const cityLabel = isJa ? "国" : "국가";
    const tzLabel   = isJa ? "タイムゾーン" : "시간대";
    const locLabel  = isJa ? "位置" : "위치";
    const latStr    = airport.latitude  != null ? `${Number(airport.latitude).toFixed(4)}°` : "--";
    const lonStr    = airport.longitude != null ? `${Number(airport.longitude).toFixed(4)}°` : "--";
    return `<div class="flight-cards-section">
  <div class="airport-info-card">
    <div class="airport-name">✈ ${escapeHtml(airport.name)}</div>
    <div class="airport-iata">${escapeHtml(airport.iata)}${airport.icao ? ` · ${escapeHtml(airport.icao)}` : ""}</div>
    <div class="airport-details">
      ${airport.country_name ? `<div>${cityLabel}: ${escapeHtml(airport.country_name)}</div>` : ""}
      ${airport.timezone     ? `<div>${tzLabel}: ${escapeHtml(airport.timezone)}</div>` : ""}
      ${airport.latitude != null ? `<div>${locLabel}: ${latStr}N, ${lonStr}E</div>` : ""}
    </div>
  </div>
</div>`;
  }

  // ── 항공편 리스트 카드 ──────────────────────────────────────
  if (!flights || flights.length === 0) return "";

  // 헤더 생성
  let headerHtml;
  if (flightSubtype === "route" && keyword) {
    const parts = keyword.replace("route:", "").split(":");
    const dep = parts[0] || "?";
    const arr = parts[1] || "?";
    headerHtml = isJa
      ? `<strong>${escapeHtml(dep)}</strong> → <strong>${escapeHtml(arr)}</strong> 運航便`
      : `<strong>${escapeHtml(dep)}</strong> → <strong>${escapeHtml(arr)}</strong> 운항 항공편`;
  } else if (flightSubtype === "flight_status") {
    const fcode = keyword.replace("flight:", "").toUpperCase();
    headerHtml = isJa ? `<strong>${escapeHtml(fcode)}</strong> 便の状況` : `<strong>${escapeHtml(fcode)}</strong> 항공편 현황`;
  } else {
    headerHtml = isJa ? "✈ フライト情報" : "✈ 항공편 정보";
  }

  const depLabel  = isJa ? "出発" : "출발";
  const arrLabel  = isJa ? "到着" : "도착";
  const delayLabel = isJa ? "遅延" : "지연";
  const termLabel  = isJa ? "T" : "T";
  const gateLabel  = isJa ? "G" : "G";
  const noDelayLabel = isJa ? "遅延なし" : "정시";

  const cards = flights.slice(0, 5).map((f) => {
    const statusKey = (f.status || "unknown").toLowerCase();
    const statusText = statusLabels[statusKey] || statusKey;
    const statusCls  = FLIGHT_STATUS_CLASS[statusKey] || "status-unknown";

    const depTime = formatFlightTime(f.dep_scheduled);
    const arrTime = formatFlightTime(f.arr_scheduled);
    const depTermGate = [
      f.dep_terminal ? `${termLabel}${escapeHtml(f.dep_terminal)}` : "",
      f.dep_gate     ? `${gateLabel}${escapeHtml(f.dep_gate)}` : "",
    ].filter(Boolean).join(" ");
    const arrTermGate = f.arr_terminal ? `${termLabel}${escapeHtml(f.arr_terminal)}` : "";

    const delayHtml = (f.dep_delay && f.dep_delay > 0)
      ? `<div class="flight-delay">⚠ ${delayLabel} +${f.dep_delay}${isJa ? "分" : "분"}</div>`
      : "";

    const codeshareHtml = f.codeshared_iata
      ? `<span class="flight-codeshare">${escapeHtml(f.codeshared_iata)}</span>`
      : "";

    // 정기편 스케줄 전용 메타정보 (운항요일 / 기간)
    const days = displayOperatingDays(f.operating_days || "", lang);
    const daysLabel = isJa ? "運航曜日" : "운항요일";
    const periodLabel = isJa ? "運航期間" : "운항기간";
    const daysHtml = days
      ? `<div class="flight-schedule-meta">${daysLabel}: ${escapeHtml(days)}</div>`
      : "";
    const periodHtml = (f.schedule_start || f.schedule_end)
      ? `<div class="flight-schedule-meta">${periodLabel}: ${escapeHtml(f.schedule_start || "?")} ~ ${escapeHtml(f.schedule_end || "?")}</div>`
      : "";

    return `<div class="flight-card">
  <div class="flight-card-header">
    <span class="flight-airline">${escapeHtml(displayAirlineName(f.airline_name, lang, f.airline_iata))}</span>
    <span class="flight-num">${escapeHtml(f.flight_iata)}</span>
    ${codeshareHtml}
    <span class="flight-status-badge ${statusCls}">${statusText}</span>
  </div>
  <div class="flight-route-row">
    <div class="flight-endpoint">
      <div class="flight-iata-code">${escapeHtml(f.dep_iata)}</div>
      <div class="flight-time">${depTime}</div>
      ${depTermGate ? `<div class="flight-terminal">${depTermGate}</div>` : ""}
    </div>
    <div class="flight-arrow">✈</div>
    <div class="flight-endpoint flight-endpoint--arr">
      <div class="flight-iata-code">${escapeHtml(f.arr_iata)}</div>
      <div class="flight-time">${arrTime}</div>
      ${arrTermGate ? `<div class="flight-terminal">${arrTermGate}</div>` : ""}
    </div>
  </div>
  ${delayHtml}${daysHtml}${periodHtml}
</div>`;
  });

  return `<div class="flight-cards-section">
  <div class="flight-cards-title">${headerHtml}</div>
  ${cards.join("")}
</div>`;
}

async function fetchHealth() {
  try {
    const r = await fetch("/api/health/");
    const j = await r.json();
    healthStatus.textContent = j.openai_configured
      ? `API: 接続済み（OpenAI キーあり / ${j.vector_backend || "faiss"}）`
      : `API: 接続済み（OpenAI キーなし / ${j.vector_backend || "faiss"}）`;
  } catch {
    healthStatus.textContent = "API: 未接続";
    healthStatus.classList.add("error");
  }
}

messageInput.addEventListener("compositionstart", () => {
  isComposing = true;
});

messageInput.addEventListener("compositionend", () => {
  isComposing = false;
});

messageInput.addEventListener("keydown", (e) => {
  if (e.key !== "Enter" || e.shiftKey) return;
  if (e.isComposing || isComposing) return;

  e.preventDefault();
  if (!btnSend.disabled) {
    chatForm.requestSubmit();
  }
});

function retryLastMessage() {
  if (!_lastFailedText) return;
  messageInput.value = _lastFailedText;
  chatForm.requestSubmit();
}

// ── suggestion chip 초기화 ───────────────────────────────────────────────
const suggestionsEl = document.getElementById("suggestions");

function hideSuggestions() {
  if (suggestionsEl) suggestionsEl.classList.add("hidden");
}

if (suggestionsEl) {
  suggestionsEl.querySelectorAll(".suggestion-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      const msg = btn.dataset.msg;
      if (!msg) return;
      messageInput.value = msg;
      chatForm.requestSubmit();
    });
  });
}

// ── SSE 파싱 헬퍼 ────────────────────────────────────────────────────────
function* parseSseLines(lines) {
  for (const line of lines) {
    if (!line.startsWith("data: ")) continue;
    try { yield JSON.parse(line.slice(6)); } catch { /* skip malformed */ }
  }
}

// ── 버블 collapse 적용 (스트리밍 완료 후 호출) ───────────────────────────
function applyCollapse(bubble, bodyEl, isJa) {
  if (!bodyEl || bodyEl.scrollHeight <= COLLAPSE_HEIGHT) return;
  bodyEl.classList.add("collapsed");
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "expand-btn";
  const txtMore = isJa ? "もっと見る ▼" : "더 보기 ▼";
  const txtLess = isJa ? "折りたたむ ▲" : "접기 ▲";
  btn.textContent = txtMore;
  btn.addEventListener("click", () => {
    const collapsed = bodyEl.classList.toggle("collapsed");
    btn.textContent = collapsed ? txtMore : txtLess;
  });
  const translation = bubble.querySelector(".translation");
  if (translation) bubble.insertBefore(btn, translation);
  else bubble.appendChild(btn);
}

// ── 메인 submit 핸들러 (streaming) ──────────────────────────────────────
chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = messageInput.value.trim();
  if (!text) return;

  hideSuggestions();
  appendBubble("user", text);
  messageInput.value = "";
  btnSend.disabled = true;
  _lastFailedText = null;

  const loading = appendLoadingBubble();
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 90000);
  const isJa = replyLanguage.value === "日本語";

  // streaming 버블용 상태
  let assistantBubble = null;
  let replyBodyEl = null;
  let replyText = "";
  let metaData = null;

  try {
    const res = await fetch("/api/chat/stream/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
      credentials: "same-origin",
      body: JSON.stringify({
        message: text,
        reply_language: replyLanguage.value,
        session_id: sessionId,
        history: history.map(({ role, content }) => ({ role, content })),
      }),
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      loading.remove();
      appendBubble("assistant", errData.detail || `HTTP ${res.status}`);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let sseBuffer = "";

    loading.remove();

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      sseBuffer += decoder.decode(value, { stream: true });
      const lines = sseBuffer.split("\n");
      sseBuffer = lines.pop(); // 마지막 불완전 줄 보존

      for (const payload of parseSseLines(lines)) {
        if (payload.type === "meta") {
          metaData = payload;
          if (payload.session_id) sessionId = payload.session_id;
          console.log("[stream] category:", payload.category,
                      "| keyword:", payload.keyword,
                      "| places:", payload.places_count);

          // 카드 렌더링
          let extra = "";
          const hasPlaceCards = payload.places && payload.places.length > 0;
          const hasVkCards = (payload.visitkorea_stays && payload.visitkorea_stays.length > 0) ||
            (payload.visitkorea_festivals && payload.visitkorea_festivals.length > 0) ||
            (payload.visitkorea_attractions && payload.visitkorea_attractions.length > 0);
          const hasFlightCards = (payload.flights && payload.flights.length > 0) || payload.airport;
          const hasEventCards = payload.gyeonggi_events && payload.gyeonggi_events.length > 0;
          const hasTicketCards = payload.ticket_platform_events && payload.ticket_platform_events.length > 0;

          if (hasPlaceCards)
            extra += renderPlaceCards(payload.places, payload.category || "", payload.keyword || "", replyLanguage.value);
          if (hasVkCards)
            extra += renderVisitKoreaCards(payload.visitkorea_stays || [], payload.visitkorea_festivals || [], payload.visitkorea_attractions || [], replyLanguage.value);
          if (hasEventCards)
            extra += renderGyeonggiEventCards(payload.gyeonggi_events, replyLanguage.value);
          if (hasTicketCards)
            extra += renderTicketPlatformCards(payload.ticket_platform_events, replyLanguage.value);
          if (hasFlightCards)
            extra += renderFlightCards(payload.flights || [], payload.airport || null, payload.flight_subtype || "", payload.keyword || "", replyLanguage.value);

          // 버블 생성 (본문은 스트리밍으로 채워짐)
          assistantBubble = document.createElement("div");
          assistantBubble.className = "bubble assistant";
          assistantBubble.innerHTML =
            `<div class="label">Guide</div><div class="bubble-body bubble-streaming"></div>${extra}`;
          chatLog.appendChild(assistantBubble);
          replyBodyEl = assistantBubble.querySelector(".bubble-body");
          chatLog.scrollTop = chatLog.scrollHeight;

        } else if (payload.type === "token") {
          replyText += payload.delta;
          if (replyBodyEl) {
            replyBodyEl.textContent = replyText;
            chatLog.scrollTop = chatLog.scrollHeight;
          }

        } else if (payload.type === "done") {
          if (replyBodyEl) {
            replyBodyEl.classList.remove("bubble-streaming");
            // ticket link 렌더링
            const inlineTickets = window.LinkPreview && LinkPreview.extractTicketUrls(replyText).length > 0;
            if (inlineTickets) {
              replyBodyEl.innerHTML = formatReplyWithTicketPreviews(replyText);
              const ticketIdx = LinkPreview.buildEventIndex(
                (metaData && metaData.ticket_platform_events) || []
              );
              LinkPreview.hydrate(assistantBubble, ticketIdx);
            }
            requestAnimationFrame(() => applyCollapse(assistantBubble, replyBodyEl, isJa));
          }
          if (payload.translated_ko && assistantBubble) {
            const t = document.createElement("div");
            t.className = "translation";
            t.innerHTML = `<h4>韓国語訳</h4>${escapeHtml(payload.translated_ko)}`;
            assistantBubble.appendChild(t);
          }
          chatLog.scrollTop = chatLog.scrollHeight;

        } else if (payload.type === "error") {
          if (assistantBubble && replyBodyEl) {
            replyBodyEl.classList.remove("bubble-streaming");
            replyBodyEl.textContent = payload.message || "Error";
          } else {
            appendBubble("assistant", payload.message || "Error");
          }
        }
      }
    }

    // 이력 업데이트
    const hasPlaceCards = metaData && metaData.places && metaData.places.length > 0;
    const hasVkCards = metaData && (
      (metaData.visitkorea_stays && metaData.visitkorea_stays.length > 0) ||
      (metaData.visitkorea_festivals && metaData.visitkorea_festivals.length > 0) ||
      (metaData.visitkorea_attractions && metaData.visitkorea_attractions.length > 0)
    );
    const hasFlightCards = metaData && ((metaData.flights && metaData.flights.length > 0) || metaData.airport);

    history.push({ role: "user", content: text });
    history.push({
      role: "assistant",
      content: hasPlaceCards || hasVkCards
        ? "(venue cards shown)"
        : hasFlightCards
          ? "(flight cards shown)"
          : replyText,
    });
    if (history.length > 40) history = history.slice(-40);

    if (!assistantBubble && !replyText) {
      const fallback = isJa
        ? "申し訳ありません、応答を生成できませんでした。もう一度お試しください。"
        : "죄송합니다, 응답을 생성하지 못했습니다. 다시 시도해 주세요.";
      appendBubble("assistant", fallback);
    }

  } catch (err) {
    clearTimeout(timeoutId);
    if (replyBodyEl) replyBodyEl.classList.remove("bubble-streaming");
    if (!assistantBubble) loading.remove();
    _lastFailedText = text;
    const errMsg = err.name === "AbortError"
      ? (isJa
          ? "応答がタイムアウトしました（90秒）。サーバーが混み合っています。"
          : "응답 시간이 초과되었습니다(90초). 잠시 후 다시 시도해 주세요.")
      : (isJa
          ? "サーバーへの接続に失敗しました。サーバーが起動しているか確認してください。"
          : "서버 연결에 실패했습니다. 서버가 실행 중인지 확인해 주세요.");
    const retryLabel = isJa ? "↩ 再試行" : "↩ 다시 시도";
    if (assistantBubble && replyBodyEl) {
      replyBodyEl.textContent = errMsg;
      assistantBubble.appendChild(
        Object.assign(document.createElement("button"), {
          className: "retry-btn",
          textContent: retryLabel,
          onclick: retryLastMessage,
        })
      );
    } else {
      appendBubble("assistant", errMsg,
        `<button class="retry-btn" onclick="retryLastMessage()">${retryLabel}</button>`);
    }
    console.error("[chat] stream error:", err);
  } finally {
    btnSend.disabled = false;
    messageInput.focus();
  }
});

btnReset.addEventListener("click", () => {
  history = [];
  sessionId = null;
  chatLog.innerHTML = "";
  if (suggestionsEl) suggestionsEl.classList.remove("hidden");
});

fetchHealth();
