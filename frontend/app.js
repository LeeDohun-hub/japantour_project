/**
 * Django `/api/chat/` と会話。同一オリジン前提（runserver）。
 */
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

const COLLAPSE_HEIGHT = 240;

function appendBubble(role, content, extraHtml = "") {
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  const label = role === "user" ? "You" : "Guide";
  // Guide: 본문만 접기(번역·버튼은 항상 표시). You: 기존과 동일.
  if (role === "assistant") {
    const bodyPart = content
      ? `<div class="bubble-body">${escapeHtml(content)}</div>`
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

    const thumb = p.photo_name
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

/** ISO 8601 시간을 KST/JST (UTC+9) HH:MM 로 변환 */
function formatFlightTime(isoStr) {
  if (!isoStr) return "--:--";
  try {
    const d = new Date(isoStr);
    const utcMs = d.getTime() + d.getTimezoneOffset() * 60000;
    const kst = new Date(utcMs + 9 * 3600000);
    return String(kst.getHours()).padStart(2, "0") + ":" + String(kst.getMinutes()).padStart(2, "0");
  } catch {
    return (isoStr.slice(11, 16)) || "--:--";
  }
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

  const depLabel  = isJa ? "출발" : "출발";
  const arrLabel  = isJa ? "도착" : "도착";
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
      ? `<div class="flight-delay">⚠ ${delayLabel} +${f.dep_delay}분</div>`
      : "";

    const codeshareHtml = f.codeshared_iata
      ? `<span class="flight-codeshare">${escapeHtml(f.codeshared_iata)}</span>`
      : "";

    return `<div class="flight-card">
  <div class="flight-card-header">
    <span class="flight-airline">${escapeHtml(f.airline_name)}</span>
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
  ${delayHtml}
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

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = messageInput.value.trim();
  if (!text) return;

  appendBubble("user", text);
  messageInput.value = "";
  btnSend.disabled = true;

  const loading = appendLoadingBubble();

  try {
    const res = await fetch("/api/chat/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        reply_language: replyLanguage.value,
        session_id: sessionId,
        history: history.map(({ role, content }) => ({ role, content })),
      }),
    });
    const data = await res.json().catch(() => ({}));
    loading.remove();
    // 진단 로그 — 원인 파악 후 제거
    console.log("[chat] category:", data.category, "| keyword:", data.keyword,
                "| places_count:", data.places_count, "| places_error:", data.places_error || "(none)");
    if (!res.ok) {
      appendBubble("assistant", data.detail || `HTTP ${res.status}`);
      return;
    }
    if (data.session_id) {
      sessionId = data.session_id;
    }

    let extra = "";
    const hasPlaceCards = data.places && data.places.length > 0;
    const hasFlightCards = (data.flights && data.flights.length > 0) || data.airport;
    if (hasPlaceCards) {
      extra += renderPlaceCards(data.places, data.category || "", data.keyword || "", replyLanguage.value);
    }
    if (hasFlightCards) {
      extra += renderFlightCards(
        data.flights || [],
        data.airport || null,
        data.flight_subtype || "",
        data.keyword || "",
        replyLanguage.value,
      );
    }
    if (data.translated_ko) {
      extra += `<div class="translation"><h4>한국어 번역</h4>${escapeHtml(data.translated_ko)}</div>`;
    }
    const displayReply = (hasPlaceCards || hasFlightCards) ? "" : (data.reply || "");
    appendBubble("assistant", displayReply, extra);

    history.push({ role: "user", content: text });
    history.push({
      role: "assistant",
      content: hasPlaceCards
        ? "(place cards shown)"
        : hasFlightCards
          ? "(flight cards shown)"
          : (data.reply || ""),
    });
    if (history.length > 40) {
      history = history.slice(-40);
    }
  } catch (err) {
    loading.remove();
    appendBubble("assistant", String(err));
  } finally {
    btnSend.disabled = false;
    messageInput.focus();
  }
});

btnReset.addEventListener("click", () => {
  history = [];
  sessionId = null;
  chatLog.innerHTML = "";
});

fetchHealth();
