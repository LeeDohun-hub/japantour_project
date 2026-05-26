/* Korea Travel Wizard — single-page 9-step flow */

function getCsrfToken() {
  return document.cookie.split(';')
    .map(c => c.trim())
    .find(c => c.startsWith('csrftoken='))
    ?.split('=')[1] ?? '';
}

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
  setupRegionCityPicker();
  setupChipGroup("activityChips",        false);
  setupChipGroup("budgetPriorityChips",  false);
  setupChipGroup("budgetStyleChips",     true);
  setupChipGroup("companionChips",       true);
  setupChipGroup("mobilityChips",        true);
  setupChipGroup("foodPreferenceChips", false);
  setupChipGroup("foodAvoidChips",        false);
  // no_pork ↔ bossam 충돌: 한쪽 선택 시 반대쪽 자동 해제
  $("foodAvoidChips")?.addEventListener("click", () => {
    if (document.querySelector('#foodAvoidChips .chip[data-val="no_pork"].selected')) {
      document.querySelector('#foodPreferenceChips .chip[data-val="bossam"]')?.classList.remove("selected");
    }
  });
  $("foodPreferenceChips")?.addEventListener("click", () => {
    if (document.querySelector('#foodPreferenceChips .chip[data-val="bossam"].selected')) {
      document.querySelector('#foodAvoidChips .chip[data-val="no_pork"]')?.classList.remove("selected");
    }
  });
  setupChipGroup("paceChips",            true);
  setupChipGroup("languageChips",        true);
  setupChipGroup("vacationChips",        false);
  setupChipGroup("sportsChips",          false);
  setupChipGroup("travelStyleChips",     false);
  setupChipGroup("flightTripTypeChips",  true);
  setupSportsDetailToggle();
  setupVacationDetailToggle();
  setupStep6();
  setupNavigation();
  setupTransportInfo();
  setupAddrDropdown();
  setupUndecidedAddrDropdown();
  setupHotelManualSearch();
  setupAccomSearch();
  setupAccomDetailSearch();

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

  if (step === 4) syncTransportChipsForAirport();
  if (step === 5) {
    restoreRegionCityStep();
    syncSportsChipsForRegion();
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
    if (window.PlanMapView?.destroy) window.PlanMapView.destroy();
    wizardData = {};
    _selectedAccomPlace = null;
    const otherIn = $("regionCitiesOther");
    if (otherIn) otherIn.value = "";
    const panels = $("regionCityPanels");
    if (panels) panels.innerHTML = "";
    syncRegionCityPanels();
    goToStep(1);
  });

  $("btnRerollPlan")?.addEventListener("click", () => {
    collect(7);
    generatePlan(true);
    window.scrollTo(0, 0);
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

    if (isRoundTrip() && !wizardData.flight?.selectedReturn) {
      if (errRet) errRet.style.display = "block";
      return false;
    }
    if (errRet) errRet.style.display = "none";
  }
  if (step === 3) {
    const sel = document.querySelector("#accomOptions .option-card.selected");
    const err = $("accomTypeError");
    if (!sel) {
      if (err) err.style.display = "block";
      $("accomOptions")?.scrollIntoView({ behavior: "smooth", block: "center" });
      return false;
    }
    if (err) err.style.display = "none";
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
  if (step === 5) {
    const regions = chips("regionChips");
    const areaErr = $("regionAreaError");
    if (!regions.length) {
      if (areaErr) areaErr.hidden = false;
      $("regionChips")?.scrollIntoView({ behavior: "smooth", block: "center" });
      return false;
    }
    if (areaErr) areaErr.hidden = true;

    const cityCount = document.querySelectorAll("#regionCityPanels .chip.selected").length;
    const cityErr = $("regionCityError");
    if (cityCount === 0) {
      if (cityErr) cityErr.hidden = false;
      $("regionCitySection")?.scrollIntoView({ behavior: "smooth", block: "center" });
      return false;
    }
    if (cityErr) cityErr.hidden = true;
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
      const roundtrip = isRoundTrip();
      const { nights, days } = roundtrip
        ? calcNights($("flightDepart").value, $("flightReturn").value)
        : { nights: 0, days: 1 };
      const prevSelected = wizardData.flight?.selected;
      const prevReturn   = roundtrip ? wizardData.flight?.selectedReturn : null;
      wizardData.flight = {
        tripType:   roundtrip ? "roundtrip" : "oneway",
        from:       $("flightFrom").value,
        to:         $("flightTo").value,
        depart:     $("flightDepart").value,
        returnDate: roundtrip ? $("flightReturn").value : "",
        passengers: +$("passengerStepper").querySelector(".step-val").textContent || 1,
        arrival_airport:   normalizeAirportIata($("flightTo")?.value),
        departure_airport: normalizeAirportIata(
          prevReturn?.dep_iata || $("flightTo")?.value || $("flightFrom")?.value
        ),
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
      wizardData.regions = chips("regionChips");
      wizardData.regionCityIds = getSelectedRegionCityIds();
      const built = buildRegionCitiesString();
      if (built) wizardData.regionCities = built;
      else delete wizardData.regionCities;
      const other = ($("regionCitiesOther")?.value || "").trim();
      if (other) wizardData.regionCitiesOther = other;
      else delete wizardData.regionCitiesOther;
      wizardData.activities = chips("activityChips");
      wizardData.sports     = chips("sportsChips");
      wizardData.vacationTypes = chips("vacationChips");
      if (wizardData.activities.includes("sports") && !wizardData.sports.length) {
        wizardData.sports = ["sports"];
      }
      if (!wizardData.activities.includes("vacation")) {
        wizardData.vacationTypes = [];
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
        foodPreferences:  chips("foodPreferenceChips"),
        foodAvoid:        chips("foodAvoidChips"),
        pace:             chips("paceChips")[0]        || "",
        travelStyles:     chips("travelStyleChips"),
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
function switchAuthTab(tab) {
  const isLogin = tab === "login";
  document.querySelectorAll(".auth-panel-tab").forEach((btn) => {
    const active = btn.dataset.authTab === tab;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  const loginForm = $("s1LoginForm");
  const signupForm = $("s1SignupForm");
  if (loginForm) loginForm.style.display = isLogin ? "flex" : "none";
  if (signupForm) signupForm.style.display = isLogin ? "none" : "flex";
  const errLogin = $("s1LoginError");
  const errSignup = $("s1SignupError");
  if (errLogin) errLogin.textContent = "";
  if (errSignup) errSignup.textContent = "";
}

function setupNavPlanMode() {
  $("btnNavPlanMode")?.addEventListener("click", (e) => {
    const path = (window.location.pathname || "/").replace(/\/$/, "") || "/";
    if (path !== "/") return;
    e.preventDefault();
    goToStep(1);
  });
}

function setupStep1() {
  setupNavPlanMode();
  $("btnLogout")?.addEventListener("click", handleLogout);
  $("btnNavLogout")?.addEventListener("click", handleLogout);

  document.querySelectorAll(".auth-panel-tab").forEach((btn) => {
    btn.addEventListener("click", () => switchAuthTab(btn.dataset.authTab || "login"));
  });

  $("s1TermsLink")?.addEventListener("click", (e) => {
    e.preventDefault();
    alert(
      "【利用規約（概要）】\n\n" +
        "・本サービスは韓国旅行プラン作成の補助を目的とします。\n" +
        "・入力いただいた情報はプラン作成・ログイン管理に利用します。\n" +
        "・外部OAuth（Google/LINE）またはメール登録でログインできます。\n" +
        "・詳細な規約は運営者にお問い合わせください。"
    );
  });

  $("s1LoginForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = $("s1LoginEmail")?.value.trim() || "";
    const password = $("s1LoginPassword")?.value || "";
    const errEl = $("s1LoginError");
    const btn = e.submitter;
    if (errEl) errEl.textContent = "";
    if (!email || !password) {
      if (errEl) errEl.textContent = "メールアドレスとパスワードを入力してください";
      return;
    }
    if (btn) btn.disabled = true;
    try {
      const res = await fetch("/api/auth/login/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
        credentials: "same-origin",
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        if (errEl) errEl.textContent = data.detail || "ログインに失敗しました";
        return;
      }
      setLoggedIn(data.user);
      goToStep(2);
    } catch {
      if (errEl) errEl.textContent = "ネットワークエラー";
    } finally {
      if (btn) btn.disabled = false;
    }
  });

  $("s1SignupForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const display_name = $("s1DisplayName")?.value.trim() || "";
    const email = $("s1SignupEmail")?.value.trim() || "";
    const password = $("s1SignupPassword")?.value || "";
    const password_confirm = $("s1SignupPassword2")?.value || "";
    const terms_accepted = $("s1Terms")?.checked;
    const errEl = $("s1SignupError");
    const btn = e.submitter;
    if (errEl) errEl.textContent = "";

    if (!display_name) {
      if (errEl) errEl.textContent = "表示名を入力してください";
      return;
    }
    if (!email) {
      if (errEl) errEl.textContent = "メールアドレスを入力してください";
      return;
    }
    if (password.length < 8) {
      if (errEl) errEl.textContent = "パスワードは8文字以上必要です";
      return;
    }
    if (password !== password_confirm) {
      if (errEl) errEl.textContent = "パスワード（確認）が一致しません";
      return;
    }
    if (!terms_accepted) {
      if (errEl) errEl.textContent = "利用規約への同意が必要です";
      return;
    }

    if (btn) btn.disabled = true;
    try {
      const res = await fetch("/api/auth/register/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
        credentials: "same-origin",
        body: JSON.stringify({
          display_name,
          email,
          password,
          password_confirm,
          terms_accepted: true,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        if (errEl) errEl.textContent = data.detail || "登録に失敗しました";
        return;
      }
      setLoggedIn(data.user);
      goToStep(2);
    } catch {
      if (errEl) errEl.textContent = "ネットワークエラー";
    } finally {
      if (btn) btn.disabled = false;
    }
  });
}

function _isOAuthInternalName(s) {
  return /^google_\d+$/i.test(s) || /^line_[\w-]+$/i.test(s);
}

function _displayName(user) {
  const name = (user.display_name || "").trim();
  if (name && !_isOAuthInternalName(name)) return name;
  const email = (user.email || "").trim();
  if (email && email.includes("@")) {
    const local = email.split("@")[0].trim();
    if (local && !/^google/i.test(local)) return local;
  }
  return "ゲスト";
}

function _planLoadingTitle(user) {
  const n = _displayName(user);
  return n === "ゲスト"
    ? "あなた専用の旅行プランを作成しています…"
    : `${n}さんの旅行プランを作成しています…`;
}

function _planResultTitle(user) {
  const n = _displayName(user);
  return n === "ゲスト" ? "あなたの旅行プラン" : `${n}さんの旅行プラン`;
}

function _promptGreeting(user) {
  const n = _displayName(user);
  return n === "ゲスト" ? "あなた専用の" : `${n}さんの`;
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
    await fetch("/api/auth/logout/", {
      method: "POST",
      headers: { "X-CSRFToken": getCsrfToken() },
      credentials: "same-origin",
    });
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
  ["s1LoginForm", "s1SignupForm"].forEach((id) => $(id)?.reset());
  switchAuthTab("login");
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
let _flightListWarning = "";
let _returnFlightListWarning = "";
const FLIGHTS_PER_PAGE = 10;

function _flightDepMinutes(f) {
  const raw = (f?.dep_scheduled || f?.arr_scheduled || "99:99").trim();
  const m = /^(\d{1,2}):(\d{2})$/.exec(raw);
  if (!m) return 9999;
  return parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
}

function _sortFlightsByDepTime(list) {
  return [...list].sort((a, b) => _flightDepMinutes(a) - _flightDepMinutes(b));
}
let _allHotels = [];
let _hotelPage = 0;
let _hotelArea = "";
let _hotelSearchMode = "recommend"; // "recommend" | "manual"
let _selectedHotel = null;          // hotel chosen while in undecided mode
const HOTELS_PER_PAGE = 5;

const AIRPORT_IATA_LABELS = {
  ICN: "仁川国際空港",
  CJU: "済州国際空港",
  PUS: "金海国際空港",
  GMP: "金浦国際空港",
};

function normalizeAirportIata(code) {
  const c = String(code || "").trim().toUpperCase().slice(0, 3);
  return Object.prototype.hasOwnProperty.call(AIRPORT_IATA_LABELS, c) ? c : "ICN";
}

function getArrivalAirportIata() {
  const to = wizardData.flight?.to || $("flightTo")?.value;
  return normalizeAirportIata(to);
}

function getDepartureAirportIata() {
  const ret = wizardData.flight?.selectedReturn?.dep_iata
    || wizardData.flight?.from
    || $("flightFrom")?.value;
  return normalizeAirportIata(ret);
}

function _isJejuOnlyTrip() {
  const regions = chips("regionChips");
  return regions.length === 1 && regions[0] === "jeju";
}

function isRoundTrip() {
  const v = document.querySelector("#flightTripTypeChips .chip.selected")?.dataset.val;
  return v !== "oneway";
}

function _clearFlightSelections() {
  if (!wizardData.flight) return;
  delete wizardData.flight.selected;
  delete wizardData.flight.selectedReturn;
  $("flightListCards")?.querySelectorAll(".flight-sel-card").forEach((c) => {
    c.classList.remove("selected");
  });
  $("returnFlightListCards")?.querySelectorAll(".flight-sel-card").forEach((c) => {
    c.classList.remove("selected");
  });
}

function _scheduleFlightRefetch() {
  clearTimeout(_flightFetchTimer);
  clearTimeout(_returnFlightFetchTimer);
  _flightFetchTimer = setTimeout(fetchFlightList, 300);
  _returnFlightFetchTimer = setTimeout(fetchReturnFlightList, 300);
}

function syncFlightTripUi() {
  const roundtrip = isRoundTrip();
  const retField = $("flightReturnField");
  const retSection = $("returnFlightListSection");
  const retLabel = $("returnFlightLegLabel");
  const errRet = $("flightReturnSelError");

  if (retField) retField.style.display = roundtrip ? "" : "none";
  if (retLabel) retLabel.style.display = roundtrip ? "" : "none";
  if (errRet) errRet.style.display = "none";

  if (!roundtrip) {
    if (retSection) retSection.style.display = "none";
    _allReturnFlights = [];
    if (wizardData.flight) delete wizardData.flight.selectedReturn;
    $("returnFlightListCards")?.querySelectorAll(".flight-sel-card").forEach((c) => {
      c.classList.remove("selected");
    });
  } else {
    fetchReturnFlightList();
  }
}

function setupStep2() {
  const onAirportChange = () => {
    if (wizardData.flight) {
      wizardData.flight.to = $("flightTo")?.value;
      wizardData.flight.from = $("flightFrom")?.value;
    }
    _clearFlightSelections();
    _scheduleFlightRefetch();
    if (currentStep === 4) syncTransportChipsForAirport();
  };
  $("flightTo")?.addEventListener("change", onAirportChange);
  $("flightFrom")?.addEventListener("change", onAirportChange);

  $("flightTripTypeChips")?.addEventListener("click", () => {
    setTimeout(() => {
      syncFlightTripUi();
      _clearFlightSelections();
      _scheduleFlightRefetch();
    }, 0);
  });
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
    _clearFlightSelections();
    _scheduleFlightRefetch();
  });

  ["flightFrom", "flightTo", "flightDepart", "flightReturn"].forEach((id) => {
    $(id)?.addEventListener("change", () => {
      if (id === "flightReturn" || id === "flightDepart") {
        _clearFlightSelections();
      }
      _scheduleFlightRefetch();
    });
  });

  syncFlightTripUi();
  fetchFlightList();
  if (isRoundTrip()) fetchReturnFlightList();
}

async function fetchFlightList() {
  const dep  = ($("flightFrom")?.value || "").trim();
  const arr  = ($("flightTo")?.value  || "ICN").trim();
  if (dep && arr && dep === arr) {
    const section = $("flightListSection");
    const label = $("flightListLabel");
    if (section) section.style.display = "block";
    if (label) label.textContent = "出発地と目的地が同じです";
    $("flightListCards").innerHTML =
      `<p class="flight-list-empty">別の空港を選んでください。</p>`;
    return;
  }
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
    label.textContent = "出発地を選択してください";
    cards.innerHTML = "";
    if (pager) pager.style.display = "none";
    return;
  }

  // Increment generation so any in-flight request becomes stale
  const gen = ++_fetchGen;

  section.style.display = "block";
  if (pager) pager.style.display = "none";
  spinner.style.display = "inline";
  label.textContent = `${dep} → ${arr}  到着便 照会中…`;
  cards.innerHTML = "";
  _allFlights = [];
  _flightPage = 0;

  try {
    const qs  = new URLSearchParams({ dep, arr, ...(date && { date }) });
    const res = await fetch(`/api/flights/?${qs}`);
    const data = await res.json();

    // Discard if a newer fetch was started while we awaited
    if (gen !== _fetchGen) return;

    if (!res.ok || data.error) throw new Error(data.error || "照会に失敗しました");

    _allFlights = _sortFlightsByDepTime(data.flights || []);
    _flightListWarning = data.warning || "";
    const src =
      data.source === "airport_co_kr" ? " · 韓国空港公社API" : "";
    label.textContent = `${dep} → ${arr}  ${date || "出発日"}  計${_allFlights.length}便${src}`;
    if (_allFlights.length === 0) {
      cards.innerHTML = `<p class="flight-list-empty">該当する便がありません。路線または日付を変更してください。</p>`;
      return;
    }
    renderFlightPage(0);
    setupPager();
  } catch (err) {
    if (gen !== _fetchGen) return;
    label.textContent = "照会失敗";
    cards.innerHTML = `<p class="flight-list-empty">${err.message}</p>`;
  } finally {
    if (gen === _fetchGen) spinner.style.display = "none";
  }
}

async function fetchReturnFlightList() {
  const section = $("returnFlightListSection");
  if (!isRoundTrip()) {
    if (section) section.style.display = "none";
    _allReturnFlights = [];
    return;
  }

  const dep  = ($("flightTo")?.value || "ICN").trim();
  const arr  = ($("flightFrom")?.value || "").trim();
  const date = $("flightReturn")?.value || "";
  const cards   = $("returnFlightListCards");
  const label   = $("returnFlightListLabel");
  const spinner = $("returnFlightListLoading");
  const pager   = $("returnFlightListPager");
  if (!section || !cards) return;

  if (dep && arr && dep === arr) {
    section.style.display = "block";
    label.textContent = "出発地と目的地が同じです";
    cards.innerHTML =
      `<p class="flight-list-empty">別の空港を選んでください。</p>`;
    if (pager) pager.style.display = "none";
    return;
  }

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

    if (!res.ok || data.error) throw new Error(data.error || "照会に失敗しました");

    _allReturnFlights = _sortFlightsByDepTime(data.flights || []);
    _returnFlightListWarning = data.warning || "";
    const srcRet =
      data.source === "airport_co_kr" ? " · 韓国空港公社API" : "";
    label.textContent = `${dep} → ${arr}  ${date || "帰国日"}  計${_allReturnFlights.length}便${srcRet}`;
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
  const warn = _flightListWarning
    ? `<p class="flight-list-warn">${escHtml(_flightListWarning)}</p>`
    : "";
  cards.innerHTML =
    warn +
    slice.map((f, i) => renderFlightSelectCard(f, start + i, "arrival")).join("");
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
  const warn = _returnFlightListWarning
    ? `<p class="flight-list-warn">${escHtml(_returnFlightListWarning)}</p>`
    : "";
  cards.innerHTML =
    warn +
    slice.map((f, i) => renderFlightSelectCard(f, start + i, "departure")).join("");
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
  const aliases = [...new Set((f.codeshare_aliases || []).filter(Boolean))];
  const MAX_ALIASES = 4;
  const aliasShown = aliases.slice(0, MAX_ALIASES);
  const aliasMore = aliases.length > MAX_ALIASES ? ` 외 ${aliases.length - MAX_ALIASES}편` : "";
  const aliasHtml = aliasShown.length
    ? `<span class="fsc-aliases">+ ${aliasShown.join(" · ")}${aliasMore}</span>`
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

// ── 観光：広域 → 都市・区 ─────────────────────────────────────────────────
function _escapeAttr(s) {
  return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;");
}

function setupRegionCityPicker() {
  const regionEl = $("regionChips");
  const panels = $("regionCityPanels");
  if (!regionEl || !panels) return;

  regionEl.addEventListener("click", () => {
    setTimeout(() => {
      syncRegionCityPanels();
      syncSportsChipsForRegion();
    }, 0);
  });

  panels.addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip?.dataset?.val) return;
    chip.classList.toggle("selected");
    const err = $("regionCityError");
    if (err) err.hidden = true;
  });

  $("regionCitiesOther")?.addEventListener("input", () => {
    const err = $("regionCityError");
    if (err && ($("regionCitiesOther").value || "").trim()) err.hidden = true;
  });

  syncRegionCityPanels();
}

const _REGION_ICONS = {
  seoul: "🏙",
  gyeonggi: "🌳",
  incheon: "✈",
  gangwon: "⛰",
  chungcheong: "🌾",
  jeolla: "🌊",
  gyeongsang: "🏯",
  jeju: "🌺",
};

function syncRegionCityPanels() {
  const selected = chips("regionChips");
  const panels = $("regionCityPanels");
  const placeholder = $("regionCityPlaceholder");
  if (!panels) return;

  if (!selected.length) {
    panels.innerHTML = "";
    if (placeholder) placeholder.hidden = false;
    return;
  }
  if (placeholder) placeholder.hidden = true;

  const savedIds = new Set(wizardData.regionCityIds || []);
  const opts = window.REGION_CITY_OPTIONS || {};
  const labels = window.REGION_AREA_LABELS || {};
  if (!Object.keys(opts).length) {
    panels.innerHTML =
      '<p class="region-city-load-error">都市・区リストの読み込みに失敗しました。ページを再読み込みしてください。</p>';
    return;
  }
  let html = "";

  for (const reg of selected) {
    const cities = opts[reg];
    if (!cities?.length) continue;
    const title = labels[reg] || reg;
    const icon = _REGION_ICONS[reg] || "📍";
    html += `<div class="region-city-group" data-region="${reg}">`;
    html += `<h4 class="region-city-group__title">${icon} ${title}</h4>`;
    html += `<div class="chip-grid region-city-grid">`;
    for (const c of cities) {
      const id = `${reg}:${c.id}`;
      const sel = savedIds.has(id) ? " selected" : "";
      html += `<button type="button" class="chip${sel}" data-region="${reg}" data-val="${c.id}" data-query="${_escapeAttr(c.query)}">${c.label}</button>`;
    }
    html += `</div></div>`;
  }
  panels.innerHTML = html;
}

function getSelectedRegionCityIds() {
  const ids = [];
  document.querySelectorAll("#regionCityPanels .chip.selected").forEach((chip) => {
    if (chip.dataset.region && chip.dataset.val) {
      ids.push(`${chip.dataset.region}:${chip.dataset.val}`);
    }
  });
  return ids;
}

function buildRegionCitiesString() {
  const parts = [];
  document.querySelectorAll("#regionCityPanels .chip.selected").forEach((chip) => {
    const q = (chip.dataset.query || "").trim();
    if (q) parts.push(q);
  });
  const other = ($("regionCitiesOther")?.value || "").trim();
  if (other) {
    other.split(/[,、/・\n|]+/).forEach((t) => {
      const s = t.trim();
      if (s) parts.push(s);
    });
  }
  return [...new Set(parts)].join("・");
}

function restoreRegionCityStep() {
  const regions = wizardData.regions || [];
  document.querySelectorAll("#regionChips .chip").forEach((c) => {
    c.classList.toggle("selected", regions.includes(c.dataset.val));
  });
  syncRegionCityPanels();

  const otherIn = $("regionCitiesOther");
  if (otherIn) {
    otherIn.value = wizardData.regionCitiesOther || "";
    if (!wizardData.regionCitiesOther && wizardData.regionCities && !wizardData.regionCityIds?.length) {
      otherIn.value = wizardData.regionCities;
    }
  }

  if (wizardData.regionCityIds?.length) {
    wizardData.regionCityIds.forEach((id) => {
      const [reg, val] = id.split(":");
      const chip = document.querySelector(
        `#regionCityPanels .chip[data-region="${reg}"][data-val="${val}"]`
      );
      chip?.classList.add("selected");
    });
  }
}

function setupSportsDetailToggle() {
  const activityEl = $("activityChips");
  if (activityEl) {
    activityEl.addEventListener("click", () => {
      setTimeout(() => {
        syncSportsDetail();
        syncSportsChipsForRegion();
      }, 0);
    });
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

function setupVacationDetailToggle() {
  const activityEl = $("activityChips");
  if (activityEl) {
    activityEl.addEventListener("click", () => setTimeout(syncVacationDetail, 0));
  }
}

function syncVacationDetail() {
  const block = $("vacationDetailBlock");
  if (!block) return;
  const show = chips("activityChips").includes("vacation");
  block.style.display = show ? "block" : "none";
  if (!show) {
    $("vacationChips")?.querySelectorAll(".chip.selected").forEach((c) => {
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
let _planRerollCount = 0;

const PLAN_MSGS = [
  "情報を整理しています...",
  "旅行データを分析しています...",
  "K-Cultureデータベースを参照中...",
  "プランを生成しています...",
];

function _collectPlanPlaceNames(reply, places) {
  const names = new Set();
  for (const p of _placesLinkedInPlan(reply, places)) {
    if (p.name) names.add(p.name.trim());
  }
  for (const ln of (reply || "").split(/\r?\n/)) {
    const m = ln.match(/^\[(?:午前|午後|昼食|夕食|夜)\]\s*(.+?)(?:\s*（|\s*$)/);
    if (m && m[1].length < 80) names.add(m[1].trim());
  }
  return [...names].slice(0, 30);
}

function _buildPlanAutoDefaults(d) {
  const days = Math.max(1, Number(d.days || 3));
  const seedText = [
    ...(d.regions || []),
    d.regionCities || "",
    d.regionCitiesOther || "",
    String(days),
  ].join("|");
  let seed = 0;
  for (const ch of seedText) seed = (seed + ch.charCodeAt(0)) % 997;

  const foodSets = [
    ["grilled_meat", "soup", "cafe"],
    ["bossam", "noodles", "cafe"],
    ["chicken", "snack", "soup"],
    ["seafood", "grilled_meat", "cafe"],
  ];
  const styleSets = [
    ["must_see", "food_first", "local_vibe"],
    ["sns_hot", "culture", "food_first"],
    ["healing", "nature", "cafe"],
    ["experience", "local_vibe", "food_first"],
  ];
  const idx = seed % foodSets.length;
  const dailyJpy = days >= 5 ? 12000 : 10000;
  return {
    budget: {
      currency: "JPY",
      daily: dailyJpy,
      total: dailyJpy * days,
      style: "normal",
      auto: true,
    },
    additional: {
      companion: "friends",
      pace: days >= 4 ? "relaxed" : "packed",
      foodPreferences: foodSets[idx],
      travelStyles: styleSets[idx],
      auto: true,
    },
  };
}

async function generatePlan(isReroll = false) {
  const barEl    = $("planBar");
  const pctEl    = $("planPct");
  const statusEl = $("planStatus");
  $("planTitle").textContent     = _planLoadingTitle(currentUser || {});
  $("planLoadingArea").style.display = "block";
  $("planOutputArea").style.display  = "none";
  $("planErrorArea").style.display   = "none";
  if (window.PlanMapView?.destroy) window.PlanMapView.destroy();

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

  if (isReroll) {
    _planRerollCount += 1;
    wizardData.plan_reroll = _planRerollCount;
    wizardData.plan_variant_seed = Date.now();
  } else {
    _planRerollCount = 0;
    wizardData.plan_reroll = 0;
    delete wizardData.plan_variant_seed;
    delete wizardData.avoid_place_names;
  }

  const autoDefaults = _buildPlanAutoDefaults(wizardData);
  const userAdditional = wizardData.additional || {};
  const mergedAdditional = {
    ...autoDefaults.additional,
    ...userAdditional,
    foodPreferences: userAdditional.foodPreferences?.length
      ? userAdditional.foodPreferences
      : autoDefaults.additional.foodPreferences,
    travelStyles: userAdditional.travelStyles?.length
      ? userAdditional.travelStyles
      : autoDefaults.additional.travelStyles,
  };
  const profilePayload = {
    ...wizardData,
    budget: wizardData.budget?.total ? wizardData.budget : autoDefaults.budget,
    additional: mergedAdditional,
    plan_auto_defaults: {
      budget: !wizardData.budget?.total,
      foodPreferences: !userAdditional.foodPreferences?.length,
      details: !userAdditional.companion || !userAdditional.pace || !userAdditional.travelStyles?.length,
    },
    plan_mode: true,
    arrival_airport: wizardData.flight?.arrival_airport || getArrivalAirportIata(),
    departure_airport: wizardData.flight?.departure_airport || getDepartureAirportIata(),
  };

  try {
    const res = await fetch("/api/chat/stream/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
      credentials: "same-origin",
      body: JSON.stringify({
        message:          buildPrompt(isReroll),
        reply_language:   "日本語",
        session_id:       null,
        history:          [],
        traveler_profile: profilePayload,
      }),
    });
    if (!res.ok) {
      const eb = await res.json().catch(() => ({}));
      throw new Error(eb.detail || `HTTP ${res.status}`);
    }

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let sseBuf = "", metaData = {}, fullReply = "", charCount = 0;

    outer: while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      sseBuf += decoder.decode(value, { stream: true });
      const lines = sseBuf.split("\n");
      sseBuf = lines.pop();
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        let msg;
        try { msg = JSON.parse(line.slice(6)); } catch { continue; }
        if (msg.type === "meta") {
          metaData = msg;
          clearInterval(timer);
          progress = 88; barEl.style.width = "88%"; pctEl.textContent = "88%";
          statusEl.textContent = "プランを書いています... (0 文字)";
        } else if (msg.type === "token") {
          fullReply += msg.delta || "";
          charCount += (msg.delta || "").length;
          statusEl.textContent = `プランを書いています... (${charCount} 文字)`;
        } else if (msg.type === "done") {
          clearInterval(timer);
          barEl.style.width = "100%"; pctEl.textContent = "100%";
          break outer;
        } else if (msg.type === "error") {
          throw new Error(msg.message || "stream error");
        }
      }
    }

    setTimeout(async () => {
      $("planLoadingArea").style.display = "none";
      $("planTitle").textContent = _planResultTitle(currentUser || {});
      await _displayPlanOutput({ ...metaData, reply: fullReply });
      $("planOutputArea").style.display = "block";
    }, 400);

  } catch {
    clearInterval(timer);
    $("planLoadingArea").style.display = "none";
    $("planErrorArea").style.display   = "block";
    $("btnRetryPlan").onclick = generatePlan;
  }
}

function buildPrompt(isReroll = false) {
  const d = wizardData;
  const autoDefaults = _buildPlanAutoDefaults(d);
  const userAdditional = d.additional || {};
  const promptAdditional = {
    ...autoDefaults.additional,
    ...userAdditional,
    foodPreferences: userAdditional.foodPreferences?.length
      ? userAdditional.foodPreferences
      : autoDefaults.additional.foodPreferences,
    travelStyles: userAdditional.travelStyles?.length
      ? userAdditional.travelStyles
      : autoDefaults.additional.travelStyles,
  };
  const promptBudget = d.budget?.total ? d.budget : autoDefaults.budget;
  const sym = d.budget?.currency === "KRW" ? "₩" : "¥";
  const rMap = { seoul:"ソウル", gyeonggi:"京畿道", incheon:"仁川", gangwon:"江原道",
                 chungcheong:"忠清道", jeolla:"全羅道", gyeongsang:"慶尚道", jeju:"済州島" };
  const aMap = { food:"グルメ", shopping:"ショッピング", nightview:"夜景", tradition:"伝統文化",
                 hallyu:"韓流・K-pop", drama:"ドラマ", kpop:"K-pop", cafe:"カフェ巡り",
                 nature:"自然", photo:"フォトスポット", sports:"スポーツ観戦", vacation:"バカンス" };
  const vacMap = { poolvilla:"プールヴィラ", pension:"ペンション" };
  const tsMap = {
    experience:"体験・アクティビティ", sns_hot:"SNS人気スポット", nature:"自然と一緒に",
    must_see:"有名観光地は必須", healing:"ゆったり癒し", culture:"文化・芸術・歴史",
    local_vibe:"旅行地の雰囲気たっぷり", shop_hard:"ショッピングは本気", food_first:"観光よりグルメ",
  };
  const tMap = { rail:"鉄道・地下鉄（AREX・広域鉄道）", taxi:"タクシー", bus:"空港バス", rental:"レンタカー",
                 arex:"鉄道・地下鉄（AREX）", subway:"鉄道・地下鉄" }; // 하위호환
  const cMap = { solo:"一人旅", couple:"カップル", friends:"友人", family:"ファミリー", parents:"親孝行" };
  const pMap = { packed:"びっしり", relaxed:"のんびり" };
  const sMap = { budget:"コスパ重視", normal:"バランス", premium:"プレミアム" };

  const lines = [
    `${_promptGreeting(currentUser || {})}韓国旅行プランを日本語で作成してください。以下の情報を基に、日程ごとの具体的なプランを提案してください。`,
  ];

  if (d.flight) {
    const f = d.flight;
    const arrAp = f.arrival_airport || normalizeAirportIata(f.to);
    const depAp = f.departure_airport || normalizeAirportIata(f.from);
    lines.push(
      `【フライト】${f.from}→${f.to}、出発:${f.depart||"未定"}、帰国:${f.returnDate||"未定"}、${f.passengers}名`,
      `【到着空港】${AIRPORT_IATA_LABELS[arrAp] || arrAp}（IATA:${arrAp}）`,
      `【出国空港】${AIRPORT_IATA_LABELS[depAp] || depAp}（IATA:${depAp}）`,
    );
    if (arrAp === "CJU") {
      lines.push(
        "【済州到着 — 交通】仁川AREX・仁川リムジンは使わない。空港→宿泊は済州空港バス（リムジン）を優先。地下鉄は利用可だが必須ではない。"
      );
    } else if (arrAp === "PUS") {
      lines.push("【金海到着 — 交通】AREXは使わない。金海空港バスを優先。");
    } else if (arrAp === "GMP") {
      lines.push("【金浦到着 — 交通】AREXは使わない。地下鉄・空港リムジンを優先。");
    } else if (arrAp === "ICN") {
      lines.push("【仁川到着 — 交通】AREX・リムジン・地下鉄のいずれか1つを明示（路線名・所要時間）。");
    }
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
      const depApLabel = AIRPORT_IATA_LABELS[depAp] || depAp;
      lines.push(
        `【最終日 出国便】${retSel.flight_iata || ""} ${depApLabel}出発予定:${depTime}${term}${gate}`
      );
      lines.push(
        `（国際線:出発2〜3時間前に${depApLabel}到着・チェックイン推奨。最終日の観光・食事は出発時刻から逆算して終了）`
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
  if (d.regionCityIds?.length && window.REGION_CITY_OPTIONS) {
    const cityLabels = [];
    for (const id of d.regionCityIds) {
      const [reg, val] = id.split(":");
      const opt = (window.REGION_CITY_OPTIONS[reg] || []).find((c) => c.id === val);
      if (opt) cityLabels.push(opt.label);
    }
    if (cityLabels.length) {
      lines.push(`【訪問したい市・郡・区】${cityLabels.join("・")}（各日の中心にする）`);
    }
  }
  if (d.regionCities)
    lines.push(`【検索・Places用キーワード】${d.regionCities}`);
  const spMap = { soccer:"サッカー観戦", baseball:"野球観戦", basketball:"バスケ観戦", volleyball:"バレー観戦", sports:"スポーツ観戦（全競技）" };
  const legacyHallyu = (d.additional?.hallyu || []).filter((h) => h !== "traditional");
  const actMerged = [...(d.activities || [])];
  for (const h of legacyHallyu) {
    const v = h === "hallyu" ? "kpop" : h;
    if (v && !actMerged.includes(v)) actMerged.push(v);
  }
  const actFiltered = actMerged.filter((a) => a !== "sports");
  const activityParts = actFiltered.map((a) => aMap[a] || a);
  const sportParts = (d.sports || []).map((s) => spMap[s] || s);
  if (activityParts.length) {
    lines.push(`【やりたいこと】${activityParts.join("・")}`);
  }
  if (sportParts.length) {
    lines.push(`【スポーツ観戦】${sportParts.join("・")} — Reference Dataの試合日程をプランに組み込むこと`);
  }
  const vacParts = (d.vacationTypes || []).map((v) => vacMap[v] || v);
  if (vacParts.length || actMerged.includes("vacation")) {
    lines.push(
      `【バカンス】${vacParts.length ? vacParts.join("・") : "バカンス"} — プールヴィラ・ペンション・リゾート滞在を意識した日程にすること`
    );
  }

  if (promptBudget?.total) {
    const bsSym = promptBudget.currency === "KRW" ? "₩" : "¥";
    let bs = `総予算:${bsSym}${promptBudget.total}`;
    if (promptBudget.daily) bs += `、1日:${bsSym}${promptBudget.daily}`;
    if (promptBudget.style) bs += `、予算の考え方:${sMap[promptBudget.style]||promptBudget.style}`;
    if (promptBudget.auto) bs += "（未入力のためシステムが標準値を設定）";
    lines.push(`【予算】${bs}`);
  }

  const add = promptAdditional;
  if (add) {
    const parts = [];
    if (add.companion)              parts.push(cMap[add.companion]||add.companion);
    if (add.pace)                   parts.push(pMap[add.pace]||add.pace);
    const prefMap = {
      grilled_meat: "焼肉・サムギョプサル", bossam: "보쌈・족발・돼지국밥",
      soup: "スープ・チゲ・クッパ", noodles: "麺類",
      seafood: "海鮮・生魚", chicken: "韓国チキン",
      snack: "分食・軽食", cafe: "カフェ・スイーツ",
    };
    const avoidMap = {
      no_spicy: "辛いものは苦手", allergy: "アレルギーあり", vegan: "ベジタリアン",
      no_pork: "豚肉なし",
      spicy: "辛いものは苦手", // 旧データ互換
    };
    const prefs = add.foodPreferences?.length
      ? add.foodPreferences
      : [];
    const avoid = [
      ...(add.foodAvoid || []),
      ...(add.foodRestrictions || []).filter((x) => x !== "vegan" || !prefs.includes("healthy")),
    ];
    if (prefs.length) {
      lines.push(
        `【食事の好み】${prefs.map((p) => prefMap[p] || p).join("・")} — ${add.auto ? "未入力のためシステムが標準設定。" : ""}韓国料理店で上記メニューが食べられる店を昼食・夕食に優先（配達専門・持ち帰り専門店は不可）`
      );
    }
    if (avoid.length) {
      const avoidUnique = [...new Set(avoid.map((a) => avoidMap[a] || a))];
      lines.push(`【食事で避ける】${avoidUnique.join("・")}`);
    }
    if (add.travelStyles?.length) {
      const tsLabels = add.travelStyles.map((t) => tsMap[t] || t);
      parts.push(`旅行スタイル:${tsLabels.join("・")}`);
    }
    if (add.note)                   parts.push(add.note);
    if (parts.length) lines.push(`【その他】${parts.join("、")}`);
  }

  if (d.regions?.length) {
    lines.push(
      "【到着日】1日目は入国・移動・チェックイン・休息のみ。観光・食事は【希望エリア】の順で2日目以降に配置（宿泊先の市区だけで観光エリアを決めない）。"
    );
  }
  if (isReroll) {
    const avoid = wizardData.avoid_place_names || [];
    lines.push(
      "【プラン再生成】前回とは別の店・観光スポットを優先すること。Reference Data内の別候補を積極的に使う。",
      avoid.length
        ? `【前回使用した店・スポット（今回は使わない）】${avoid.join("、")}`
        : "【前回使用した店・スポット】直前プランに出た店名・施設名はできるだけ避け、別の候補を選ぶ。",
    );
  }
  lines.push(
    "\n地図アプリへの検索依頼は禁止。",
    "【言語】本文は必ず日本語。韓国語の説明文（■1일째、한식점で 等）は禁止。店名の韓国語表記のみ可。",
    "【表示形式】時刻レンジ（例:[10:00〜11:00]）は書かない。各日は「1日目」「2日目」見出し＋「①②③」または「午前」「昼食」「午後」「夕食」。",
    "【食事 — 厳守】Reference Dataの「食事候補」リストの実在店のみ。店名の次の行に google_maps_uri をコピー。リストが空なら店名禁止（「近郊で食事」の1行のみ）。「한식店」「現地のレストラン」「別の韓国料理店」は絶対禁止。",
    "【観光】「観光スポット候補」リストの施設名＋URLのみ。リスト外の創作禁止。",
    "【スポーツ】Sports Schedule Resultsの試合またはオフシーズン案内をそのまま記載。ジム・ストリートへの置き換え禁止。",
    "営業時間・料金・チケットは文末で一言のみ。"
  );
  return lines.join("\n");
}

// ── TRANSPORT INFO PANEL ──────────────────────────────────────────────────
const TRANSPORT_BUS_BY_AIRPORT = {
  ICN: `<div class="ti-card"><strong>🚌 空港リムジンバス（仁川）</strong>
ソウル市内・京畿方面への直行バス（6000〜18000番台など）<br>
<a href="https://www.airportlimousine.co.kr/" target="_blank" rel="noopener">▶ 空港リムジン 公式（時刻表・乗り場）</a>
 · <a href="https://www.bustago.or.kr/newweb/kr/index.do" target="_blank" rel="noopener">バスタゴ（全国）</a></div>`,
  CJU: `<div class="ti-card"><strong>🚌 済州空港バス</strong>
<a href="https://bus.jeju.go.kr/?lang=ko" target="_blank" rel="noopener">▶ 済州空港バス 公式</a></div>`,
  PUS: `<div class="ti-card"><strong>🚌 金海空港バス</strong>
<a href="https://newbusan.net/airportbus/info_bus_stop.html" target="_blank" rel="noopener">▶ 金海国際空港 バス案内</a></div>`,
  GMP: `<div class="ti-card"><strong>🚌 金浦空港バス</strong>
ソウル市内へのリムジン・空港バス<br>
<a href="https://www.airportlimousine.co.kr/" target="_blank" rel="noopener">▶ 空港リムジン 公式</a></div>`,
};

const LOCAL_RAIL_OFFICIAL_LINKS = `
<div class="ti-links-note">地方移動・都市鉄道の公式リンク</div>
<a href="https://info.korail.com/info/contents.do?key=857" target="_blank" rel="noopener">KORAIL 路線図・時刻表</a> ·
<a href="https://www.humetro.busan.kr/" target="_blank" rel="noopener">釜山交通公社</a> ·
<a href="https://www.grtc.co.kr/" target="_blank" rel="noopener">光州交通公社</a> ·
<a href="https://www.dtro.or.kr/cmsh/dtro.or.kr/html/nosundo.html" target="_blank" rel="noopener">大邱都市鉄道 路線図</a>`;

const TRANSPORT_RAIL_BY_AIRPORT = {
  ICN: `<div class="ti-card"><strong>🚆 鉄道・地下鉄（AREX・広域鉄道）</strong>
仁川空港↔ソウル駅 AREX直通約43分 / 一般約51分。乗換で広域鉄道・地下鉄（1・9号線等）<br>
<a href="https://www.arex.or.kr/jp/" target="_blank" rel="noopener">▶ AREX 公式</a> ·
<a href="https://www.seoulmetro.co.kr/jp/" target="_blank" rel="noopener">ソウル交通公社</a> ·
${LOCAL_RAIL_OFFICIAL_LINKS}</div>`,
  GMP: `<div class="ti-card"><strong>🚆 鉄道・地下鉄（広域鉄道）</strong>
金浦空港↔ソウル市内 空港鉄道・9号線等（AREXは利用しません）<br>
<a href="https://www.seoulmetro.co.kr/jp/" target="_blank" rel="noopener">▶ ソウル交通公社</a> ·
${LOCAL_RAIL_OFFICIAL_LINKS}</div>`,
  PUS: `<div class="ti-card"><strong>🚆 釜山・地方鉄道</strong>
金海空港↔釜山市内は釜山-金海軽電鉄・釜山都市鉄道連携。KTX・ITXなど地方移動はKORAILを確認<br>
${LOCAL_RAIL_OFFICIAL_LINKS}</div>`,
  CJU: `<div class="ti-card"><strong>🚆 地方鉄道・都市鉄道</strong>
済州島内に地下鉄はありません。韓国内の都市間移動はKORAIL、釜山・光州・大邱などの都市鉄道は各公式路線図を確認<br>
${LOCAL_RAIL_OFFICIAL_LINKS}</div>`,
};

const TRANSPORT_INFO = {
  rail: TRANSPORT_RAIL_BY_AIRPORT.ICN,
  subway: TRANSPORT_RAIL_BY_AIRPORT.ICN,
  taxi: `<div class="ti-card"><strong>🚕 タクシー / KakaoTaxi</strong>
<a href="https://www.kakaomobility.com/" target="_blank" rel="noopener">▶ KakaoTaxi</a></div>`,
  bus: TRANSPORT_BUS_BY_AIRPORT.ICN,
  rental: `<div class="ti-card"><strong>🚗 レンタカー</strong>
<a href="https://www.lotterentacar.net/" target="_blank" rel="noopener">▶ 各社レンタカー</a></div>`,
  arex: TRANSPORT_RAIL_BY_AIRPORT.ICN,
};

function syncTransportChipsForAirport() {
  const iata = getArrivalAirportIata();
  const label = AIRPORT_IATA_LABELS[iata] || iata;
  const hint = $("transportAirportHint");
  const chipRail = $("transportChipRail");
  const chipBus = $("transportChipBus");

  if (hint) {
    hint.style.display = "block";
    hint.textContent = `到着空港: ${label} — 利用可能な交通手段を表示しています。`;
  }

  const showRail = iata === "ICN" || iata === "GMP";

  if (chipRail) {
    chipRail.style.display = showRail ? "" : "none";
    chipRail.textContent =
      iata === "GMP"
        ? "🚆 地下鉄・広域鉄道"
        : "🚆 鉄道・地下鉄（AREX・広域鉄道）";
    if (!showRail && chipRail.classList.contains("selected")) chipRail.classList.remove("selected");
    TRANSPORT_INFO.rail = TRANSPORT_RAIL_BY_AIRPORT[iata] || TRANSPORT_RAIL_BY_AIRPORT.ICN;
    TRANSPORT_INFO.subway = TRANSPORT_INFO.rail;
    TRANSPORT_INFO.arex = TRANSPORT_INFO.rail;
  }
  if (chipBus) {
    chipBus.style.display = "";
    chipBus.textContent =
      iata === "CJU"
        ? "🚌 済州空港バス"
        : iata === "PUS"
          ? "🚌 空港バス（金海）"
          : iata === "GMP"
            ? "🚌 空港バス（金浦）"
            : "🚌 空港リムジン";
  }
  TRANSPORT_INFO.bus = TRANSPORT_BUS_BY_AIRPORT[iata] || TRANSPORT_BUS_BY_AIRPORT.ICN;
}

function setupTransportInfo() {
  const el = $("transportChips");
  const panel = $("transportInfoPanel");
  if (!el || !panel) return;

  syncTransportChipsForAirport();

  el.addEventListener("click", () => {
    requestAnimationFrame(() => {
      const selected = chips("transportChips");
      if (!selected.length) {
        panel.style.display = "none";
        panel.innerHTML = "";
        return;
      }
      panel.innerHTML = selected.map((t) => TRANSPORT_INFO[t] || "").join("");
      panel.style.display = "block";
    });
  });
}

function syncSportsChipsForRegion() {
  const jejuOnly = _isJejuOnlyTrip();
  const chipBaseball = $("sportsChipBaseball");
  const chipSoccer = $("sportsChipSoccer");
  if (chipBaseball) {
    chipBaseball.style.display = jejuOnly ? "none" : "";
    if (jejuOnly && chipBaseball.classList.contains("selected")) {
      chipBaseball.classList.remove("selected");
    }
  }
  if (chipSoccer) {
    chipSoccer.textContent = jejuOnly ? "⚽ Kリーグ（済州・SK等）" : "⚽ サッカー";
  }
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
  const { label } = _buildHotelSearchContext();
  return label;
}

/** @returns {{ sido: string, sigungu: string, label: string, query: string }} */
function _buildHotelSearchContext() {
  const sido    = ($("addrSidoUnd")?.value    || "").trim();
  const sigungu = ($("addrSigunguUnd")?.value || "").trim();
  const label   = [sido, sigungu].filter(Boolean).join(" ");
  let query = "";
  if (sigungu && sido) query = `${sido} ${sigungu} 호텔`;
  else if (sigungu) query = `${sigungu} 호텔`;
  else if (sido) query = `${sido} 호텔`;
  return { sido, sigungu, label, query };
}

function _hotelSearchParams(ctx) {
  const params = new URLSearchParams({ all: "1" });
  if (ctx.query) params.set("q", ctx.query);
  if (ctx.sido) params.set("sido", ctx.sido);
  if (ctx.sigungu) params.set("sigungu", ctx.sigungu);
  return params;
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
  const ctx  = _buildHotelSearchContext();
  const q    = ($("hotelManualInput")?.value || "").trim();
  if (!q && !ctx.query) {
    const input = $("hotelManualInput");
    if (input) input.focus();
    return;
  }

  const query = q
    ? (ctx.label ? `${ctx.label} ${q}` : q)
    : ctx.query;
  const area = ctx.label || q;

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
    const manualCtx = { ...ctx, query };
    const res = await fetch(`/api/places/search/?${_hotelSearchParams(manualCtx)}`);
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
    if (btn) { btn.disabled = false; btn.textContent = "検索"; }
  }
}

async function _fetchHotelRecommend() {
  const ctx = _buildHotelSearchContext();
  if (!ctx.query) return;

  const statusEl  = $("hotelSearchStatus");
  const statusTxt = $("hotelStatusText");
  const resultsEl = $("hotelResults");

  if (statusEl) { statusEl.style.display = "flex"; }
  if (statusTxt) { statusTxt.textContent = `${ctx.label}のホテルを検索中…`; }
  if (resultsEl) { resultsEl.style.display = "none"; resultsEl.innerHTML = ""; }

  if ($("hotelListPager")) $("hotelListPager").style.display = "none";
  _allHotels = [];
  _hotelPage = 0;
  _hotelSearchMode = "recommend";

  try {
    const res = await fetch(`/api/places/search/?${_hotelSearchParams(ctx)}`);
    const data = await res.json();
    _allHotels = data.places || [];
    _hotelArea = ctx.label;
    _renderHotelPage(0);
  } catch {
    _allHotels = [];
    _hotelArea = ctx.label;
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
    const strictHint = "選択した地域に合うホテルのみ表示しています。";
    const emptyMsg = _hotelSearchMode === "manual"
      ? `「${escHtml(area)}」の検索結果はありませんでした。${strictHint}キーワードを変えて再検索するか、<a href="/chat/" class="link-inline">AIチャット</a>でご相談ください。`
      : `「${escHtml(area)}」のおすすめホテルが見つかりませんでした。${strictHint}下の検索欄でホテル名を入力してください。`;
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

async function _fetchJusoAddresses(keyword, page = 1) {
  const res = await fetch(
    `/api/address/juso/?keyword=${encodeURIComponent(keyword)}&page=${page}&count=25`
  );
  const data = await res.json();
  return { addresses: data.addresses || [], error: data.error || "", configured: data.configured !== false };
}

function _applyJusoAddress(addr) {
  const road = (addr.road_addr || addr.display_name || "").trim();
  const jibun = (addr.jibun_addr || "").trim();
  if ($("accomDetailManual")) {
    $("accomDetailManual").value = _stripAccomBase(road, _buildAccomBase()) || road;
  }
  if ($("accomAddress")) $("accomAddress").value = road || jibun;
  if (addr.building_name && $("accomName") && !($("accomName").value || "").trim()) {
    $("accomName").value = addr.building_name;
  }
  _storeAccomPlace({
    name: addr.building_name || "",
    address: road || jibun,
    latitude: null,
    longitude: null,
    maps_url: "",
  });
  _syncAccomDisplay();
}

function _renderJusoResults(addresses, { resultsEl, error, configured }) {
  if (!resultsEl) return;
  resultsEl.style.display = "block";

  if (!configured) {
    resultsEl.innerHTML =
      '<p class="accom-search-msg">道路名住所API（JUSO_API_KEY）が未設定です。.env にキーを追加してサーバーを再起動してください。</p>';
    return;
  }
  if (error && !addresses.length) {
    resultsEl.innerHTML =
      `<p class="accom-search-msg">住所検索エラー: ${escHtml(error)}</p>`;
    return;
  }
  if (!addresses.length) {
    resultsEl.innerHTML =
      '<p class="accom-no-result">該当する道路名住所がありません。キーワードを変えるか、詳細住所を直接入力してください。</p>';
    return;
  }

  resultsEl.innerHTML =
    '<p class="accom-search-msg accom-search-msg--hint">行政安全部 道路名住所 API の結果です。行をクリックして選択してください。</p>' +
    addresses
      .map(
        (a, i) => `
    <button type="button" class="accom-result-item accom-result-item--juso" data-idx="${i}">
      <strong>${escHtml(a.display_name || a.road_addr || "住所")}</strong>
      ${a.jibun_addr ? `<span class="accom-result-addr">${escHtml(a.jibun_addr)}</span>` : ""}
      ${a.zip_no ? `<span class="accom-result-zip">〒${escHtml(a.zip_no)}</span>` : ""}
    </button>`
      )
      .join("");

  resultsEl.querySelectorAll(".accom-result-item--juso").forEach((item) => {
    item.addEventListener("click", () => {
      const a = addresses[+item.dataset.idx];
      _applyJusoAddress(a);
      resultsEl.style.display = "none";
    });
  });
}

// ── ACCOMMODATION SEARCH ──────────────────────────────────────────────────
function setupAccomSearch() {
  const btn = $("accomSearchBtn");
  if (!btn) return;

  btn.addEventListener("click", async () => {
    const facility = ($("accomSearchInput")?.value || "").trim();
    const base = _buildAccomBase();
    const resultsEl = $("accomSearchResults");
    if (!facility && !base) {
      if (resultsEl) {
        resultsEl.style.display = "block";
        resultsEl.innerHTML =
          '<p class="accom-search-msg">道・市・区を選んでから検索するか、施設名を入力してください。</p>';
      }
      return;
    }

    btn.disabled = true;
    btn.textContent = "検索中…";
    try {
      if (!facility && base) {
        const { addresses, error, configured } = await _fetchJusoAddresses(base);
        _renderJusoResults(addresses, { resultsEl, error, configured });
        return;
      }
      const query = _accomSearchQuery(facility);
      if (!query) return;
      const places = await _fetchPlaces(query);
      _renderPlacesResults(places, {
        resultsEl,
        mode: "facility",
      });
    } catch {
      if (!facility && base) {
        _renderJusoResults([], { resultsEl, error: "network_error", configured: true });
      } else {
        _renderPlacesResults([], { resultsEl, mode: "facility" });
      }
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
    const detailKw = ($("accomDetailSearchInput")?.value || "").trim();
    const base = _buildAccomBase();
    const query = _accomSearchQuery(detailKw);
    const resultsEl = $("accomDetailSearchResults");
    if (!query) {
      if (resultsEl) {
        resultsEl.style.display = "block";
        resultsEl.innerHTML =
          '<p class="accom-search-msg">道・市・区を選ぶか、詳細キーワードを入力してください。</p>';
      }
      return;
    }

    btn.disabled = true;
    btn.textContent = "検索中…";
    try {
      const { addresses, error, configured } = await _fetchJusoAddresses(query);
      if (addresses.length || !configured) {
        _renderJusoResults(addresses, { resultsEl, error, configured });
        if (addresses.length) return;
      }
      const places = await _fetchPlaces(query);
      _renderPlacesResults(places, { resultsEl, mode: "detail" });
    } catch {
      _renderPlacesResults([], { resultsEl, mode: "detail" });
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
const _PLAN_MAPS_URL_RE = /^https?:\/\/(?:maps\.google\.com|www\.google\.com\/maps|goo\.gl\/maps|maps\.app\.goo\.gl)\/\S+/i;
const _PLAN_MAPS_URL_EXTRACT =
  /https?:\/\/(?:maps\.google\.com|www\.google\.com\/maps|goo\.gl\/maps|maps\.app\.goo\.gl)\/[^\s\]<")]+/gi;
const _PLAN_TICKET_URL_RE = /^https?:\/\/(?:tickets?\.interpark\.com|www\.ticketlink\.co\.kr|www\.ssglanders\.com|www\.giantsclub\.com|ticket\.ncdinos\.com)\/\S+/i;

function _escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function _mapsUrlKey(url) {
  const m = String(url).match(/[?&]cid=(\d+)/);
  return m ? `cid:${m[1]}` : String(url).split("&g_mp=")[0].split("&")[0];
}

function _normalizePlaceName(s) {
  return String(s || "")
    .replace(/[『』「」'"`\u2018\u2019\u201C\u201D]/g, "")
    .replace(/\s+/g, "")
    .toLowerCase();
}

const _JP_ADDR_MARKERS = [
  "〒", "일본", "日本", "japan",
  "도쿄도", "도쿄", "東京",
  "오사카", "大阪", "교토", "京都",
  "신주쿠구", "시부야구", "아키하바라",
];
function _isJpAddress(place) {
  const addr = (place?.address || "").toLowerCase();
  return _JP_ADDR_MARKERS.some((m) => addr.includes(m.toLowerCase()));
}

function _buildPlaceIndexes(apiPlaces) {
  const byUrl = {};
  const byName = {};
  for (const p of apiPlaces || []) {
    const uri = p.google_maps_uri || p.maps_url;
    if (uri) byUrl[_mapsUrlKey(uri)] = p;
    const nk = _normalizePlaceName(p.name);
    if (nk && !byName[nk]) byName[nk] = p;
  }
  return { byUrl, byName, unresolved: {} };
}

/** @deprecated use _buildPlaceIndexes — PlanMapView 호환 */
function _buildPlaceIndex(apiPlaces) {
  return _buildPlaceIndexes(apiPlaces).byUrl;
}

function _extractMapsUrlsFromPlan(text) {
  const found = new Set();
  const re = new RegExp(_PLAN_MAPS_URL_EXTRACT.source, "gi");
  let m;
  while ((m = re.exec(text)) !== null) found.add(m[0]);
  return [...found];
}

function _extractUrlsFromLine(line) {
  const re = new RegExp(_PLAN_MAPS_URL_EXTRACT.source, "gi");
  return [...line.matchAll(re)].map((m) => m[0]);
}

function _isEchoCardLine(t) {
  const s = String(t || "").trim();
  if (!s) return true;
  if (/^[★⭐][\d.]/u.test(s)) return true;
  if (/^\([\d,.\s件건]+?\)\s*$/.test(s)) return true;
  if (/^(営業中|영업\s*중|時間外|営業時間外)/i.test(s)) return true;
  if (/^(地図|経路|지도|통로|ルート|Map|Directions)$/i.test(s)) return true;
  if (/^[¥￥$€]+\s*$/.test(s)) return true;
  if (/^주소\s*[:：]/i.test(s)) return true;
  if (/^住所\s*[:：]/.test(s)) return true;
  if (/^\d+[\d\-.,\s]+(ro|gu|si|do|kyeonggi|seoul)/i.test(s) && s.length < 120) return true;
  return false;
}

function _nameKeysFromLine(line) {
  const keys = [];
  const quoted = [...line.matchAll(/[『「']([^』」']+)[』」']|[「『]([^」』]+)[」』]/g)];
  for (const m of quoted) keys.push(_normalizePlaceName(m[1] || m[2]));
  const bare = line.match(
    /([\u3131-\uD79D]{2,}(?:한우|마을|식당|카페|공원|역|몰|호텔|박물관|시장|맛집|레스토랑|restaurant|cafe|park|station))/i
  );
  if (bare) keys.push(_normalizePlaceName(bare[1]));
  return keys.filter(Boolean);
}

const _PLAN_SLOT_PREFIX_RE =
  /^(?:昼食|午後|午前|夕食|朝食|夜|ランチ|ディナー|朝|昼|食事|점심|저녁|아침|오전|오후|식사)[：:\s]+/u;

function _normalizeQueryLabelForEnrich(label) {
  let t = String(label || "").replace(/\s+/g, " ").trim();
  t = t.replace(/^[-・*①②③④⑤⑥⑦⑧⑨⑩]\s*/, "");
  t = t.replace(_PLAN_SLOT_PREFIX_RE, "");
  t = t.replace(/^【[^】]*】\s*/, "");
  const paren = t.match(/^(.+?)[（(]([^）)]+)[）)]/);
  if (paren) {
    const a = paren[1].trim();
    const b = paren[2].trim();
    t = a.length >= 2 ? a : b;
  }
  t = t.replace(/[（(][^）)]*[）)]/g, "").trim();
  t = t.replace(/\s*본점.*$/g, "").replace(/\s*本店.*$/g, "").trim();
  return t;
}

function _findPlaceByName(indexes, query) {
  const nk = _normalizePlaceName(query);
  if (!nk) return null;
  if (indexes.byName[nk]) return indexes.byName[nk];
  for (const [k, p] of Object.entries(indexes.byName)) {
    if (k.includes(nk) || nk.includes(k)) return p;
  }
  return null;
}

function _queryLabelForUrl(lines, url, lineIdx) {
  const i =
    lineIdx != null
      ? lineIdx
      : lines.findIndex((ln) => ln.includes(url));
  if (i < 0) return "";
  const same = lines[i].trim();
  const prefix = same.split(url)[0].replace(/[:：]\s*$/, "").trim();
  if (prefix && prefix.length >= 2 && prefix.length < 80 && !_isEchoCardLine(prefix)) {
    return prefix.replace(/^[-・*]\s*/, "").trim();
  }
  const suffix = same.split(url)[1]?.replace(/^[:：\s]+/, "").trim() || "";
  if (suffix && suffix.length >= 2 && suffix.length < 80 && !_isEchoCardLine(suffix)) {
    return suffix.replace(/^[-・*]\s*/, "").trim();
  }
  for (let j = i - 1; j >= 0; j--) {
    const t = lines[j].trim();
    if (!t || _isEchoCardLine(t)) continue;
    if (_extractUrlsFromLine(t).length) continue;
    return t
      .replace(/^\[[\d:〜~\-]+\]\s*/, "")
      .replace(/^[-・*]\s*/, "")
      .trim();
  }
  return "";
}

function _mapsOpenOpts() {
  return {
    regions: wizardData.regions || [],
    regionCities: wizardData.regionCities || wizardData.regionCitiesOther || "",
  };
}

function _mapOpenUrl(p) {
  if (window.MapsOpenUrl?.build) {
    return MapsOpenUrl.build(p || {}, _mapsOpenOpts());
  }
  return p?.google_maps_uri || p?.maps_url || "#";
}

function _renderMapsUnresolvedFallback(url, queryLabel) {
  const q = _normalizeQueryLabelForEnrich(queryLabel);
  console.debug?.("Plan place link omitted: unresolved Google Places detail", { url, query: q });
  return "";
}

function _lookupPlace(indexes, url) {
  return indexes.byUrl[_mapsUrlKey(url)] || null;
}

function _placeRenderKey(place) {
  const uri = place?.google_maps_uri || place?.maps_url;
  return uri ? _mapsUrlKey(uri) : _normalizePlaceName(place?.name);
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
  const mapsUri = _mapOpenUrl(p);
  const dirUri = _directionsUrl(p);
  const meta = [rating && `<span class="plan-place-card__rating">${rating}${reviews}</span>`, openBadge, priceLabel]
    .filter(Boolean).join("");
  const thumbLink = mapsUri || dirUri;
  return `<div class="plan-inline-spot"><article class="plan-place-card"><a class="plan-place-card__thumb-link" href="${_escapeHtml(thumbLink)}" target="_blank" rel="noopener">${thumb}</a><div class="plan-place-card__body"><h4 class="plan-place-card__name">${name}</h4>${meta ? `<div class="plan-place-card__meta">${meta}</div>` : ""}${addr}<div class="plan-place-card__actions">${mapsUri ? `<a href="${_escapeHtml(mapsUri)}" target="_blank" rel="noopener" class="plan-place-card__btn">地図</a>` : ""}<a href="${_escapeHtml(dirUri)}" target="_blank" rel="noopener" class="plan-place-card__btn plan-place-card__btn--route">経路</a></div></div></article></div>`;
}

const _PLAN_CLOCK_RE = /\[[\d０-９]{1,2}\s*[:：]\s*[\d０-９]{2}[^\]]*\]/g;
const _PLAN_DAY_HEAD_RE = /^(【\s*)?(\d+)\s*日目|^(【\s*)?最終日|帰国日|最終\s*日|^#{1,3}\s*\d+\s*日目/i;
const _PLAN_SLOT_RE = /^\[(午前|午後|昼食|夕食|夜|朝食|朝|ランチ|ディナー)\]/;
const _PLAN_STEP_RE = /^[①②③④⑤⑥⑦⑧⑨⑩]\s*/;

function _stripPlanClocks(line) {
  return (line || "")
    .replace(_PLAN_CLOCK_RE, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function _isPlanDayHeader(line) {
  const t = (line || "").trim();
  return _PLAN_DAY_HEAD_RE.test(t) || /^Day\s*\d+/i.test(t);
}

function _isPlanSlotLabel(line) {
  return _PLAN_SLOT_RE.test((line || "").trim());
}

function _formatPlanTextLine(line) {
  return _escapeHtml(_stripPlanClocks(line)).replace(/【(.*?)】/g, "<strong>【$1】</strong>");
}

function _tryRenderPlaceCard(indexes, rendered, url) {
  const key = _mapsUrlKey(url);
  if (rendered.has(key)) return false;
  const place = _lookupPlace(indexes, url);
  if (!place) return false;
  const pk = _placeRenderKey(place);
  if (pk && rendered.has(pk)) return false;
  rendered.add(key);
  if (pk) rendered.add(pk);
  return true;
}

function _renderPlanHtml(text, placeIndexes, ticketEventIndex) {
  const lines = text.split(/\r?\n/);
  const out = [];
  const rendered = new Set();
  let timelineOpen = false;

  const closeTimeline = () => {
    if (timelineOpen) {
      out.push("</ol></div>");
      timelineOpen = false;
    }
  };

  const openTimeline = (headingHtml) => {
    closeTimeline();
    out.push('<div class="plan-day-block">');
    if (headingHtml) out.push(headingHtml);
    out.push('<ol class="plan-timeline">');
    timelineOpen = true;
  };

  const pushSlot = (labelHtml) => {
    if (!timelineOpen) openTimeline("");
    out.push(`<li class="plan-timeline-slot">${labelHtml}</li>`);
  };

  const pushStep = (innerHtml) => {
    if (!timelineOpen) openTimeline("");
    out.push(`<li class="plan-timeline-item"><div class="plan-timeline-body">${innerHtml}</div></li>`);
  };

  const emitCard = (place) => _renderInlinePlaceCard(place);

  const ticketIdx = ticketEventIndex || {};
  const LP = window.LinkPreview;

  const _ticketCardsForUrls = (urls) => {
    if (!LP) {
      return urls.map(
        (url) =>
          `<a href="${_escapeHtml(url)}" target="_blank" rel="noopener" class="plan-ticket-link">🎫 公演チケット</a>`
      );
    }
    return urls.map((rawUrl) => {
      const url = LP.normalizeUrl(rawUrl);
      const known = ticketIdx[url] || ticketIdx[url.split("?")[0]];
      if (known) return LP.renderCard(LP.eventToPreview(known, url));
      return LP.renderSkeleton(url);
    });
  };

  const isUnresolvedMapsUrl = (url) => {
    const key = _mapsUrlKey(url);
    return Boolean(placeIndexes.unresolved?.[key] && !_lookupPlace(placeIndexes, url));
  };

  const lineLooksLikeUnresolvedPlaceLabel = (rawLine, nextRawLine) => {
    const current = _normalizePlaceName(
      _normalizeQueryLabelForEnrich(
        String(rawLine || "")
          .replace(/^\[[\d:〜~\-]+\]\s*/, "")
          .replace(/^[-・*]\s*/, "")
          .trim()
      )
    );
    if (!current || current.length < 2) return false;
    for (const url of _extractUrlsFromLine(String(nextRawLine || ""))) {
      if (!isUnresolvedMapsUrl(url)) continue;
      const q = _normalizePlaceName(placeIndexes.unresolved?.[_mapsUrlKey(url)] || "");
      if (q && (current === q || current.includes(q) || q.includes(current))) return true;
    }
    return false;
  };

  const processContentLine = (rawLine) => {
    const line = _stripPlanClocks(rawLine);
    const trimmed = line.trim();
    if (!trimmed || _isEchoCardLine(trimmed)) return;

    const ticketUrls = LP ? LP.extractTicketUrls(line) : [];
    if (ticketUrls.length) {
      const prose = LP ? LP.stripUrlsFromProse(line, ticketUrls) : line;
      const cardParts = _ticketCardsForUrls(ticketUrls);
      if (prose && !_isEchoCardLine(prose)) {
        pushStep(`<p class="plan-line">${_formatPlanTextLine(prose)}</p>${cardParts.join("")}`);
      } else {
        pushStep(cardParts.join(""));
      }
      return;
    }

    if (_PLAN_TICKET_URL_RE.test(trimmed)) {
      const ticketUrl = LP ? LP.normalizeUrl(trimmed.split(/\s/)[0]) : trimmed.split(/\s/)[0];
      pushStep(_ticketCardsForUrls([ticketUrl]).join(""));
      return;
    }

    const urls = _extractUrlsFromLine(line);
    if (urls.length) {
      let prose = line;
      const cardParts = [];
      for (const url of urls) {
        const place = _lookupPlace(placeIndexes, url);
        if (place && _tryRenderPlaceCard(placeIndexes, rendered, url)) {
          cardParts.push(emitCard(place));
        } else if (!rendered.has(_mapsUrlKey(url))) {
          rendered.add(_mapsUrlKey(url));
          cardParts.push(
            _renderMapsUnresolvedFallback(url, placeIndexes.unresolved?.[_mapsUrlKey(url)])
          );
        }
        prose = prose.replace(url, "");
      }
      if (!cardParts.join("").trim() && urls.every(isUnresolvedMapsUrl)) {
        return;
      }
      prose = prose.replace(/^\s*[^:：\n]{1,40}[:：]\s*$/u, "").trim();
      if (prose && !_isEchoCardLine(prose)) {
        pushStep(`<p class="plan-line">${_formatPlanTextLine(prose)}</p>${cardParts.join("")}`);
      } else if (cardParts.length) {
        pushStep(cardParts.join(""));
      }
      return;
    }

    if (_PLAN_MAPS_URL_RE.test(trimmed)) {
      const url = trimmed.split(/\s/)[0];
      if (isUnresolvedMapsUrl(url)) {
        rendered.add(_mapsUrlKey(url));
        return;
      }
      const place = _lookupPlace(placeIndexes, url);
      if (place && _tryRenderPlaceCard(placeIndexes, rendered, url)) {
        pushStep(emitCard(place));
      } else if (!rendered.has(_mapsUrlKey(url))) {
        rendered.add(_mapsUrlKey(url));
        pushStep(
          _renderMapsUnresolvedFallback(url, placeIndexes.unresolved?.[_mapsUrlKey(url)])
        );
      }
      return;
    }

    for (const nk of _nameKeysFromLine(trimmed)) {
      const place = placeIndexes.byName[nk];
      if (!place) continue;
      const uri = place.google_maps_uri || place.maps_url;
      if (uri && _tryRenderPlaceCard(placeIndexes, rendered, uri)) {
        pushStep(emitCard(place));
        return;
      }
    }

    if (_isPlanSlotLabel(trimmed)) {
      const slot = trimmed.match(_PLAN_SLOT_RE)?.[1] || trimmed;
      pushSlot(`<span class="plan-slot-label">${_escapeHtml(slot)}</span>`);
      const rest = trimmed.replace(_PLAN_SLOT_RE, "").trim();
      if (rest) pushStep(`<p class="plan-line">${_formatPlanTextLine(rest)}</p>`);
      return;
    }

    if (_PLAN_STEP_RE.test(trimmed)) {
      pushStep(`<p class="plan-line">${_formatPlanTextLine(trimmed)}</p>`);
      return;
    }

    if (/^【(予算|旅行)/.test(trimmed)) {
      closeTimeline();
      out.push(`<p class="plan-line plan-line--meta">${_formatPlanTextLine(trimmed)}</p>`);
      return;
    }

    pushStep(`<p class="plan-line">${_formatPlanTextLine(trimmed)}</p>`);
  };

  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim();
    if (!trimmed) continue;
    if (lineLooksLikeUnresolvedPlaceLabel(lines[i], lines[i + 1] || "")) {
      continue;
    }

    if (_isPlanDayHeader(trimmed)) {
      openTimeline(`<h3 class="plan-day-heading">${_formatPlanTextLine(trimmed)}</h3>`);
      continue;
    }

    processContentLine(lines[i]);
  }

  closeTimeline();
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

function _placesLinkedInPlan(reply, places) {
  const keys = new Set(_extractMapsUrlsFromPlan(reply).map(_mapsUrlKey));
  if (!keys.size) return [];
  return (places || []).filter((p) => {
    const u = p.google_maps_uri || p.maps_url;
    return u && keys.has(_mapsUrlKey(u));
  });
}

const _FOOD_PREF_KW = {
  grilled_meat: ["삼겹", "갈비", "한우", "고기", "bbq"],
  bossam: ["보쌈", "족발", "돼지국밥", "수육"],
  soup: ["찌개", "국밥", "곰탕", "설렁탕", "감자탕", "삼계탕", "추어탕", "전골"],
  noodles: ["냉면", "국수", "칼국수", "짜장"],
  seafood: ["회", "해물", "생선", "조개", "낙지"],
  chicken: ["치킨", "닭", "chicken", "フライド"],
  snack: ["분식", "떡볶이", "순대", "파전", "빈대떡", "김밥"],
  cafe: ["카페", "커피", "coffee", "베이커리"],
};

function _placeMatchesUserFoodPref(place) {
  const prefs = wizardData.additional?.foodPreferences || [];
  if (!prefs.length) return true;
  const blob = `${place.name || ""} ${place.address || ""}`.toLowerCase();
  // 식당명에 메뉴 키워드가 없는 경우가 많으므로 positive 매칭은 요구하지 않음.
  // 선택하지 않은 카테고리 키워드가 명시적으로 있을 때만 제외.
  const unselected = Object.keys(_FOOD_PREF_KW).filter((k) => !prefs.includes(k));
  return !unselected.some((k) => (_FOOD_PREF_KW[k] || []).some((kw) => blob.includes(kw)));
}

function _renderPlanPlacesRefSection(places, reply) {
  const foodPlaces = (places || []).filter((p) => _placeMatchesUserFoodPref(p));
  if (!foodPlaces.length) return "";
  const linked = _placesLinkedInPlan(reply, foodPlaces);
  const toShow = (linked.length ? linked : foodPlaces).slice(0, 6);
  const cards = toShow.map((p) => _renderInlinePlaceCard(p)).join("");
  const note = linked.length
    ? "※ 本文で引用された店舗。評価・写真は Google データです。"
    : "※ エリア周辺の検索候補。評価・写真は Google データです。";
  return `<div class="plan-refs-section"><h3 class="plan-refs-title">📍 エリア周辺のスポット（Google Places）</h3>
    <div class="plan-place-grid">${cards}</div>
    <p class="plan-refs-note">${note}</p></div>`;
}

// 플랜 텍스트에서 URL 없는 관광지 이름 추출 (괄호형 또는 **bold** 형식)
// 식당/카페 키워드가 포함된 이름은 제외 (food 카드에서 이미 처리)
const _ATTR_PAREN_RE = /([가-힣A-Za-z][가-힣A-Za-z0-9\s]{1,25})\(([가-힣A-Za-z][가-힣A-Za-z0-9\s]{1,25})\)/gu;
const _ATTR_BOLD_RE = /\*{1,2}([가-힣][가-힣A-Za-z0-9\s·]{2,24})\*{1,2}/gu;
const _ATTR_FOOD_SKIP_RE = /식당|레스토랑|맛집|카페|커피|치킨|갈비|국밥|냉면|삼겹|restaurant|cafe/i;
const _MAPS_URL_LINE_RE = /https?:\/\/(?:maps\.google\.com|goo\.gl)/;
// 단어 1~2개짜리 에리어 이름(홍대, 강남 등)은 건너뜀 — 너무 범용적
const _ATTR_AREA_SKIP_RE = /^(홍대|명동|강남|인사동|동대문|이태원|한강|성수|압구정|광장시장|여의도|해운대|부산|제주|대전|전주|경주|속초|강릉)$/;

function _extractUnlinkedAttrNames(text, placeIndexes) {
  const results = new Map(); // name → normalizedKey
  const urlLines = new Set();
  const lines = text.split(/\r?\n/);

  // 먼저 URL이 있는 라인 바로 윗줄(장소 이름 줄)을 마킹 — 해당 줄은 건너뜀
  for (let i = 0; i < lines.length; i++) {
    if (_MAPS_URL_LINE_RE.test(lines[i])) {
      urlLines.add(i);
      if (i > 0) urlLines.add(i - 1); // 직전 이름 줄도 skip
    }
  }

  const tryAdd = (name) => {
    name = name.trim();
    if (name.length < 3 || _ATTR_FOOD_SKIP_RE.test(name) || _ATTR_AREA_SKIP_RE.test(name)) return;
    const nk = _normalizePlaceName(name);
    if (!nk || placeIndexes.byName[nk]) return;
    results.set(name, nk);
  };

  for (let i = 0; i < lines.length; i++) {
    if (urlLines.has(i)) continue;
    const line = lines[i];
    // 괄호형: 더현대서울(더현대서울)
    _ATTR_PAREN_RE.lastIndex = 0;
    let m;
    while ((m = _ATTR_PAREN_RE.exec(line)) !== null) {
      tryAdd(m[2] || m[1]);
    }
    // 볼드형: **더현대서울**, *명동대성당*
    _ATTR_BOLD_RE.lastIndex = 0;
    while ((m = _ATTR_BOLD_RE.exec(line)) !== null) {
      tryAdd(m[1]);
    }
  }
  return [...results.keys()].slice(0, 8);
}

async function _enrichUnlinkedAttractions(names, placeIndexes) {
  if (!names.length) return;
  const regionHint = (wizardData.regions || []).join(" ") + " " +
    (wizardData.regionCities || wizardData.regionCitiesOther || "");
  await Promise.allSettled(names.map(async (name) => {
    try {
      const q = encodeURIComponent(`${name} ${regionHint}`.trim());
      const res = await fetch(`/api/places/search/?q=${q}&limit=1`, {
        credentials: "same-origin",
      });
      if (!res.ok) return;
      const body = await res.json();
      const p = (body.places || [])[0];
      if (!p || !p.maps_url || _isJpAddress(p)) return;
      const nk = _normalizePlaceName(p.name || name);
      if (nk) placeIndexes.byName[nk] = { ...p, google_maps_uri: p.maps_url };
    } catch (_) { /* 무시 */ }
  }));
}

async function _displayPlanOutput(data) {
  const reply = data.reply || "";
  const placeIndexes = _buildPlaceIndexes(data.places || []);
  const lines = reply.split(/\r?\n/);
  const missing = [];
  for (const url of _extractMapsUrlsFromPlan(reply)) {
    if (_lookupPlace(placeIndexes, url)) continue;
    const idx = lines.findIndex((ln) => ln.includes(url));
    const rawQ = _queryLabelForUrl(lines, url, idx >= 0 ? idx : undefined);
    const query = _normalizeQueryLabelForEnrich(rawQ);
    placeIndexes.unresolved[_mapsUrlKey(url)] = query || rawQ;
    const matched = _findPlaceByName(placeIndexes, query);
    if (matched) {
      placeIndexes.byUrl[_mapsUrlKey(url)] = {
        ...matched,
        google_maps_uri: url,
        maps_url: url,
      };
      continue;
    }
    missing.push({ url, query });
  }
  if (missing.length) {
    try {
      const res = await fetch("/api/places/enrich/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
        credentials: "same-origin",
        body: JSON.stringify({
          items: missing,
          language: "ja",
          regions: wizardData.regions || [],
          region_cities: wizardData.regionCities || wizardData.regionCitiesOther || "",
        }),
      });
      const body = await res.json();
      if (res.ok && body.places) {
        for (const [url, p] of Object.entries(body.places)) {
          if (_isJpAddress(p)) continue;
          placeIndexes.byUrl[_mapsUrlKey(url)] = p;
          const nk = _normalizePlaceName(p.name);
          if (nk) placeIndexes.byName[nk] = p;
        }
      }
    } catch (_) { /* プラン本文のみ */ }
  }
  // URL 없는 관광지 이름(괄호형) 2차 Places 검색
  const unlinkedAttrNames = _extractUnlinkedAttrNames(reply, placeIndexes);
  await _enrichUnlinkedAttractions(unlinkedAttrNames, placeIndexes);

  const ticketIdx = window.LinkPreview
    ? LinkPreview.buildEventIndex(data.ticket_platform_events || [])
    : {};
  $("planContent").innerHTML = _renderPlanHtml(reply, placeIndexes, ticketIdx);
  if (window.LinkPreview) {
    await LinkPreview.hydrate($("planContent"), ticketIdx);
  }

  if (window.PlanMapView) {
    const rMap = {
      seoul: "ソウル", gyeonggi: "京畿", incheon: "仁川", gangwon: "江原",
      chungcheong: "忠清", jeolla: "全羅", gyeongsang: "慶尚", jeju: "済州",
    };
    const regions = (wizardData.regions || []).map((r) => rMap[r] || r).filter(Boolean);
    const stay = regions.length ? regions.join("·") : "韓国";
    const nights = wizardData.nights || "";
    const days = wizardData.days || "";
    const title =
      nights && days
        ? `${stay}、${nights}泊${days}日のおすすめルート`
        : `${stay}の旅行ルート`;
    const arrivalIata = wizardData.flight?.arrival_airport || getArrivalAirportIata();
    await window.PlanMapView.render(reply, placeIndexes.byUrl, {
      days: wizardData.days,
      nights: wizardData.nights,
      title,
      subtitle: "Dayタブで日程を切り替え。番号順にルートを表示します。",
      arrivalAirport: arrivalIata,
      regions: wizardData.regions || [],
      regionCities: wizardData.regionCities || wizardData.regionCitiesOther || "",
    });
    setTimeout(() => window.PlanMapView?.refreshMapLayout?.(), 450);
    setTimeout(() => window.PlanMapView?.refreshMapLayout?.(), 1200);
  }

  const places = data.places || [];
  const placesEl = $("planPlacesArea");
  const placesHtml = _renderPlanPlacesRefSection(places, reply);
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

  const ticketEl = $("planTicketArea");
  const ticketHtml = ticketEl ? _renderTicketPlatformCards(data.ticket_platform_events || []) : "";
  if (ticketEl) {
    ticketEl.innerHTML = ticketHtml;
    ticketEl.style.display = ticketHtml ? "block" : "none";
  }

  const sportsEl = $("planSportsArea");
  const sportsHtml = sportsEl ? _renderPlanSportsCards(data.sports_events || []) : "";
  if (sportsEl) {
    sportsEl.innerHTML = sportsHtml;
    sportsEl.style.display = sportsHtml ? "block" : "none";
  }

  const refsEmpty = $("planRefsEmpty");
  if (refsEmpty) {
    const hasRefs = Boolean(placesHtml || vkHtml || eventsHtml || ticketHtml || sportsHtml);
    refsEmpty.style.display = hasRefs ? "none" : "block";
  }

  wizardData.avoid_place_names = _collectPlanPlaceNames(reply, places);
}

const _LEAGUE_LABELS = {
  kbo: "KBO（野球）",
  kbl: "KBL（バスケ）",
  kovo: "KOVO（バレー）",
  kleague: "Kリーグ（サッカー）",
  kleague2: "K2（サッカー）",
};

function _renderTicketPlatformCards(events) {
  if (!events || !events.length || !window.LinkPreview) return "";
  const cards = events.slice(0, 8).map((ev) => {
    const url = LinkPreview.normalizeUrl(ev.ticket_url || "");
    return LinkPreview.renderCard(LinkPreview.eventToPreview(ev, url));
  }).join("");
  return `<div class="plan-refs-section">
    <h3 class="plan-refs-title">🎫 チケット・公演（インターパーク）</h3>
    <div class="plan-ticket-grid">${cards}</div>
  </div>`;
}

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
