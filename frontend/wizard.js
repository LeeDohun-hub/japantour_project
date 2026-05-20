/* Korea Travel Wizard — single-page 9-step flow */

const TOTAL_STEPS = 8;
let currentStep = 1;
let currentUser = null;
let wizardData = {};
/** @type {{ name?: string, address?: string, latitude?: number, longitude?: number, maps_url?: string } | null} */
let _selectedAccomPlace = null;

const $ = (id) => document.getElementById(id);
const wizFill    = $("wizFill");
const wizStepsRow = $("wizStepsRow");
const wizNavBar  = $("wizNavBar");
const wizBtnBack = $("wizBtnBack");
const wizBtnNext = $("wizBtnNext");

const STEP_LABELS = ["ログイン","フライト","宿泊","交通","観光","予算","詳細","プラン"];

// ── INIT ──────────────────────────────────────────────────────────────────
async function init() {
  buildStepDots();
  setupStep1();
  setupStep2();
  setupStep3();
  setupChipGroup("transportChips",       false);
  setupChipGroup("regionChips",          false);
  setupChipGroup("activityChips",        false);
  setupChipGroup("budgetPriorityChips",  false);
  setupChipGroup("budgetStyleChips",     true);
  setupChipGroup("companionChips",       true);
  setupChipGroup("mobilityChips",        true);
  setupChipGroup("foodRestrictionChips", false);
  setupChipGroup("paceChips",            true);
  setupChipGroup("hallyuChips",          false);
  setupChipGroup("languageChips",        true);
  setupChipGroup("sportsChips",          false);
  setupStep6();
  setupNavigation();
  setupTransportInfo();
  setupAddrDropdown();
  setupUndecidedAddrDropdown();
  setupHotelManualSearch();
  setupAccomSearch();
  setupAccomDetailSearch();
  setupSportsDetailToggle();

  const params = new URLSearchParams(location.search);
  const oauthError = params.get("oauth_error") === "1";
  const oauthSuccess = params.get("oauth_success") === "1";
  if (oauthError) {
    const el = $("oauthErrorMsg");
    if (el) el.style.display = "block";
  }
  if (oauthError || oauthSuccess) {
    history.replaceState(null, "", location.pathname + (location.hash || ""));
  }

  await checkAuthState();
  if (currentUser && oauthSuccess) {
    goToStep(2);
  } else {
    goToStep(1);
  }
}

// ── STEP DOTS ─────────────────────────────────────────────────────────────
function buildStepDots() {
  wizStepsRow.innerHTML = STEP_LABELS.map((label, i) => `
    <div class="wiz-dot" data-step="${i + 1}" style="cursor:pointer">
      <div class="wiz-dot-circle">${i + 1}</div>
      <div class="wiz-dot-label">${label}</div>
    </div>`).join("");

  wizStepsRow.addEventListener("click", (e) => {
    const dot = e.target.closest(".wiz-dot");
    if (!dot) return;
    const target = +dot.dataset.step;
    if (target < currentStep) goToStep(target);
  });
}

// ── NAVIGATION ────────────────────────────────────────────────────────────
function goToStep(step) {
  currentStep = step;

  document.querySelectorAll(".wiz-card").forEach((card) => {
    const s = +card.dataset.step;
    card.classList.remove("active", "slide-prev", "slide-next");
    if (s === step)       card.classList.add("active");
    else if (s < step)    card.classList.add("slide-prev");
    else                  card.classList.add("slide-next");
  });

  const pct = ((step - 1) / (TOTAL_STEPS - 1)) * 100;
  wizFill.style.width = pct + "%";

  document.querySelectorAll(".wiz-dot").forEach((dot) => {
    const s = +dot.dataset.step;
    dot.classList.toggle("active", s === step);
    dot.classList.toggle("done",   s < step);
  });

  wizBtnBack.style.visibility = step > 1 && step < TOTAL_STEPS ? "visible" : "hidden";

  if (step === TOTAL_STEPS) {
    wizNavBar.style.display = "none";
    generatePlan();
  } else {
    wizNavBar.style.display = "flex";
    wizBtnNext.textContent = step === TOTAL_STEPS - 1 ? "プランを生成 ✨" : "次へ";
  }

  if (step === 5) {
    const regionIn = $("regionCitiesInput");
    if (regionIn) regionIn.value = wizardData.regionCities || "";
  }

  window.scrollTo(0, 0);
}

function setupNavigation() {
  wizBtnNext.addEventListener("click", () => {
    if (validate(currentStep)) {
      collect(currentStep);
      goToStep(currentStep + 1);
    }
  });

  wizBtnBack.addEventListener("click", () => {
    if (currentStep > 1) goToStep(currentStep - 1);
  });

  $("btnGuest")?.addEventListener("click", () => {
    wizardData.isGuest = true;
    goToStep(2);
  });

  $("btnRestart")?.addEventListener("click", () => {
    wizardData = {};
    _selectedAccomPlace = null;
    const regionIn = $("regionCitiesInput");
    if (regionIn) regionIn.value = "";
    goToStep(1);
  });
}

// ── VALIDATION ────────────────────────────────────────────────────────────
function validate(step) {
  if (step === 2) {
    const errArr = $("flightSelError");
    const errRet = $("flightReturnSelError");
    if (!wizardData.flight?.selected) {
      if (errArr) errArr.style.display = "block";
      return false;
    }
    if (errArr) errArr.style.display = "none";

    if (!wizardData.flight?.selectedReturn) {
      if (errRet) errRet.style.display = "block";
      return false;
    }
    if (errRet) errRet.style.display = "none";
  }
  if (step === 6) {
    const total = $("budgetTotal").value;
    const errEl = $("budgetTotalError");
    if (!total || +total <= 0) {
      errEl.textContent = "総予算を入力してください";
      $("budgetTotal").focus();
      return false;
    }
    errEl.textContent = "";
  }
  return true;
}

// ── DATA COLLECTION ───────────────────────────────────────────────────────
function calcNights(departStr, returnStr) {
  if (!departStr || !returnStr) return { nights: 0, days: 0 };
  const diff = new Date(returnStr) - new Date(departStr);
  const nights = Math.max(0, Math.round(diff / 86400000));
  return { nights, days: nights + 1 };
}

function collect(step) {
  switch (step) {
    case 2: {
      const { nights, days } = calcNights($("flightDepart").value, $("flightReturn").value);
      const prevSelected = wizardData.flight?.selected;
      const prevReturn   = wizardData.flight?.selectedReturn;
      wizardData.flight = {
        from:       $("flightFrom").value,
        to:         $("flightTo").value,
        depart:     $("flightDepart").value,
        returnDate: $("flightReturn").value,
        passengers: +$("passengerStepper").querySelector(".step-val").textContent || 1,
        ...(prevSelected && { selected: prevSelected }),
        ...(prevReturn && { selectedReturn: prevReturn }),
      };
      wizardData.nights = nights;
      wizardData.days   = days;
      break;
    }
    case 3: {
      const sel = document.querySelector("#accomOptions .option-card.selected");
      const accomType = sel?.dataset.val || "";
      const lat =
        _selectedHotel?.latitude ?? _selectedAccomPlace?.latitude ?? null;
      const lng =
        _selectedHotel?.longitude ?? _selectedAccomPlace?.longitude ?? null;
      wizardData.accommodation = {
        type:    accomType,
        name:    $("accomName")?.value    || (_selectedHotel?.name || ""),
        address: $("accomAddress")?.value || (_selectedHotel?.address || ""),
        detail:  ($("accomDetailManual")?.value || "").trim(),
        region:  _buildAccomBase() || "",
        ...(lat != null && lng != null ? { latitude: lat, longitude: lng } : {}),
        ...(accomType === "undecided" && _selectedHotel ? { selectedHotel: _selectedHotel } : {}),
        ...(_selectedAccomPlace && accomType !== "undecided"
          ? { selectedPlace: _selectedAccomPlace }
          : {}),
      };
      break;
    }
    case 4:
      wizardData.transport = chips("transportChips");
      break;
    case 5: {
      wizardData.regions    = chips("regionChips");
      const regionCities = ($("regionCitiesInput")?.value || "").trim();
      if (regionCities) wizardData.regionCities = regionCities;
      else delete wizardData.regionCities;
      wizardData.activities = chips("activityChips");
      wizardData.sports     = chips("sportsChips");
      if (wizardData.activities.includes("sports") && !wizardData.sports.length) {
        wizardData.sports = ["sports"];
      }
      break;
    }
    case 6:
      wizardData.budget = {
        currency: $("budgetCurrency").value,
        total:    $("budgetTotal").value,
        daily:    $("budgetDaily").value,
        priority: chips("budgetPriorityChips"),
        style:    chips("budgetStyleChips")[0] || "",
      };
      break;
    case 7:
      wizardData.additional = {
        companion:        chips("companionChips")[0]  || "",
        mobility:         chips("mobilityChips")[0]   || "",
        foodRestrictions: chips("foodRestrictionChips"),
        pace:             chips("paceChips")[0]        || "",
        hallyu:           chips("hallyuChips"),
        language:         chips("languageChips")[0]   || "jp_first",
        note:             $("additionalNote")?.value  || "",
      };
      break;
  }
}

function chips(id) {
  return Array.from(
    document.querySelectorAll(`#${id} .chip.selected`)
  ).map((c) => c.dataset.val);
}

// ── STEP 1: AUTH ──────────────────────────────────────────────────────────
function setupStep1() {
  $("btnLogout")?.addEventListener("click", handleLogout);
  $("btnNavLogout")?.addEventListener("click", handleLogout);

  $("step1Form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = $("s1Username").value.trim();
    const password = $("s1Password").value;
    const errEl = $("s1Error");
    errEl.textContent = "";
    try {
      const res  = await fetch("/api/auth/login/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (!res.ok) { errEl.textContent = data.detail || "ログイン失敗"; return; }
      setLoggedIn(data.user);
      goToStep(2);
    } catch { errEl.textContent = "ネットワークエラー"; }
  });

  $("s1BtnSignup")?.addEventListener("click", async () => {
    const username = $("s1Username").value.trim();
    const password = $("s1Password").value;
    const errEl = $("s1Error");
    errEl.textContent = "";
    if (!username || password.length < 8) {
      errEl.textContent = "ユーザー名と8文字以上のパスワードを入力してください";
      return;
    }
    try {
      const res  = await fetch("/api/auth/register/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (!res.ok) { errEl.textContent = data.detail || "登録失敗"; return; }
      setLoggedIn(data.user);
      goToStep(2);
    } catch { errEl.textContent = "ネットワークエラー"; }
  });
}

function _displayName(user) {
  return (user.display_name || user.username || "ゲスト").trim();
}

function setLoggedIn(user) {
  currentUser = user;
  wizardData.user = user;
  const name = _displayName(user);
  $("authSection").style.display = "none";
  $("loggedInSection").style.display = "block";
  $("s1Avatar").textContent = name[0].toUpperCase();
  $("s1Name").textContent = `${name} さん`;
  const lbl = $("navUserLabel");
  if (lbl) lbl.textContent = name;
  const navLogout = $("btnNavLogout");
  if (navLogout) navLogout.style.display = "inline-flex";
}

async function handleLogout() {
  try {
    await fetch("/api/auth/logout/", { method: "POST" });
  } catch (_) {}
  currentUser = null;
  delete wizardData.user;
  // UI 리셋
  const authSec = $("authSection");
  const loggedSec = $("loggedInSection");
  if (authSec) authSec.style.display = "block";
  if (loggedSec) loggedSec.style.display = "none";
  const lbl = $("navUserLabel");
  if (lbl) lbl.textContent = "";
  const navLogout = $("btnNavLogout");
  if (navLogout) navLogout.style.display = "none";
  goToStep(1);
}

async function checkAuthState() {
  try {
    const res = await fetch("/api/auth/me/", { credentials: "same-origin" });
    if (res.ok) {
      const data = await res.json();
      if (data.authenticated) setLoggedIn(data.user);
    }
  } catch { /* ignore */ }
}

// ── STEP 2: FLIGHTS ───────────────────────────────────────────────────────
let _flightFetchTimer = null;
let _returnFlightFetchTimer = null;
let _allFlights = [];
let _allReturnFlights = [];
let _flightPage = 0;
let _returnFlightPage = 0;
let _fetchGen = 0;
let _returnFetchGen = 0;
const FLIGHTS_PER_PAGE = 10;
let _allHotels = [];
let _hotelPage = 0;
let _hotelArea = "";
let _hotelSearchMode = "recommend"; // "recommend" | "manual"
let _selectedHotel = null;          // hotel chosen while in undecided mode
const HOTELS_PER_PAGE = 5;

function setupStep2() {
  const depart = $("flightDepart");
  const ret    = $("flightReturn");

  if (depart) {
    const d = new Date();
    d.setMonth(d.getMonth() + 1);
    depart.value = fmtDate(d);
  }
  if (ret) {
    const r = new Date();
    r.setMonth(r.getMonth() + 1);
    r.setDate(r.getDate() + 4);
    ret.value = fmtDate(r);
  }

  let pax = 1;
  $("passengerStepper")?.addEventListener("click", (e) => {
    const action = e.target.closest(".step-btn")?.dataset.action;
    if (action === "inc" && pax < 10) pax++;
    if (action === "dec" && pax > 1)  pax--;
    $("passengerStepper").querySelector(".step-val").textContent = pax;
  });

  // 출발·도착 교체 버튼
  $("swapFlightRoute")?.addEventListener("click", () => {
    const from = $("flightFrom");
    const to   = $("flightTo");
    const tmp  = from.value;
    from.value = to.value;
    to.value   = tmp;
    clearTimeout(_flightFetchTimer);
    clearTimeout(_returnFlightFetchTimer);
    _flightFetchTimer = setTimeout(fetchFlightList, 100);
    _returnFlightFetchTimer = setTimeout(fetchReturnFlightList, 100);
  });

  ["flightFrom", "flightTo", "flightDepart"].forEach((id) => {
    $(id)?.addEventListener("change", () => {
      clearTimeout(_flightFetchTimer);
      _flightFetchTimer = setTimeout(fetchFlightList, 300);
    });
  });

  $("flightReturn")?.addEventListener("change", () => {
    clearTimeout(_returnFlightFetchTimer);
    _returnFlightFetchTimer = setTimeout(fetchReturnFlightList, 300);
  });

  fetchFlightList();
  fetchReturnFlightList();
}

async function fetchFlightList() {
  const dep  = ($("flightFrom")?.value || "").trim();
  const arr  = ($("flightTo")?.value  || "ICN").trim();
  const date = $("flightDepart")?.value || "";
  const section = $("flightListSection");
  const cards   = $("flightListCards");
  const label   = $("flightListLabel");
  const spinner = $("flightListLoading");
  const pager   = $("flightListPager");
  if (!section || !cards) return;

  // Guard: dep must be selected before fetching
  if (!dep) {
    section.style.display = "block";
    label.textContent = "출발지를 선택해주세요";
    cards.innerHTML = "";
    if (pager) pager.style.display = "none";
    return;
  }

  // Increment generation so any in-flight request becomes stale
  const gen = ++_fetchGen;

  section.style.display = "block";
  if (pager) pager.style.display = "none";
  spinner.style.display = "inline";
  label.textContent = `${dep} → ${arr} 항공편 조회 중…`;
  cards.innerHTML = "";
  _allFlights = [];
  _flightPage = 0;

  try {
    const qs  = new URLSearchParams({ dep, arr, ...(date && { date }) });
    const res = await fetch(`/api/flights/?${qs}`);
    const data = await res.json();

    // Discard if a newer fetch was started while we awaited
    if (gen !== _fetchGen) return;

    if (!res.ok || data.error) throw new Error(data.error || "조회 실패");

    _allFlights = data.flights || [];
    label.textContent = `${dep} → ${arr}  ${date || "오늘"}  총 ${_allFlights.length}편`;
    if (_allFlights.length === 0) {
      cards.innerHTML = `<p class="flight-list-empty">해당 노선·날짜의 항공편 정보가 없습니다.</p>`;
      return;
    }
    renderFlightPage(0);
    setupPager();
  } catch (err) {
    if (gen !== _fetchGen) return;
    label.textContent = "조회 실패";
    cards.innerHTML = `<p class="flight-list-empty">${err.message}</p>`;
  } finally {
    if (gen === _fetchGen) spinner.style.display = "none";
  }
}

async function fetchReturnFlightList() {
  const dep  = ($("flightTo")?.value || "ICN").trim();
  const arr  = ($("flightFrom")?.value || "").trim();
  const date = $("flightReturn")?.value || "";
  const section = $("returnFlightListSection");
  const cards   = $("returnFlightListCards");
  const label   = $("returnFlightListLabel");
  const spinner = $("returnFlightListLoading");
  const pager   = $("returnFlightListPager");
  if (!section || !cards) return;

  if (!arr) {
    section.style.display = "block";
    label.textContent = "帰国先（出発地）を選択してください";
    cards.innerHTML = "";
    if (pager) pager.style.display = "none";
    return;
  }

  const gen = ++_returnFetchGen;

  section.style.display = "block";
  if (pager) pager.style.display = "none";
  spinner.style.display = "inline";
  label.textContent = `${dep} → ${arr} 帰国便 照会中…`;
  cards.innerHTML = "";
  _allReturnFlights = [];
  _returnFlightPage = 0;

  try {
    const qs = new URLSearchParams({ dep, arr, ...(date && { date }) });
    const res = await fetch(`/api/flights/?${qs}`);
    const data = await res.json();

    if (gen !== _returnFetchGen) return;

    if (!res.ok || data.error) throw new Error(data.error || "조회 실패");

    _allReturnFlights = data.flights || [];
    label.textContent = `${dep} → ${arr}  ${date || "帰国日"}  計${_allReturnFlights.length}便`;
    if (_allReturnFlights.length === 0) {
      cards.innerHTML =
        `<p class="flight-list-empty">該当する帰国便がありません。帰国日または路線を変更してください。</p>`;
      return;
    }
    renderReturnFlightPage(0);
    setupReturnPager();
  } catch (err) {
    if (gen !== _returnFetchGen) return;
    label.textContent = "照会失敗";
    cards.innerHTML = `<p class="flight-list-empty">${err.message}</p>`;
  } finally {
    if (gen === _returnFetchGen) spinner.style.display = "none";
  }
}

function renderFlightPage(page) {
  const cards = $("flightListCards");
  if (!cards) return;
  const start = page * FLIGHTS_PER_PAGE;
  const slice = _allFlights.slice(start, start + FLIGHTS_PER_PAGE);
  cards.innerHTML = slice
    .map((f, i) => renderFlightSelectCard(f, start + i, "arrival"))
    .join("");
  cards.querySelectorAll(".flight-sel-card").forEach((el) => {
    el.addEventListener("click", () => selectFlight(el, _allFlights[+el.dataset.idx]));
  });
  // 이미 선택된 편명 유지 표시
  const sel = wizardData.flight?.selected;
  if (sel) {
    cards.querySelectorAll(".flight-sel-card").forEach((el) => {
      if (_allFlights[+el.dataset.idx]?.flight_iata === sel.flight_iata)
        el.classList.add("selected");
    });
  }
  // 페이저 상태 업데이트
  const totalPages = Math.ceil(_allFlights.length / FLIGHTS_PER_PAGE);
  const info = $("flightPageInfo");
  if (info) info.textContent = `${page + 1} / ${totalPages}`;
  $("flightPagePrev").disabled = page === 0;
  $("flightPageNext").disabled = page >= totalPages - 1;
}

function renderReturnFlightPage(page) {
  const cards = $("returnFlightListCards");
  if (!cards) return;
  const start = page * FLIGHTS_PER_PAGE;
  const slice = _allReturnFlights.slice(start, start + FLIGHTS_PER_PAGE);
  cards.innerHTML = slice
    .map((f, i) => renderFlightSelectCard(f, start + i, "departure"))
    .join("");
  cards.querySelectorAll(".flight-sel-card").forEach((el) => {
    el.addEventListener("click", () =>
      selectReturnFlight(el, _allReturnFlights[+el.dataset.idx])
    );
  });
  const sel = wizardData.flight?.selectedReturn;
  if (sel) {
    cards.querySelectorAll(".flight-sel-card").forEach((el) => {
      if (_allReturnFlights[+el.dataset.idx]?.flight_iata === sel.flight_iata)
        el.classList.add("selected");
    });
  }
  const totalPages = Math.ceil(_allReturnFlights.length / FLIGHTS_PER_PAGE);
  const info = $("returnFlightPageInfo");
  if (info) info.textContent = `${page + 1} / ${totalPages}`;
  $("returnFlightPagePrev").disabled = page === 0;
  $("returnFlightPageNext").disabled = page >= totalPages - 1;
}

function setupPager() {
  const pager = $("flightListPager");
  if (!pager) return;
  const totalPages = Math.ceil(_allFlights.length / FLIGHTS_PER_PAGE);
  pager.style.display = totalPages > 1 ? "flex" : "none";

  $("flightPagePrev").onclick = () => {
    if (_flightPage > 0) { _flightPage--; renderFlightPage(_flightPage); }
  };
  $("flightPageNext").onclick = () => {
    // Read live length so stale closure never blocks navigation after a re-fetch
    const tp = Math.ceil(_allFlights.length / FLIGHTS_PER_PAGE);
    if (_flightPage < tp - 1) { _flightPage++; renderFlightPage(_flightPage); }
  };
}

function setupReturnPager() {
  const pager = $("returnFlightListPager");
  if (!pager) return;
  const totalPages = Math.ceil(_allReturnFlights.length / FLIGHTS_PER_PAGE);
  pager.style.display = totalPages > 1 ? "flex" : "none";

  $("returnFlightPagePrev").onclick = () => {
    if (_returnFlightPage > 0) {
      _returnFlightPage--;
      renderReturnFlightPage(_returnFlightPage);
    }
  };
  $("returnFlightPageNext").onclick = () => {
    const tp = Math.ceil(_allReturnFlights.length / FLIGHTS_PER_PAGE);
    if (_returnFlightPage < tp - 1) {
      _returnFlightPage++;
      renderReturnFlightPage(_returnFlightPage);
    }
  };
}

function renderFlightSelectCard(f, idx, leg = "arrival") {
  const dep = f.dep_scheduled || "--:--";
  const arr = f.arr_scheduled || "--:--";
  const gate =
    leg === "departure" && f.dep_gate
      ? ` · G${f.dep_gate}`
      : f.arr_gate
        ? ` · G${f.arr_gate}`
        : "";
  const term =
    leg === "departure" && f.dep_terminal
      ? ` · ${f.dep_terminal}`
      : f.arr_terminal
        ? ` · ${f.arr_terminal}`
        : "";
  const delay = f.arr_delay > 0 ? `<span class="fsc-delay">+${f.arr_delay}분 지연</span>` : "";
  const days = f.operating_days ? `<span class="fsc-days">${f.operating_days}</span>` : "";
  const aliases = (f.codeshare_aliases || []);
  const aliasHtml = aliases.length
    ? `<span class="fsc-aliases">+ ${aliases.join(" · ")}</span>`
    : "";
  return `
<div class="flight-sel-card" data-idx="${idx}">
  <div class="fsc-airline">${escHtml(f.airline_name)} <span class="fsc-num">${escHtml(f.flight_iata)}</span>${aliasHtml}${days}</div>
  <div class="fsc-route">
    <span class="fsc-ap">${escHtml(f.dep_iata)}</span>
    <span class="fsc-time">${dep}</span>
    <span class="fsc-arrow">→</span>
    <span class="fsc-ap">${escHtml(f.arr_iata)}</span>
    <span class="fsc-time">${arr}</span>
    ${gate || term ? `<span class="fsc-meta">${gate}${term}</span>` : ""}
  </div>
  ${delay}
</div>`;
}

function escHtml(s) {
  return String(s || "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function selectFlight(el, flight) {
  $("flightListCards")
    ?.querySelectorAll(".flight-sel-card")
    .forEach((c) => c.classList.remove("selected"));
  el.classList.add("selected");
  wizardData.flight = { ...wizardData.flight, selected: flight };
}

function selectReturnFlight(el, flight) {
  $("returnFlightListCards")
    ?.querySelectorAll(".flight-sel-card")
    .forEach((c) => c.classList.remove("selected"));
  el.classList.add("selected");
  wizardData.flight = { ...wizardData.flight, selectedReturn: flight };
}

// ── STEP 3: ACCOMMODATION ─────────────────────────────────────────────────
function setupStep3() {
  $("accomOptions")?.addEventListener("click", (e) => {
    const card = e.target.closest(".option-card");
    if (!card) return;
    document.querySelectorAll("#accomOptions .option-card")
      .forEach((c) => c.classList.remove("selected"));
    card.classList.add("selected");
    const val = card.dataset.val;
    const showLoc = val === "decided" || val === "friend";
    $("accomLocationBlock").style.display   = showLoc ? "block" : "none";
    $("accomDetailShared").style.display    = showLoc ? "block" : "none";
    $("accomDetailUndecided").style.display = val === "undecided" ? "block" : "none";
    if (val !== "undecided") _showHotelManualBlock(false);
    _syncAccomDisplay();
  });
}

// ── STEP 6: BUDGET ────────────────────────────────────────────────────────
function setupStep6() {
  $("budgetCurrency")?.addEventListener("change", (e) => {
    $("dailyCurrencySym").textContent = e.target.value === "KRW" ? "₩" : "¥";
  });
}

// ── CHIPS ─────────────────────────────────────────────────────────────────
function setupChipGroup(id, singleSelect) {
  const el = $(id);
  if (!el) return;
  el.addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    if (singleSelect) {
      el.querySelectorAll(".chip").forEach((c) => c.classList.remove("selected"));
      chip.classList.add("selected");
    } else {
      chip.classList.toggle("selected");
    }
  });
}

function setupSportsDetailToggle() {
  const activityEl = $("activityChips");
  if (activityEl) {
    activityEl.addEventListener("click", () => setTimeout(syncSportsDetail, 0));
  }
}

function syncSportsDetail() {
  const block = $("sportsDetailBlock");
  if (!block) return;
  const show = chips("activityChips").includes("sports");
  block.style.display = show ? "block" : "none";
  if (!show) {
    $("sportsChips")?.querySelectorAll(".chip.selected").forEach((c) => {
      c.classList.remove("selected");
    });
  }
}

// ── KOREAN ADDRESS DATA ───────────────────────────────────────────────────
const ADDR_DATA = {
  "서울특별시":      ["강남구","강동구","강북구","강서구","관악구","광진구","구로구","금천구","노원구","도봉구","동대문구","동작구","마포구","서대문구","서초구","성동구","성북구","송파구","양천구","영등포구","용산구","은평구","종로구","중구","중랑구"],
  "부산광역시":      ["강서구","금정구","기장군","남구","동구","동래구","부산진구","북구","사상구","사하구","서구","수영구","연제구","영도구","중구","해운대구"],
  "대구광역시":      ["달서구","달성군","동구","북구","서구","수성구","중구"],
  "인천광역시":      ["강화군","계양구","남동구","동구","미추홀구","부평구","서구","연수구","옹진군","중구"],
  "광주광역시":      ["광산구","남구","동구","북구","서구"],
  "대전광역시":      ["대덕구","동구","서구","유성구","중구"],
  "울산광역시":      ["남구","동구","북구","울주군","중구"],
  "세종특별자치시":  ["세종시"],
  "경기도":          ["고양시 덕양구","고양시 일산동구","고양시 일산서구","과천시","광명시","광주시","구리시","군포시","김포시","남양주시","동두천시","부천시","성남시 분당구","성남시 수정구","성남시 중원구","수원시 권선구","수원시 영통구","수원시 장안구","수원시 팔달구","시흥시","안산시 단원구","안산시 상록구","안성시","안양시 동안구","안양시 만안구","양주시","양평군","여주시","연천군","오산시","용인시 기흥구","용인시 수지구","용인시 처인구","의왕시","의정부시","이천시","파주시","평택시","포천시","하남시","화성시"],
  "강원특별자치도":  ["강릉시","고성군","동해시","삼척시","속초시","양구군","양양군","영월군","원주시","인제군","정선군","철원군","춘천시","태백시","평창군","홍천군","화천군","횡성군"],
  "충청북도":        ["괴산군","단양군","보은군","영동군","옥천군","음성군","제천시","증평군","진천군","청주시 서원구","청주시 상당구","청주시 청원구","청주시 흥덕구","충주시"],
  "충청남도":        ["계룡시","공주시","금산군","논산시","당진시","보령시","부여군","서산시","서천군","아산시","예산군","천안시 동남구","천안시 서북구","청양군","태안군","홍성군"],
  "전북특별자치도":  ["고창군","군산시","김제시","남원시","무주군","부안군","순창군","완주군","익산시","임실군","장수군","전주시 덕진구","전주시 완산구","정읍시","진안군"],
  "전라남도":        ["강진군","고흥군","곡성군","광양시","구례군","나주시","담양군","목포시","무안군","보성군","순천시","신안군","여수시","영광군","영암군","완도군","장성군","장흥군","진도군","함평군","해남군","화순군"],
  "경상북도":        ["경산시","경주시","고령군","구미시","김천시","문경시","봉화군","상주시","성주군","안동시","영덕군","영양군","영주시","영천시","예천군","울릉군","울진군","의성군","청도군","청송군","칠곡군","포항시 남구","포항시 북구"],
  "경상남도":        ["거제시","거창군","고성군","김해시","남해군","밀양시","사천시","산청군","양산시","의령군","진주시","창녕군","창원시 마산합포구","창원시 마산회원구","창원시 성산구","창원시 의창구","창원시 진해구","통영시","하동군","함안군","함양군","합천군"],
  "제주특별자치도":  ["서귀포시","제주시"],
};

// ── PLAN GENERATION ───────────────────────────────────────────────────────
const PLAN_MSGS = [
  "情報を整理しています...",
  "旅行データを分析しています...",
  "K-Cultureデータベースを参照中...",
  "プランを生成しています...",
];

async function generatePlan() {
  const barEl    = $("planBar");
  const pctEl    = $("planPct");
  const statusEl = $("planStatus");
  const userName = _displayName(currentUser || {});

  $("planTitle").textContent     = `${userName}さんの旅行プランを生成中...`;
  $("planLoadingArea").style.display = "block";
  $("planOutputArea").style.display  = "none";
  $("planErrorArea").style.display   = "none";

  let progress = 0;
  const timer = setInterval(() => {
    if      (progress < 40) progress += Math.random() * 3 + 1;
    else if (progress < 80) progress += Math.random() * 1.5 + 0.3;
    else if (progress < 92) progress += 0.25;
    progress = Math.min(progress, 92);
    const idx = progress < 25 ? 0 : progress < 50 ? 1 : progress < 75 ? 2 : 3;
    statusEl.textContent = PLAN_MSGS[idx];
    barEl.style.width    = progress + "%";
    pctEl.textContent    = Math.floor(progress) + "%";
  }, 300);

  try {
    const res  = await fetch("/api/chat/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message:         buildPrompt(),
        reply_language:  "日本語",
        session_id:      null,
        history:         [],
        traveler_profile: wizardData,
      }),
    });
    const data = await res.json();
    clearInterval(timer);
    barEl.style.width = "100%"; pctEl.textContent = "100%";
    if (!res.ok) throw new Error(data.detail || "error");

    setTimeout(async () => {
      $("planLoadingArea").style.display = "none";
      $("planTitle").textContent = `${userName}さんの旅行プラン`;
      await _displayPlanOutput(data);
      $("planOutputArea").style.display = "block";
    }, 400);

  } catch {
    clearInterval(timer);
    $("planLoadingArea").style.display = "none";
    $("planErrorArea").style.display   = "block";
    $("btnRetryPlan").onclick = generatePlan;
  }
}

function buildPrompt() {
  const d = wizardData;
  const sym = d.budget?.currency === "KRW" ? "₩" : "¥";
  const rMap = { seoul:"ソウル", gyeonggi:"京畿道", incheon:"仁川", gangwon:"江原道",
                 chungcheong:"忠清道", jeolla:"全羅道", gyeongsang:"慶尚道", jeju:"済州島" };
  const aMap = { food:"グルメ", shopping:"ショッピング", nightview:"夜景", tradition:"伝統文化",
                 hallyu:"韓流", nature:"自然", photo:"フォトスポット", sports:"スポーツ観戦" };
  const tMap = { rail:"鉄道・地下鉄（AREX・広域鉄道）", taxi:"タクシー", bus:"空港バス", rental:"レンタカー",
                 arex:"鉄道・地下鉄（AREX）", subway:"鉄道・地下鉄" }; // 하위호환
  const cMap = { solo:"一人旅", couple:"カップル", friends:"友人", family:"ファミリー", parents:"親孝行" };
  const pMap = { packed:"びっしり", relaxed:"のんびり" };
  const sMap = { budget:"コスパ重視", normal:"バランス", premium:"プレミアム" };

  const lines = [
    `${_displayName(currentUser || {})}さんの韓国旅行プランを日本語で作成してください。以下の情報を基に、日程ごとの具体的なプランを提案してください。`,
  ];

  if (d.flight) {
    const f = d.flight;
    lines.push(`【フライト】${f.from}→${f.to}、出発:${f.depart||"未定"}、帰国:${f.returnDate||"未定"}、${f.passengers}名`);
    if (f.selected) {
      const sel = f.selected;
      const arrTime = sel.arr_scheduled || "未定";
      const term    = sel.arr_terminal  ? ` ${sel.arr_terminal}ターミナル` : "";
      lines.push(`【1日目 到着便】${sel.flight_iata||""} 到着予定:${arrTime}${term}（入国審査+税関:通常60〜90分）`);
    }
    if (f.selectedReturn) {
      const retSel = f.selectedReturn;
      const depTime = retSel.dep_scheduled || "未定";
      const term = retSel.dep_terminal ? ` ${retSel.dep_terminal}ターミナル` : "";
      const gate = retSel.dep_gate ? ` ゲート${retSel.dep_gate}` : "";
      lines.push(
        `【最終日 出国便】${retSel.flight_iata || ""} ICN出発予定:${depTime}${term}${gate}`
      );
      lines.push(
        "（国際線:出発2〜3時間前にICN到着・チェックイン推奨。最終日の観光・食事は出発時刻から逆算して終了）"
      );
    }
  }
  if (d.nights) lines.push(`【日程】${d.nights}泊${d.days}日`);

  if (d.accommodation?.type) {
    const typeMap = { decided:"予約済み", undecided:"未定（候補あり）", friend:"友人・家族宅" };
    let accomStr = typeMap[d.accommodation.type] || "";
    if (d.accommodation.name)    accomStr += ` 施設名:${d.accommodation.name}`;
    if (d.accommodation.address) accomStr += ` 住所:${d.accommodation.address}`;
    if (d.accommodation.detail)  accomStr += ` 詳細:${d.accommodation.detail}`;
    else if (d.accommodation.region) accomStr += ` 詳細:${d.accommodation.region}`;
    const sh = d.accommodation.selectedHotel;
    if (sh) {
      accomStr += ` ホテル候補:${sh.name}`;
      if (sh.address) accomStr += `（${sh.address}）`;
    }
    lines.push(`【宿泊】${accomStr}`);
  }
  if (d.transport?.length) {
    const tTimeMap = {
      rail:   "鉄道・地下鉄（AREX直通:約43分/AREX一般:約51分 ソウル駅着 / 乗換先により広域鉄道・地下鉄を利用）",
      bus:    "リムジンバス:約60〜90分",
      taxi:   "タクシー/KakaoTaxi:約60〜90分",
      rental: "レンタカー:約60〜90分",
      // 하위호환 (구 저장 데이터 대응)
      arex:   "鉄道・地下鉄（AREX直通:約43分/AREX一般:約51分）",
      subway: "鉄道・地下鉄（広域鉄道・地下鉄経由）",
    };
    const accomDest = d.accommodation?.address || d.accommodation?.region || "";
    const tInfo = d.transport.map((t) => tTimeMap[t] || tMap[t] || t).join(" または ");
    lines.push(`【空港→宿泊先の移動】${tInfo}${accomDest ? ` → ${accomDest}` : ""}`);
    if (d.flight?.selectedReturn) {
      const airportCode = d.flight?.to || "ICN";
      lines.push(
        `【最終日 宿泊先→空港】${accomDest || "宿泊先"} → ${airportCode}（${tInfo}。出発便の2〜3時間前までに到着）`
      );
    }
  }
  if (d.regions?.length)
    lines.push(`【希望エリア】${d.regions.map((r)=>rMap[r]||r).join("・")}`);
  if (d.regionCities)
    lines.push(`【重点都市・区】${d.regionCities}（この都市を中心に日程・食事を組むこと）`);
  const spMap = { soccer:"サッカー観戦", baseball:"野球観戦", basketball:"バスケ観戦", volleyball:"バレー観戦", sports:"スポーツ観戦（全競技）" };
  const actFiltered = (d.activities || []).filter((a) => a !== "sports");
  const activityParts = actFiltered.map((a) => aMap[a] || a);
  const sportParts = (d.sports || []).map((s) => spMap[s] || s);
  if (activityParts.length) {
    lines.push(`【やりたいこと】${activityParts.join("・")}`);
  }
  if (sportParts.length) {
    lines.push(`【スポーツ観戦】${sportParts.join("・")} — Reference Dataの試合日程をプランに組み込むこと`);
  }

  if (d.budget?.total) {
    let bs = `総予算:${sym}${d.budget.total}`;
    if (d.budget.daily) bs += `、1日:${sym}${d.budget.daily}`;
    if (d.budget.style) bs += `、スタイル:${sMap[d.budget.style]||d.budget.style}`;
    lines.push(`【予算】${bs}`);
  }

  const add = d.additional;
  if (add) {
    const parts = [];
    if (add.companion)              parts.push(cMap[add.companion]||add.companion);
    if (add.pace)                   parts.push(pMap[add.pace]||add.pace);
    if (add.foodRestrictions?.length) {
      const frMap = {
        spicy:   "辛いものは苦手（辛い料理は避ける）",
        allergy: "アレルギーあり",
        vegan:   "ベジタリアン向けを優先",
      };
      const frLabels = add.foodRestrictions.map((f) => frMap[f] || f);
      parts.push(`食事制限:${frLabels.join("・")}`);
    }
    if (add.note)                   parts.push(add.note);
    if (parts.length) lines.push(`【その他】${parts.join("、")}`);
  }

  if (d.accommodation?.type === "friend" || (d.accommodation?.address || "").includes("고양")) {
    lines.push("【到着日】友人宅・京畿道宿泊のため、1日目の夕食は高陽・宿泊近郊のみ。明洞・弘大への移動は2日目以降。");
  }
  lines.push(
    "\n地図アプリへの検索依頼は禁止。",
    "【食事】Reference Dataのレストラン名を昼食・夕食ブロックに必ず記載し、GoogleマップURLを付ける。データがなければ料理ジャンル＋エリアのみ。",
    "【スポーツ】Sports Schedule Resultsの試合またはオフシーズン案内をそのまま記載。ジム・ストリートへの置き換え禁止。",
    "営業時間・料金・チケットは文末で一言のみ。"
  );
  return lines.join("\n");
}

// ── TRANSPORT INFO PANEL ──────────────────────────────────────────────────
function setupTransportInfo() {
  const TRANSPORT_INFO = {
    rail: `<div class="ti-card"><strong>🚆 鉄道・地下鉄（AREX・広域鉄道）</strong>
<strong>AREX（空港鉄道）</strong>: 仁川空港↔ソウル駅 直通約43分 / 一般列車約51分（DMC・弘大入口など途中停車）<br>
AREX一般でDMC駅乗換 → 京義中央線で高陽・能谷方面へも接続<br>
<strong>ソウル地下鉄・広域鉄道</strong>: 1〜9号線・水仁盆唐線・新盆唐線・경의중앙선など。釜山・大邱・仁川・大田・光州でも地下鉄が利用できます。<br>
経路検索には <strong>ネイバーマップ</strong> または <strong>カカオマップ</strong> が便利です（日本語対応）。<br>
<a href="https://www.arex.or.kr/jp/" target="_blank" rel="noopener">▶ AREX 公式サイト（時刻表・料金）</a>
<a href="https://map.naver.com/" target="_blank" rel="noopener">▶ ネイバーマップ（経路検索）</a>
<a href="https://www.seoulmetro.co.kr/jp/" target="_blank" rel="noopener">▶ ソウル交通公社（路線図）</a></div>`,
    taxi: `<div class="ti-card"><strong>🚕 タクシー / KakaoTaxi</strong>
KakaoTaxiアプリで配車。インチョン空港からソウル市内は約60〜90分<br>
<a href="https://www.kakaomobility.com/" target="_blank" rel="noopener">▶ KakaoTaxi 公式サイト・アプリ</a></div>`,
    bus: `<div class="ti-card"><strong>🚌 空港リムジンバス</strong>
ソウル市内・地方都市への直行バス（6000〜18000ウォン台）<br>
<a href="https://www.airportlimousine.co.kr/jp/" target="_blank" rel="noopener">▶ リムジンバス 公式サイト（時刻表・乗り場）</a></div>`,
    rental: `<div class="ti-card"><strong>🚗 インチョン空港 レンタカー</strong>
第1・第2旅客ターミナル地下1階に各社カウンターあり<br>
<a href="https://www.lotterentacar.net/" target="_blank" rel="noopener">▶ ロッテレンタカー</a>
<a href="https://www.skrentacar.co.kr/" target="_blank" rel="noopener">▶ SKレンタカー</a>
<a href="https://www.ajrentacar.co.kr/" target="_blank" rel="noopener">▶ AJレンタカー</a></div>`,
    // 하위호환: 구 데이터에 arex/subway가 저장된 경우
    arex:   `<div class="ti-card"><strong>🚆 AREX（空港鉄道）</strong>
仁川空港↔ソウル駅 直通約43分 / 一般列車約51分<br>
<a href="https://www.arex.or.kr/jp/" target="_blank" rel="noopener">▶ AREX 公式サイト</a></div>`,
    subway: `<div class="ti-card"><strong>🚇 地下鉄・広域鉄道</strong>
<a href="https://map.naver.com/" target="_blank" rel="noopener">▶ ネイバーマップ（経路検索）</a></div>`,
  };

  const el = $("transportChips");
  const panel = $("transportInfoPanel");
  if (!el || !panel) return;

  el.addEventListener("click", () => {
    requestAnimationFrame(() => {
      const selected = chips("transportChips");
      if (!selected.length) { panel.style.display = "none"; panel.innerHTML = ""; return; }
      panel.innerHTML = selected.map((t) => TRANSPORT_INFO[t] || "").join("");
      panel.style.display = "block";
    });
  });
}

// ── UNDECIDED HOTEL RECOMMEND ─────────────────────────────────────────────
function setupUndecidedAddrDropdown() {
  const sido    = $("addrSidoUnd");
  const sigungu = $("addrSigunguUnd");
  if (!sido || !sigungu) return;

  Object.keys(ADDR_DATA).forEach((d) => {
    const opt = document.createElement("option");
    opt.value = opt.textContent = d;
    sido.appendChild(opt);
  });

  sido.addEventListener("change", () => {
    const districts = ADDR_DATA[sido.value] || [];
    sigungu.innerHTML = `<option value="">-- 선택 --</option>` +
      districts.map((d) => `<option value="${d}">${d}</option>`).join("");
    sigungu.disabled = !sido.value;
    // 도만 선택돼도 검색 (선택사항)
    _fetchHotelRecommend();
  });

  sigungu.addEventListener("change", _fetchHotelRecommend);

  // 選択解除ボタン
  $("hotelSelClearBtn")?.addEventListener("click", () => {
    _selectedHotel = null;
    _selectedAccomPlace = null;
    const panel = $("hotelSelectedPanel");
    if (panel) panel.style.display = "none";
  });
}

function _buildUndecidedArea() {
  const sido    = $("addrSidoUnd")?.value    || "";
  const sigungu = $("addrSigunguUnd")?.value || "";
  return sigungu || sido;
}

function _showHotelManualBlock(show, emphasizeEmpty) {
  const block = $("hotelManualBlock");
  const lead  = $("hotelManualLead");
  if (!block) return;
  block.style.display = show ? "block" : "none";
  if (lead && emphasizeEmpty) {
    lead.textContent = "おすすめホテルが見つかりませんでした。ホテル名で直接検索してください。";
  } else if (lead) {
    lead.textContent = "別のホテル名で再検索できます";
  }
}

function setupHotelManualSearch() {
  const btn = $("hotelManualSearchBtn");
  const input = $("hotelManualInput");
  if (!btn) return;

  const run = () => _fetchHotelManualSearch();
  btn.addEventListener("click", run);
  input?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); run(); }
  });
}

async function _fetchHotelManualSearch() {
  const area = _buildUndecidedArea();
  const q    = ($("hotelManualInput")?.value || "").trim();
  if (!q && !area) {
    const input = $("hotelManualInput");
    if (input) input.focus();
    return;
  }

  const query = area && q ? `${area} ${q}` : (q || `${area} 호텔`);

  const statusEl  = $("hotelSearchStatus");
  const statusTxt = $("hotelStatusText");
  const btn       = $("hotelManualSearchBtn");

  if (statusEl) statusEl.style.display = "flex";
  if (statusTxt) statusTxt.textContent = "ホテルを検索中…";
  if (btn) { btn.disabled = true; btn.textContent = "検索中…"; }

  _hotelSearchMode = "manual";
  _allHotels = [];
  _hotelPage = 0;

  try {
    const res = await fetch(
      `/api/places/search/?q=${encodeURIComponent(query)}&all=1`
    );
    const data = await res.json();
    _allHotels = data.places || [];
    _hotelArea = area || q;
    _renderHotelPage(0);
  } catch {
    _allHotels = [];
    _hotelArea = area || q;
    _renderHotelPage(0);
  } finally {
    if (statusEl) statusEl.style.display = "none";
    if (btn) { btn.disabled = false; btn.textContent = "検索"; }
  }
}

async function _fetchHotelRecommend() {
  const sido    = $("addrSidoUnd")?.value    || "";
  const sigungu = $("addrSigunguUnd")?.value || "";
  const area    = sigungu || sido;
  if (!area) return;

  const statusEl  = $("hotelSearchStatus");
  const statusTxt = $("hotelStatusText");
  const resultsEl = $("hotelResults");

  if (statusEl) { statusEl.style.display = "flex"; }
  if (statusTxt) { statusTxt.textContent = `${area}のホテルを検索中…`; }
  if (resultsEl) { resultsEl.style.display = "none"; resultsEl.innerHTML = ""; }

  if ($("hotelListPager")) $("hotelListPager").style.display = "none";
  _allHotels = [];
  _hotelPage = 0;
  _hotelSearchMode = "recommend";

  try {
    const res = await fetch(
      `/api/places/search/?q=${encodeURIComponent(area + " 호텔")}&all=1`
    );
    const data = await res.json();
    _allHotels = data.places || [];
    _hotelArea = area;
    _renderHotelPage(0);
  } catch {
    _allHotels = [];
    _hotelArea = area;
    _renderHotelPage(0);
  } finally {
    if (statusEl) statusEl.style.display = "none";
  }
}

function _selectHotelFromList(p) {
  // Stay in undecided mode — just record the selected hotel and show info within the undecided panel.
  _selectedHotel = p;

  const infoEl   = $("hotelSelectedPanel");
  const nameEl   = $("hotelSelectedPanelName");
  const addrEl   = $("hotelSelectedPanelAddr");
  const ratingEl = $("hotelSelectedPanelRating");
  const linkEl   = $("hotelSelectedPanelLink");

  if (infoEl) {
    if (nameEl)   nameEl.textContent  = p.name || "";
    if (addrEl)   addrEl.textContent  = p.address || "";
    if (ratingEl) {
      const stars = p.rating ? `⭐ ${p.rating.toFixed(1)}` : "";
      const cnt   = p.user_rating_count ? ` (${p.user_rating_count.toLocaleString()}件)` : "";
      const price = p.price_level ? ` · ${p.price_level}` : "";
      ratingEl.textContent = stars + cnt + price;
    }
    if (linkEl && p.maps_url) {
      linkEl.href = p.maps_url;
      linkEl.style.display = "inline";
    } else if (linkEl) {
      linkEl.style.display = "none";
    }
    infoEl.style.display = "block";
  }

  // Scroll to the info panel
  infoEl?.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function _renderHotelPage(page) {
  const el = $("hotelResults");
  const pagerEl = $("hotelListPager");
  if (!el) return;

  _hotelPage = page;
  const area = _hotelArea;
  const total = _allHotels.length;

  if (!total) {
    const emptyMsg = _hotelSearchMode === "manual"
      ? `「${escHtml(area)}」の検索結果はありませんでした。キーワードを変えて再検索するか、<a href="/chat/" class="link-inline">AIチャット</a>でご相談ください。`
      : `「${escHtml(area)}」のおすすめホテルが見つかりませんでした。下の検索欄でホテル名を入力してください。`;
    el.innerHTML = `<p class="accom-no-result">${emptyMsg}</p>`;
    el.style.display = "block";
    if (pagerEl) pagerEl.style.display = "none";
    _showHotelManualBlock(true, _hotelSearchMode === "recommend");
    return;
  }

  _showHotelManualBlock(true, false);

  const start = page * HOTELS_PER_PAGE;
  const slice = _allHotels.slice(start, start + HOTELS_PER_PAGE);
  const totalPages = Math.ceil(total / HOTELS_PER_PAGE);
  const listLabel = _hotelSearchMode === "manual" ? "検索結果" : "おすすめホテル";

  el.innerHTML =
    `<p class="hotel-results-label">📍 ${escHtml(area)} — ${listLabel} 全${total}件（${page + 1}/${totalPages}ページ）</p>` +
    slice.map((p, i) => {
      const photoHtml = p.photo_name
        ? `<img class="hotel-photo" src="/api/photo/?name=${encodeURIComponent(p.photo_name)}" loading="lazy" alt="${escHtml(p.name)}" onerror="this.style.display='none'" />`
        : "";
      const ratingHtml = p.rating
        ? `<span class="hotel-rating">⭐ ${Number(p.rating).toFixed(1)}<span class="hotel-rating-cnt">${p.user_rating_count ? ` (${p.user_rating_count.toLocaleString()}件)` : ""}</span></span>`
        : "";
      const priceHtml = p.price_level
        ? `<span class="hotel-price">${escHtml(p.price_level)}</span>`
        : "";
      const mapsHtml = p.maps_url
        ? `<a href="${escHtml(p.maps_url)}" target="_blank" rel="noopener" class="hotel-maps-link">📍 Googleマップで見る</a>`
        : "";
      return `
      <div class="hotel-card">
        ${photoHtml}
        <div class="hotel-card-info">
          <span class="hotel-name">${escHtml(p.name)}</span>
          <div class="hotel-meta">${ratingHtml}${priceHtml}</div>
          ${p.address ? `<span class="hotel-addr">${escHtml(p.address)}</span>` : ""}
          ${mapsHtml}
        </div>
        <button type="button" class="btn btn-sm secondary hotel-select-btn" data-idx="${start + i}">
          このホテルを選択
        </button>
      </div>`;
    }).join("");
  el.style.display = "block";

  el.querySelectorAll(".hotel-select-btn").forEach((btn) => {
    btn.addEventListener("click", () => _selectHotelFromList(_allHotels[+btn.dataset.idx]));
  });

  if (pagerEl) {
    pagerEl.style.display = totalPages > 1 ? "flex" : "none";
    const info = $("hotelPageInfo");
    if (info) info.textContent = `${page + 1} / ${totalPages}`;
    const prev = $("hotelPagePrev");
    const next = $("hotelPageNext");
    if (prev) {
      prev.disabled = page === 0;
      prev.onclick = () => { if (_hotelPage > 0) _renderHotelPage(_hotelPage - 1); };
    }
    if (next) {
      next.disabled = page >= totalPages - 1;
      next.onclick = () => {
        const tp = Math.ceil(_allHotels.length / HOTELS_PER_PAGE);
        if (_hotelPage < tp - 1) _renderHotelPage(_hotelPage + 1);
      };
    }
  }
}

// ── ADDRESS DROPDOWN ──────────────────────────────────────────────────────
function setupAddrDropdown() {
  const sido    = $("addrSido");
  const sigungu = $("addrSigungu");
  if (!sido || !sigungu) return;

  Object.keys(ADDR_DATA).forEach((d) => {
    const opt = document.createElement("option");
    opt.value = opt.textContent = d;
    sido.appendChild(opt);
  });

  sido.addEventListener("change", () => {
    const districts = ADDR_DATA[sido.value] || [];
    sigungu.innerHTML = `<option value="">-- 選択 --</option>` +
      districts.map((d) => `<option value="${d}">${d}</option>`).join("");
    sigungu.disabled = !sido.value;
    _syncAccomDisplay();
  });

  sigungu.addEventListener("change", _syncAccomDisplay);
  $("accomDetailManual")?.addEventListener("input", _syncAccomDisplay);
}

function _buildAccomBase() {
  const sido    = $("addrSido")?.value    || "";
  const sigungu = $("addrSigungu")?.value || "";
  return [sido, sigungu].filter(Boolean).join(" ");
}

function _stripAccomBase(full, base) {
  const f = (full || "").trim();
  const b = (base || "").trim();
  if (!f) return "";
  if (!b) return f;
  if (f.startsWith(b)) return f.slice(b.length).trim();
  return f;
}

function _buildFullAccomAddress() {
  const base   = _buildAccomBase();
  const detail = ($("accomDetailManual")?.value || "").trim();
  if (!base && !detail) return "";
  if (detail && (!base || detail.includes(base))) return detail;
  if (!detail) return base;
  return `${base} ${detail}`;
}

function _syncAccomDisplay() {
  const full = _buildFullAccomAddress();
  if ($("accomAddress")) $("accomAddress").value = full;

  const name   = ($("accomName")?.value || "").trim();
  const infoEl = $("accomSelectedInfo");
  if (!infoEl) return;

  if (name || full) {
    infoEl.style.display = "flex";
    const nameEl = $("accomSelectedName");
    const addrEl = $("accomSelectedAddr");
    if (nameEl) nameEl.textContent = name || "選択済み住所";
    if (addrEl) addrEl.textContent = full || _buildAccomBase();
  } else {
    infoEl.style.display = "none";
  }
}

function _accomSearchQuery(extra) {
  const q = (extra || "").trim();
  const base = _buildAccomBase();
  if (!q && !base) return "";
  return base ? `${base} ${q}`.trim() : q;
}

async function _fetchPlaces(query) {
  const res = await fetch(`/api/places/search/?q=${encodeURIComponent(query)}`);
  const data = await res.json();
  return data.places || [];
}

// ── ACCOMMODATION SEARCH ──────────────────────────────────────────────────
function setupAccomSearch() {
  const btn = $("accomSearchBtn");
  if (!btn) return;

  btn.addEventListener("click", async () => {
    const query = _accomSearchQuery($("accomSearchInput")?.value);
    if (!query) return;

    btn.disabled = true;
    btn.textContent = "検索中…";
    try {
      const places = await _fetchPlaces(query);
      _renderPlacesResults(places, {
        resultsEl: $("accomSearchResults"),
        mode: "facility",
      });
    } catch {
      _renderPlacesResults([], { resultsEl: $("accomSearchResults"), mode: "facility" });
    } finally {
      btn.disabled = false;
      btn.textContent = "検索";
    }
  });
}

function setupAccomDetailSearch() {
  const btn = $("accomDetailSearchBtn");
  if (!btn) return;

  btn.addEventListener("click", async () => {
    const query = _accomSearchQuery($("accomDetailSearchInput")?.value);
    if (!query) return;

    btn.disabled = true;
    btn.textContent = "検索中…";
    try {
      const places = await _fetchPlaces(query);
      _renderPlacesResults(places, {
        resultsEl: $("accomDetailSearchResults"),
        mode: "detail",
      });
    } catch {
      _renderPlacesResults([], { resultsEl: $("accomDetailSearchResults"), mode: "detail" });
    } finally {
      btn.disabled = false;
      btn.textContent = "検索";
    }
  });
}

function _storeAccomPlace(p) {
  _selectedAccomPlace = {
    name: p.name || "",
    address: p.address || "",
    latitude: p.latitude ?? null,
    longitude: p.longitude ?? null,
    maps_url: p.maps_url || "",
  };
}

function _applyFacilityPlace(p) {
  _storeAccomPlace(p);
  $("accomName").value = p.name || "";
  const addr = (p.address || "").trim();
  if ($("accomDetailManual") && addr) {
    $("accomDetailManual").value = _stripAccomBase(addr, _buildAccomBase()) || addr;
  }
  _syncAccomDisplay();
}

function _applyDetailPlace(p) {
  _storeAccomPlace(p);
  const addr = (p.address || "").trim();
  if ($("accomDetailManual") && addr) {
    $("accomDetailManual").value = _stripAccomBase(addr, _buildAccomBase()) || addr;
  }
  if (p.name && !($("accomName")?.value || "").trim()) {
    $("accomName").value = p.name;
  }
  _syncAccomDisplay();
}

function _renderPlacesResults(places, { resultsEl, mode }) {
  if (!resultsEl) return;

  if (!places.length) {
    resultsEl.innerHTML =
      `<p class="accom-no-result">見つかりませんでした。キーワードを変えるか、「詳細住所（直接入力）」に入力してください。</p>`;
    resultsEl.style.display = "block";
    return;
  }

  resultsEl.innerHTML = places.map((p, i) => `
    <button type="button" class="accom-result-item" data-idx="${i}">
      <strong>${escHtml(p.name || p.address || "住所")}</strong>
      ${p.address ? `<span class="accom-result-addr">${escHtml(p.address)}</span>` : ""}
    </button>`).join("");
  resultsEl.style.display = "block";

  resultsEl.querySelectorAll(".accom-result-item").forEach((item) => {
    item.addEventListener("click", () => {
      const p = places[+item.dataset.idx];
      if (mode === "facility") _applyFacilityPlace(p);
      else _applyDetailPlace(p);
      resultsEl.style.display = "none";
      if (mode === "facility" && $("accomSearchResults")) $("accomSearchResults").style.display = "none";
    });
  });
}

// ── PLAN HTML RENDERER ────────────────────────────────────────────────────
const _PLAN_MAPS_URL_RE = /^https?:\/\/(?:maps\.google\.com|www\.google\.com\/maps)\/\S+/i;

function _escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function _mapsUrlKey(url) {
  const m = url.match(/[?&]cid=(\d+)/);
  return m ? `cid:${m[1]}` : url.split("&g_mp=")[0].split("&")[0];
}

function _buildPlaceIndex(apiPlaces) {
  const idx = {};
  for (const p of apiPlaces) {
    const uri = p.google_maps_uri || p.maps_url;
    if (uri) idx[_mapsUrlKey(uri)] = p;
  }
  return idx;
}

function _extractMapsUrlsFromPlan(text) {
  const found = new Set();
  for (const line of text.split(/\r?\n/)) {
    const t = line.trim();
    if (_PLAN_MAPS_URL_RE.test(t)) found.add(t.split(/\s/)[0]);
  }
  return [...found];
}

function _queryLabelForUrl(lines, url) {
  const i = lines.findIndex((ln) => ln.trim().startsWith(url) || ln.includes(url));
  if (i <= 0) return "";
  for (let j = i - 1; j >= 0; j--) {
    const t = lines[j].trim();
    if (!t || _PLAN_MAPS_URL_RE.test(t) || t.startsWith("http")) continue;
    return t.replace(/^[-・*]\s*/, "").replace(/（[^）]*）$/g, "").trim();
  }
  return "";
}

function _lookupPlace(index, url) {
  return index[_mapsUrlKey(url)] || null;
}

function _directionsUrl(p) {
  if (p.latitude != null && p.longitude != null) {
    return `https://www.google.com/maps/dir/?api=1&destination=${p.latitude},${p.longitude}&travelmode=transit`;
  }
  return p.google_maps_uri || "#";
}

function _renderInlinePlaceCard(p) {
  const name = _escapeHtml(p.name || "");
  const rating = p.rating ? `★${Number(p.rating).toFixed(1)}` : "";
  const reviews = p.user_rating_count
    ? `<span class="plan-place-card__reviews">(${Number(p.user_rating_count).toLocaleString()}件)</span>`
    : "";
  let openBadge = "";
  if (p.is_open_now === true) openBadge = '<span class="plan-place-card__open">営業中</span>';
  else if (p.is_open_now === false) openBadge = '<span class="plan-place-card__closed">時間外の可能性</span>';
  const priceLabel = p.price_level
    ? `<span class="plan-place-card__price">${_escapeHtml(p.price_level)}</span>`
    : "";
  const thumb = p.photo_name
    ? `<img class="plan-place-card__img" src="/api/photo/?name=${encodeURIComponent(p.photo_name)}" alt="" loading="lazy" onerror="this.classList.add('plan-place-card__img--fallback')" />`
    : '<span class="plan-place-card__img plan-place-card__img--fallback" aria-hidden="true">🍽</span>';
  const addr = p.address
    ? `<p class="plan-place-card__addr">${_escapeHtml(p.address)}</p>`
    : "";
  const mapsUri = p.google_maps_uri || "";
  const dirUri = _directionsUrl(p);
  const meta = [rating && `<span class="plan-place-card__rating">${rating}${reviews}</span>`, openBadge, priceLabel]
    .filter(Boolean).join("");
  const thumbLink = mapsUri || dirUri;
  return `<div class="plan-inline-spot"><article class="plan-place-card"><a class="plan-place-card__thumb-link" href="${_escapeHtml(thumbLink)}" target="_blank" rel="noopener">${thumb}</a><div class="plan-place-card__body"><h4 class="plan-place-card__name">${name}</h4>${meta ? `<div class="plan-place-card__meta">${meta}</div>` : ""}${addr}<div class="plan-place-card__actions">${mapsUri ? `<a href="${_escapeHtml(mapsUri)}" target="_blank" rel="noopener" class="plan-place-card__btn">地図</a>` : ""}<a href="${_escapeHtml(dirUri)}" target="_blank" rel="noopener" class="plan-place-card__btn plan-place-card__btn--route">経路</a></div></div></article></div>`;
}

function _formatPlanTextLine(line) {
  return _escapeHtml(line).replace(/【(.*?)】/g, "<strong>【$1】</strong>");
}

function _renderPlanHtml(text, placeIndex) {
  const lines = text.split(/\r?\n/);
  const out = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (_PLAN_MAPS_URL_RE.test(trimmed)) {
      const url = trimmed.split(/\s/)[0];
      const place = _lookupPlace(placeIndex, url);
      if (place) {
        out.push(_renderInlinePlaceCard(place));
        continue;
      }
      const esc = _escapeHtml(trimmed);
      out.push(`<a href="${esc}" target="_blank" rel="noopener noreferrer" class="plan-maps-fallback">${esc}</a>`);
      continue;
    }
    if (!trimmed) {
      out.push('<div class="plan-line-spacer" aria-hidden="true"></div>');
      continue;
    }
    out.push(`<p class="plan-line">${_formatPlanTextLine(line)}</p>`);
  }
  return out.join("");
}

function _renderVisitKoreaCards(stays, festivals, attractions) {
  let html = "";
  const buildCards = (items, emoji, showPeriod) =>
    items.slice(0, 5).map((it) => {
      const name  = _escapeHtml(it.title || "");
      const addr  = it.addr1 ? `<div class="plan-vk-addr">${_escapeHtml(it.addr1)}</div>` : "";
      const period = showPeriod && it.event_period
        ? `<span class="plan-vk-badge">${_escapeHtml(it.event_period)}</span>` : "";
      const thumb = it.first_image
        ? `<img class="plan-vk-thumb" src="${_escapeHtml(it.first_image)}" alt="" loading="lazy" onerror="this.style.display='none'" />`
        : `<span class="plan-vk-thumb plan-vk-thumb--fallback" aria-hidden="true">${emoji}</span>`;
      const uri   = it.maps_uri || "";
      const inner = `<div class="plan-vk-thumb-wrap">${thumb}</div><div class="plan-vk-text"><div class="plan-vk-name">${name}</div>${period ? `<div class="plan-vk-meta">${period}</div>` : ""}${addr}</div>`;
      return uri
        ? `<a class="plan-vk-card" href="${_escapeHtml(uri)}" target="_blank" rel="noopener">${inner}</a>`
        : `<div class="plan-vk-card">${inner}</div>`;
    }).join("");

  if (attractions && attractions.length) {
    html += `<div class="plan-refs-section"><h3 class="plan-refs-title">🗺 観光スポット（韓国観光公社）</h3><div class="plan-vk-grid">${buildCards(attractions, "🗺", false)}</div></div>`;
  }
  if (festivals && festivals.length) {
    html += `<div class="plan-refs-section"><h3 class="plan-refs-title">🎭 イベント・祭り（韓国観光公社）</h3><div class="plan-vk-grid">${buildCards(festivals, "🎭", true)}</div></div>`;
  }
  if (stays && stays.length) {
    html += `<div class="plan-refs-section"><h3 class="plan-refs-title">🏨 宿泊施設（韓国観光公社）</h3><div class="plan-vk-grid">${buildCards(stays, "🏨", false)}</div></div>`;
  }
  return html;
}

function _renderPlanPlacesRefSection(places) {
  if (!places.length) return "";
  const cards = places.slice(0, 12).map((p) => _renderInlinePlaceCard(p)).join("");
  return `<div class="plan-refs-section"><h3 class="plan-refs-title">📍 周辺スポット・飲食店（Google Places）</h3>
    <div class="plan-place-grid">${cards}</div>
    <p class="plan-refs-note">※ 評価・料金帯・写真は Google データ。プラン本文の店名とあわせてご利用ください。</p></div>`;
}

async function _displayPlanOutput(data) {
  const reply = data.reply || "";
  const placeIndex = _buildPlaceIndex(data.places || []);
  const lines = reply.split(/\r?\n/);
  const missing = [];
  for (const url of _extractMapsUrlsFromPlan(reply)) {
    if (_lookupPlace(placeIndex, url)) continue;
    missing.push({ url, query: _queryLabelForUrl(lines, url) });
  }
  if (missing.length) {
    try {
      const res = await fetch("/api/places/enrich/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items: missing, language: "ja" }),
      });
      const body = await res.json();
      if (res.ok && body.places) {
        for (const [url, p] of Object.entries(body.places)) {
          placeIndex[_mapsUrlKey(url)] = p;
        }
      }
    } catch (_) { /* プラン本文のみ */ }
  }
  $("planContent").innerHTML = _renderPlanHtml(reply, placeIndex);

  const places = data.places || [];
  const placesEl = $("planPlacesArea");
  const placesHtml = _renderPlanPlacesRefSection(places);
  if (placesEl) {
    placesEl.innerHTML = placesHtml;
    placesEl.style.display = placesHtml ? "block" : "none";
  }

  const vkEl = $("planVisitKoreaArea");
  const vkHtml = vkEl
    ? _renderVisitKoreaCards(
        data.visitkorea_stays || [],
        data.visitkorea_festivals || [],
        data.visitkorea_attractions || []
      )
    : "";
  if (vkEl) {
    vkEl.innerHTML = vkHtml;
    vkEl.style.display = vkHtml ? "block" : "none";
  }

  const eventsEl = $("planEventsArea");
  const eventsHtml = eventsEl ? _renderPlanEventsCards(data.gyeonggi_events || []) : "";
  if (eventsEl) {
    eventsEl.innerHTML = eventsHtml;
    eventsEl.style.display = eventsHtml ? "block" : "none";
  }

  const sportsEl = $("planSportsArea");
  const sportsHtml = sportsEl ? _renderPlanSportsCards(data.sports_events || []) : "";
  if (sportsEl) {
    sportsEl.innerHTML = sportsHtml;
    sportsEl.style.display = sportsHtml ? "block" : "none";
  }

  const refsEmpty = $("planRefsEmpty");
  if (refsEmpty) {
    const hasRefs = Boolean(placesHtml || vkHtml || eventsHtml || sportsHtml);
    refsEmpty.style.display = hasRefs ? "none" : "block";
  }
}

const _LEAGUE_LABELS = {
  kbo: "KBO（野球）",
  kbl: "KBL（バスケ）",
  kovo: "KOVO（バレー）",
  kleague: "Kリーグ（サッカー）",
  kleague2: "K2（サッカー）",
};

function _renderPlanEventsCards(events) {
  if (!events || !events.length) return "";
  const cards = events.slice(0, 8).map((ev) => {
    const name   = _escapeHtml(ev.name || "");
    const period = ev.start_date === ev.end_date
      ? _escapeHtml(ev.start_date || "")
      : `${_escapeHtml(ev.start_date || "")}〜${_escapeHtml(ev.end_date || "")}`;
    const venue  = ev.venue  ? `<div class="plan-vk-addr">${_escapeHtml(ev.venue)}</div>` : "";
    const city   = ev.city   ? `<span class="plan-vk-badge">${_escapeHtml(ev.city)}</span>` : "";
    const desc   = ev.description
      ? `<div class="plan-ev-desc">${_escapeHtml(ev.description.slice(0, 80))}${ev.description.length > 80 ? "…" : ""}</div>`
      : "";
    const _src = ev.source_service || "";
    const source = _src.startsWith("kintex") ? "KINTEX" : _src === "kpop_web" ? "K-pop 공연" : "전국행사";
    const badge  = `<span class="plan-ev-source">${source}</span>`;
    const inner  = `
      <div class="plan-vk-thumb-wrap"><span class="plan-vk-thumb plan-vk-thumb--fallback" aria-hidden="true">🎭</span></div>
      <div class="plan-vk-text">
        <div class="plan-vk-name">${name}</div>
        <div class="plan-vk-meta">${period}${city ? " · " + city : ""} ${badge}</div>
        ${venue}${desc}
      </div>`;
    return ev.url
      ? `<a class="plan-vk-card" href="${_escapeHtml(ev.url)}" target="_blank" rel="noopener">${inner}</a>`
      : `<div class="plan-vk-card">${inner}</div>`;
  }).join("");
  return `<div class="plan-refs-section">
    <h3 class="plan-refs-title">🎪 旅行期間中の公演・行事</h3>
    <div class="plan-vk-grid">${cards}</div>
  </div>`;
}

function _renderPlanSportsCards(events) {
  if (!events.length) return "";
  const cards = events.map((ev) => {
    const lg = _LEAGUE_LABELS[ev.league] || ev.league || "";
    const isNotice = ev.status === "off_season_notice";
    const time = ev.time ? ` ${ev.time}` : "";
    const url = ev.official_url
      ? `<a href="${_escapeHtml(ev.official_url)}" target="_blank" rel="noopener" class="sport-official">公式日程ページ →</a>`
      : "";
    if (isNotice) {
      return `<div class="sport-event-card sport-event-card--notice">
        <span class="sport-league">${_escapeHtml(lg)}</span>
        <p class="sport-notice-title">${_escapeHtml(ev.home_team || "")}</p>
        <p class="sport-notice-body">${_escapeHtml(ev.away_team || "")}</p>
        ${url}
      </div>`;
    }
    const teams = [ev.home_team, ev.away_team].filter(Boolean).join(" vs ");
    const venue = ev.venue ? `<span class="sport-venue">${_escapeHtml(ev.venue)}</span>` : "";
    return `<div class="sport-event-card">
      <span class="sport-league">${_escapeHtml(lg)}</span>
      <strong>${_escapeHtml(ev.date || "")}${time}</strong>
      <div class="sport-match">${_escapeHtml(teams)}</div>
      ${venue}${url}
    </div>`;
  });
  return `<div class="plan-refs-section"><h3 class="plan-refs-title">⚽ 試合日程（宿泊先近郊・公式データ参照）</h3>
    <div class="plan-sport-grid">${cards.join("")}</div>
    <p class="plan-refs-note">※ 宿泊先近くで開催される試合のみ表示。最新日程・チケットは各公式サイトでご確認ください。</p></div>`;
}

// ── UTILS ─────────────────────────────────────────────────────────────────
function fmtDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
}
function fmtDateJa(d) {
  return `${d.getFullYear()}年${d.getMonth()+1}月${d.getDate()}日`;
}

init();
