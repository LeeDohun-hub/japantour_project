/* Korea Travel Wizard — single-page 7-step flow */

function getCsrfToken() {
  return document.cookie.split(';')
    .map(c => c.trim())
    .find(c => c.startsWith('csrftoken='))
    ?.split('=')[1] ?? '';
}

const TOTAL_STEPS = 6;
let currentStep = 1;
let currentUser = null;
let wizardData = {};
/** @type {{ name?: string, address?: string, english_address?: string, latitude?: number, longitude?: number, maps_url?: string } | null} */
let _selectedAccomPlace = null;

const $ = (id) => document.getElementById(id);
const wizFill    = $("wizFill");
const wizStepsRow = $("wizStepsRow");
const wizNavBar  = $("wizNavBar");
const wizBtnBack = $("wizBtnBack");
const wizBtnNext = $("wizBtnNext");

const STEP_LABELS = ["ログイン","フライト","宿泊","観光","詳細","プラン"];

// ── INIT ──────────────────────────────────────────────────────────────────
async function init() {
  buildStepDots();
  setupStep1();
  setupStep2();
  setupStep3();
  setupChipGroup("regionChips",          true);
  setupRegionCityPicker();
  setupChipGroup("activityChips",        false);
  setupChipGroup("companionChips",       true);
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
  setupChipGroup("vacationChips",        false);
  setupChipGroup("sportsChips",          false);
  setupChipGroup("travelStyleChips",     false);
  setupChipGroup("flightTripTypeChips",  true);
  setupSportsDetailToggle();
  setupVacationDetailToggle();
  setupNavigation();
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
function goToStep(step, options = {}) {
  const skipGenerate = Boolean(options.skipGenerate);
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
    if (!skipGenerate) generatePlan();
  } else {
    wizNavBar.style.display = "flex";
    wizBtnNext.textContent = step === TOTAL_STEPS - 1 ? "プランを生成 ✨" : "次へ";
  }

  if (step === 4) {
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
    if (window.PlanMapView?.clearLocks) window.PlanMapView.clearLocks();
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

  $("btnSavedPlans")?.addEventListener("click", () => openSavedPlansPanel());
  $("ddSavedPlans")?.addEventListener("click", () => openSavedPlansPanel());
  $("btnOpenSavedPlans")?.addEventListener("click", () => openSavedPlansPanel());
  $("btnSavePlan")?.addEventListener("click", () => saveCurrentPlanManually());
  $("btnClearSavedPlans")?.addEventListener("click", clearSavedPlans);
  $("btnCloseSavedPlans")?.addEventListener("click", closeSavedPlansPanel);
  $("savedPlansOverlay")?.addEventListener("click", (e) => {
    if (e.target === $("savedPlansOverlay")) closeSavedPlansPanel();
  });

  $("btnPrintPlan")?.addEventListener("click", () => {
    window.print();
  });

  $("btnSharePlan")?.addEventListener("click", async () => {
    const url = wizardData.planShareUrl || "";
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      _setShareButtonLabel("コピー済み");
      setTimeout(() => _syncPlanShareActions(), 1400);
    } catch {
      window.prompt("共有リンク", url);
    }
  });
}

function _setShareButtonLabel(text) {
  const btn = $("btnSharePlan");
  if (btn) btn.textContent = `🔗 ${text}`;
}

function _syncPlanShareActions() {
  const btn = $("btnSharePlan");
  const saveBtn = $("btnSavePlan");
  const hasUrl = Boolean(wizardData.planShareUrl);
  const hasPlan = Boolean((wizardData.currentPlanText || wizardData.planEditedText || "").trim());
  if (btn) {
    btn.disabled = !hasUrl;
    _setShareButtonLabel(hasUrl ? "共有リンクをコピー" : "保存後に共有リンク");
  }
  if (saveBtn) {
    saveBtn.disabled = !hasPlan || Boolean(wizardData.currentPlanSnapshotId && !wizardData.planDirty);
    saveBtn.textContent = wizardData.currentPlanSnapshotId
      ? (wizardData.planDirty ? "💾 変更を保存" : "💾 保存済み")
      : "💾 プランを保存";
  }
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

    const val = sel.dataset.val;
    if (val === "decided") {
      const sidoEl = $("addrSido");
      const regionErr = $("accomRegionError");
      if (!sidoEl?.value) {
        if (regionErr) regionErr.style.display = "block";
        sidoEl?.scrollIntoView({ behavior: "smooth", block: "center" });
        return false;
      }
      if (regionErr) regionErr.style.display = "none";
    } else if (val === "undecided") {
      const sidoUndEl = $("addrSidoUnd");
      const undRegionErr = $("accomUndecidedRegionError");
      if (!sidoUndEl?.value) {
        if (undRegionErr) undRegionErr.style.display = "block";
        sidoUndEl?.scrollIntoView({ behavior: "smooth", block: "center" });
        return false;
      }
      if (undRegionErr) undRegionErr.style.display = "none";
    }
  }
  if (step === 4) {
    const regions = chips("regionChips");
    const areaErr = $("regionAreaError");
    if (!regions.length) {
      if (areaErr) areaErr.hidden = false;
      $("regionChips")?.scrollIntoView({ behavior: "smooth", block: "center" });
      return false;
    }
    if (areaErr) areaErr.hidden = true;

    const cityErr = $("regionCityError");
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
    case 4: {
      const selectedAreaKeys = chips("regionChips").slice(0, 1);
      wizardData.regionAreaKeys = selectedAreaKeys;
      wizardData.regions = _regionBucketKeys(selectedAreaKeys);
      wizardData.regionCityIds = getSelectedRegionCityIds();
      wizardData.regionCityMeta = getSelectedRegionCityMeta();
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
    case 5:
      wizardData.additional = {
        companion:        chips("companionChips")[0]  || "",
        foodPreferences:  chips("foodPreferenceChips"),
        foodAvoid:        chips("foodAvoidChips"),
        pace:             chips("paceChips")[0]        || "",
        travelStyles:     chips("travelStyleChips"),
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
  const planModeHandler = (e) => {
    const path = (window.location.pathname || "/").replace(/\/$/, "") || "/";
    if (path !== "/") return;
    e.preventDefault();
    goToStep(1);
  };
  $("btnNavPlanMode")?.addEventListener("click", planModeHandler);
  $("ddPlanMode")?.addEventListener("click", planModeHandler);
}

// ── 네비게이션 드롭다운 ──────────────────────────────────────
function openNavDropdown() {
  $("navDropdown")?.classList.add("open");
  $("navProfileBtn")?.setAttribute("aria-expanded", "true");
}
function closeNavDropdown() {
  $("navDropdown")?.classList.remove("open");
  $("navProfileBtn")?.setAttribute("aria-expanded", "false");
}
function toggleNavDropdown() {
  $("navDropdown")?.classList.contains("open") ? closeNavDropdown() : openNavDropdown();
}

// ── 회원탈퇴 모달 ────────────────────────────────────────────
function openDeleteModal() {
  const modal = $("deleteAccountModal");
  if (!modal) return;
  const isOAuth = (currentUser?.username || "").startsWith("google_") ||
                  (currentUser?.username || "").startsWith("line_");
  const pwField = $("deletePasswordField");
  if (pwField) pwField.style.display = isOAuth ? "none" : "block";
  const pwInput = $("deletePasswordInput");
  if (pwInput) pwInput.value = "";
  const errEl = $("deleteAccountError");
  if (errEl) errEl.textContent = "";
  modal.style.display = "flex";
  document.body.style.overflow = "hidden";
}
function closeDeleteModal() {
  const modal = $("deleteAccountModal");
  if (!modal) return;
  modal.style.display = "none";
  document.body.style.overflow = "";
}
async function handleDeleteAccount() {
  const errEl = $("deleteAccountError");
  const btn = $("btnDeleteConfirm");
  const isOAuth = (currentUser?.username || "").startsWith("google_") ||
                  (currentUser?.username || "").startsWith("line_");
  const password = isOAuth ? undefined : $("deletePasswordInput")?.value;
  if (!isOAuth && !password) {
    if (errEl) errEl.textContent = "パスワードを入力してください";
    return;
  }
  if (errEl) errEl.textContent = "";
  btn.disabled = true;
  const origText = btn.textContent;
  btn.textContent = "...";
  try {
    const res = await fetch("/api/auth/delete-account/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
      credentials: "same-origin",
      body: JSON.stringify(isOAuth ? {} : { password }),
    });
    const data = await res.json();
    if (res.ok) {
      closeDeleteModal();
      window.location.reload();
    } else {
      if (errEl) errEl.textContent = data.detail || "退会処理に失敗しました";
    }
  } catch (_) {
    if (errEl) errEl.textContent = "ネットワークエラーが発生しました";
  } finally {
    btn.disabled = false;
    btn.textContent = origText;
  }
}

function setupStep1() {
  setupNavPlanMode();
  $("btnLogout")?.addEventListener("click", handleLogout);
  $("ddLogout")?.addEventListener("click", handleLogout);

  // 드롭다운 토글
  $("navProfileBtn")?.addEventListener("click", (e) => { e.stopPropagation(); toggleNavDropdown(); });
  document.addEventListener("click", (e) => {
    if (!$("navProfileMenu")?.contains(e.target)) closeNavDropdown();
  });

  // 드롭다운 내 버튼
  $("ddDeleteAccount")?.addEventListener("click", () => { closeNavDropdown(); openDeleteModal(); });
  $("btnDeleteAccount")?.addEventListener("click", openDeleteModal);

  // 퇴회 모달
  $("btnDeleteConfirm")?.addEventListener("click", handleDeleteAccount);
  $("btnDeleteCancel")?.addEventListener("click", closeDeleteModal);
  $("deleteAccountModal")?.addEventListener("click", (e) => {
    if (e.target === $("deleteAccountModal")) closeDeleteModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { closeNavDropdown(); closeDeleteModal(); }
  });

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
  // 네비게이션: 드롭다운 표시, 게스트 버튼 숨김
  const navUsername = $("navUsername");
  if (navUsername) navUsername.textContent = name;
  const navAvatar = $("navAvatar");
  if (navAvatar) navAvatar.textContent = name[0].toUpperCase();
  const profileMenu = $("navProfileMenu");
  if (profileMenu) profileMenu.style.display = "flex";
  const guestBtns = $("navGuestBtns");
  if (guestBtns) guestBtns.style.display = "none";
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
  // 네비게이션: 게스트 버튼 복원, 드롭다운 숨김
  closeNavDropdown();
  const profileMenu = $("navProfileMenu");
  if (profileMenu) profileMenu.style.display = "none";
  const guestBtns = $("navGuestBtns");
  if (guestBtns) guestBtns.style.display = "flex";
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
let _flightBundleGen = 0;
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
  _flightFetchTimer = setTimeout(fetchFlightLists, 300);
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
    const retCards = $("returnFlightListCards");
    const retLabel = $("returnFlightListLabel");
    if (retCards) retCards.innerHTML = "";
    if (retLabel) retLabel.textContent = "";
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
  fetchFlightLists();
}

async function _requestFlightData(dep, arr, date) {
  const qs = new URLSearchParams({ dep, arr, ...(date && { date }) });
  const res = await fetch(`/api/flights/?${qs}`);
  const data = await res.json();
  if (!res.ok || data.error) throw new Error(data.error || "照会に失敗しました");
  return data;
}

async function fetchFlightLists() {
  if (!isRoundTrip()) {
    _flightBundleGen++;
    fetchFlightList();
    return;
  }

  const dep = ($("flightFrom")?.value || "").trim();
  const arr = ($("flightTo")?.value || "ICN").trim();
  const departDate = $("flightDepart")?.value || "";
  const retDep = arr;
  const retArr = dep;
  const returnDate = $("flightReturn")?.value || "";

  const section = $("flightListSection");
  const cards = $("flightListCards");
  const label = $("flightListLabel");
  const spinner = $("flightListLoading");
  const pager = $("flightListPager");

  const retSection = $("returnFlightListSection");
  const retCards = $("returnFlightListCards");
  const retLabel = $("returnFlightListLabel");
  const retSpinner = $("returnFlightListLoading");
  const retPager = $("returnFlightListPager");
  if (!section || !cards || !retSection || !retCards) return;

  if (dep && arr && dep === arr) {
    section.style.display = "block";
    retSection.style.display = "block";
    if (label) label.textContent = "出発地と目的地が同じです";
    if (retLabel) retLabel.textContent = "出発地と目的地が同じです";
    cards.innerHTML = `<p class="flight-list-empty">別の空港を選んでください。</p>`;
    retCards.innerHTML = `<p class="flight-list-empty">別の空港を選んでください。</p>`;
    if (pager) pager.style.display = "none";
    if (retPager) retPager.style.display = "none";
    if (spinner) spinner.style.display = "none";
    if (retSpinner) retSpinner.style.display = "none";
    return;
  }

  const gen = ++_flightBundleGen;
  _fetchGen++;
  _returnFetchGen++;
  section.style.display = "block";
  retSection.style.display = "block";
  if (pager) pager.style.display = "none";
  if (retPager) retPager.style.display = "none";
  if (spinner) spinner.style.display = "inline";
  if (retSpinner) retSpinner.style.display = "inline";
  if (label) label.textContent = `${dep} → ${arr}  到着便 照会中…`;
  if (retLabel) retLabel.textContent = `${retDep} → ${retArr} 帰国便 照会中…`;
  cards.innerHTML = "";
  retCards.innerHTML = "";
  _allFlights = [];
  _allReturnFlights = [];
  _flightPage = 0;
  _returnFlightPage = 0;

  const [arrivalResult, returnResult] = await Promise.allSettled([
    _requestFlightData(dep, arr, departDate),
    _requestFlightData(retDep, retArr, returnDate),
  ]);
  if (gen !== _flightBundleGen) return;

  if (arrivalResult.status === "fulfilled") {
    const data = arrivalResult.value;
    _allFlights = _sortFlightsByDepTime(data.flights || []);
    _flightListWarning = data.warning || "";
    const src = data.source === "airport_co_kr" ? " · 韓国空港公社API" : "";
    if (label) label.textContent = `${dep} → ${arr}  ${departDate || "出発日"}  計${_allFlights.length}便${src}`;
    if (_allFlights.length === 0) {
      cards.innerHTML = `<p class="flight-list-empty">該当する便がありません。路線または日付を変更してください。</p>`;
    } else {
      renderFlightPage(0);
      setupPager();
    }
  } else {
    if (label) label.textContent = "照会失敗";
    cards.innerHTML = `<p class="flight-list-empty">${arrivalResult.reason?.message || "照会に失敗しました"}</p>`;
  }

  if (returnResult.status === "fulfilled") {
    const data = returnResult.value;
    _allReturnFlights = _sortFlightsByDepTime(data.flights || []);
    _returnFlightListWarning = data.warning || "";
    const src = data.source === "airport_co_kr" ? " · 韓国空港公社API" : "";
    if (retLabel) retLabel.textContent = `${retDep} → ${retArr}  ${returnDate || "帰国日"}  計${_allReturnFlights.length}便${src}`;
    if (_allReturnFlights.length === 0) {
      retCards.innerHTML = `<p class="flight-list-empty">該当する便がありません。路線または日付を変更してください。</p>`;
    } else {
      renderReturnFlightPage(0);
      setupReturnPager();
    }
  } else {
    if (retLabel) retLabel.textContent = "照会失敗";
    retCards.innerHTML = `<p class="flight-list-empty">${returnResult.reason?.message || "照会に失敗しました"}</p>`;
  }

  if (spinner) spinner.style.display = "none";
  if (retSpinner) retSpinner.style.display = "none";
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


function renderFlightPage(_page) {
  const cards = $("flightListCards");
  if (!cards) return;
  const warn = _flightListWarning
    ? `<p class="flight-list-warn">${escHtml(_flightListWarning)}</p>`
    : "";
  cards.innerHTML = warn + _allFlights.map((f, i) => renderFlightSelectCard(f, i, "arrival")).join("");
  cards.querySelectorAll(".flight-sel-card").forEach((el) => {
    el.addEventListener("click", () => selectFlight(el, _allFlights[+el.dataset.idx]));
  });
  const sel = wizardData.flight?.selected;
  if (sel) {
    cards.querySelectorAll(".flight-sel-card").forEach((el) => {
      if (_allFlights[+el.dataset.idx]?.flight_iata === sel.flight_iata)
        el.classList.add("selected");
    });
  }
  const pager = $("flightListPager");
  if (pager) pager.style.display = "none";
}

function renderReturnFlightPage(_page) {
  const cards = $("returnFlightListCards");
  if (!cards) return;
  const warn = _returnFlightListWarning
    ? `<p class="flight-list-warn">${escHtml(_returnFlightListWarning)}</p>`
    : "";
  cards.innerHTML = warn + _allReturnFlights.map((f, i) => renderFlightSelectCard(f, i, "departure")).join("");
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
  const pager = $("returnFlightListPager");
  if (pager) pager.style.display = "none";
}

function setupPager() {
  const pager = $("flightListPager");
  if (pager) pager.style.display = "none";
}

function setupReturnPager() {
  const pager = $("returnFlightListPager");
  if (pager) pager.style.display = "none";
}

const AIRLINE_NAME_JA = {
  "아시아나항공": "アシアナ航空",
  "대한항공": "大韓航空",
  "진에어": "ジンエアー",
  "에어부산": "エアプサン",
  "에어서울": "エアソウル",
  "이스타항공": "イースター航空",
  "이스타": "イースター航空",
  "부활절 항공": "イースター航空",
  "부활절항공": "イースター航空",
  "이스터항공": "イースター航空",
  "제주항공": "チェジュ航空",
  "티웨이항공": "ティーウェイ航空",
  "티웨이": "ティーウェイ航空",
  "에어로케이항공": "エアロK",
  "에어로케이": "エアロK",
  "에어프레미아": "エアプレミア",
  "에어프레미아항공": "エアプレミア",
  "플라이강원": "フライ江原",
  "에티오피아항공": "エチオピア航空",
  "파라타항공": "パラタ航空",
  "에어인천": "エアインチョン",
  "에어인천국제항공": "エアインチョン",
  "하이에어": "ハイエア",
  "코리아익스프레스에어": "コリアエクスプレスエア",
  "ZIPAIR": "ZIPAIR",
};

const AIRLINE_CODE_NAME_JA = {
  KE: "大韓航空",
  OZ: "アシアナ航空",
  LJ: "ジンエアー",
  BX: "エアプサン",
  RS: "エアソウル",
  ZE: "イースター航空",
  "7C": "チェジュ航空",
  TW: "ティーウェイ航空",
  RF: "エアプレミア",
  YP: "エアインチョン",
  KJ: "エアインチョン",
  "4H": "ハイエア",
  ZG: "ZIPAIR",
  NH: "ANA",
  JL: "JAL",
  MM: "Peach",
  "7G": "StarFlyer",
  GK: "Jetstar Japan",
  BC: "Skymark",
  ET: "エチオピア航空",
  SQ: "シンガポール航空",
  CX: "キャセイパシフィック航空",
  MH: "マレーシア航空",
  TG: "タイ国際航空",
  CI: "チャイナエアライン",
  BR: "エバー航空",
  CA: "中国国際航空",
  MU: "中国東方航空",
  CZ: "中国南方航空",
  OA: "オリンピック航空",
};

function displayAirlineName(name, code = "") {
  const raw = String(name || "").trim();
  const norm = raw.replace(/\s+/g, "");
  return AIRLINE_NAME_JA[raw] || AIRLINE_NAME_JA[norm] || AIRLINE_CODE_NAME_JA[String(code || "").toUpperCase()] || raw;
}

function displayOperatingDays(days) {
  let text = String(days || "").trim();
  if (!text) return "";
  const map = { 월: "月", 화: "火", 수: "水", 목: "木", 금: "金", 토: "土", 일: "日" };
  text = text.replace(/[월화수목금토일]/g, (ch) => map[ch] || ch);
  text = text.replace(/매일|매일운항/g, "毎日");
  return text;
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
  const delay = f.arr_delay > 0 ? `<span class="fsc-delay">+${f.arr_delay}分遅延</span>` : "";
  const days = f.operating_days ? `<span class="fsc-days">${escHtml(displayOperatingDays(f.operating_days))}</span>` : "";
  const aliases = [...new Set((f.codeshare_aliases || []).filter(Boolean))];
  const MAX_ALIASES = 4;
  const aliasShown = aliases.slice(0, MAX_ALIASES);
  const aliasMore = aliases.length > MAX_ALIASES ? ` 他${aliases.length - MAX_ALIASES}便` : "";
  const aliasHtml = aliasShown.length
    ? `<span class="fsc-aliases">+ ${aliasShown.join(" · ")}${aliasMore}</span>`
    : "";
  return `
<div class="flight-sel-card" data-idx="${idx}">
  <div class="fsc-airline">${escHtml(displayAirlineName(f.airline_name, f.airline_iata))} <span class="fsc-num">${escHtml(f.flight_iata)}</span>${aliasHtml}${days}</div>
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
    const showLoc = val === "decided";
    $("accomLocationBlock").style.display   = showLoc ? "block" : "none";
    $("accomDetailShared").style.display    = showLoc ? "block" : "none";
    $("accomDetailUndecided").style.display = val === "undecided" ? "block" : "none";
    if (val !== "undecided") _showHotelManualBlock(false);
    _syncAccomDisplay();
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
      const wasSelected = chip.classList.contains("selected");
      el.querySelectorAll(".chip").forEach((c) => c.classList.remove("selected"));
      if (!wasSelected) chip.classList.add("selected");
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
      wizardData.regionCityIds = [];
      wizardData.regionCityMeta = [];
      wizardData.regionCities = "";
      const otherIn = $("regionCitiesOther");
      if (otherIn) otherIn.value = "";
      syncRegionCityPanels();
      syncSportsChipsForRegion();
    }, 0);
  });

  panels.addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip?.dataset?.val) return;
    chip.classList.toggle("selected");
    if (chip.classList.contains("selected")) {
      const otherIn = $("regionCitiesOther");
      if (otherIn) otherIn.value = "";
    }
    const err = $("regionCityError");
    if (err) err.hidden = true;
  });

  $("regionCitiesOther")?.addEventListener("input", () => {
    if (($("regionCitiesOther").value || "").trim()) {
      panels.querySelectorAll(".chip.selected").forEach((c) => c.classList.remove("selected"));
    }
    const err = $("regionCityError");
    if (err && ($("regionCitiesOther").value || "").trim()) err.hidden = true;
  });

  syncRegionCityPanels();
}

const _REGION_ICONS = {
  seoul: "🏙",
  busan: "🌉",
  daegu: "🏙",
  gyeonggi: "🌳",
  incheon: "✈",
  gwangju: "🌿",
  daejeon: "🚄",
  ulsan: "🌊",
  sejong: "🏛",
  gangwon: "⛰",
  chungbuk: "🌾",
  chungnam: "🌾",
  chungcheong: "🌾",
  jeonbuk: "🍃",
  jeonnam: "🌊",
  jeolla: "🌊",
  gyeongbuk: "🏯",
  gyeongnam: "🏞",
  gyeongsang: "🏯",
  jeju: "🌺",
};

function _regionBucketKeys(areaKeys) {
  const bucketMap = window.REGION_BUCKET_BY_AREA || {};
  return [...new Set((areaKeys || []).map((r) => bucketMap[r] || r).filter(Boolean))];
}

function _regionAreaLabels(areaKeys) {
  const labels = window.REGION_AREA_LABELS || {};
  return (areaKeys || []).map((r) => labels[r] || r).filter(Boolean);
}

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

function _regionCityOtherTokens() {
  const other = ($("regionCitiesOther")?.value || "").trim();
  if (!other) return [];
  return other
    .split(/[,、/・\n|]+/)
    .map((t) => t.trim())
    .filter(Boolean);
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

function getSelectedRegionCityMeta() {
  return getSelectedRegionCityIds()
    .map((key) => {
      const [region, id] = key.split(":");
      const option = (window.REGION_CITY_OPTIONS?.[region] || []).find((c) => c.id === id);
      if (!option) return null;
      return {
        key,
        region,
        id,
        label: option.label,
        query: option.query,
      };
    })
    .filter(Boolean);
}

function buildRegionCitiesString() {
  const parts = [];
  document.querySelectorAll("#regionCityPanels .chip.selected").forEach((chip) => {
    const q = (chip.dataset.query || "").trim();
    if (q) parts.push(q);
  });
  parts.push(..._regionCityOtherTokens());
  return [...new Set(parts)].join("・");
}

function restoreRegionCityStep() {
  const regionAreaKeys = (wizardData.regionAreaKeys || wizardData.regions || []).slice(0, 1);
  wizardData.regionAreaKeys = regionAreaKeys;
  wizardData.regions = _regionBucketKeys(regionAreaKeys);
  document.querySelectorAll("#regionChips .chip").forEach((c) => {
    c.classList.toggle("selected", regionAreaKeys.includes(c.dataset.val));
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

const SIDO_DISPLAY_LABELS = {
  "서울특별시": "Seoul",
  "부산광역시": "Busan",
  "대구광역시": "Daegu",
  "인천광역시": "Incheon",
  "광주광역시": "Gwangju",
  "대전광역시": "Daejeon",
  "울산광역시": "Ulsan",
  "세종특별자치시": "Sejong",
  "경기도": "Gyeonggi-do",
  "강원특별자치도": "Gangwon-do",
  "충청북도": "Chungcheongbuk-do",
  "충청남도": "Chungcheongnam-do",
  "전북특별자치도": "Jeonbuk-do",
  "전라남도": "Jeollanam-do",
  "경상북도": "Gyeongsangbuk-do",
  "경상남도": "Gyeongsangnam-do",
  "제주특별자치도": "Jeju-do",
};

const HANGUL_INITIAL_ROMAN = ["g","kk","n","d","tt","r","m","b","pp","s","ss","","j","jj","ch","k","t","p","h"];
const HANGUL_MEDIAL_ROMAN = ["a","ae","ya","yae","eo","e","yeo","ye","o","wa","wae","oe","yo","u","wo","we","wi","yu","eu","ui","i"];
const HANGUL_FINAL_ROMAN = ["","k","k","ks","n","nj","nh","t","l","lk","lm","lb","ls","lt","lp","lh","m","p","ps","t","t","ng","t","t","k","t","p","t"];

function _hangulToRoman(text) {
  return String(text || "").replace(/[가-힣]/g, (ch) => {
    const code = ch.charCodeAt(0) - 0xac00;
    const jong = code % 28;
    const jung = Math.floor(code / 28) % 21;
    const cho = Math.floor(code / 588);
    return `${HANGUL_INITIAL_ROMAN[cho] || ""}${HANGUL_MEDIAL_ROMAN[jung] || ""}${HANGUL_FINAL_ROMAN[jong] || ""}`;
  });
}

function _titleCaseRoman(text) {
  return String(text || "")
    .split(/(\s|-)/)
    .map((part) => /^[a-z]/.test(part) ? part.charAt(0).toUpperCase() + part.slice(1) : part)
    .join("");
}

function _romanizedAreaLabel(part) {
  const suffixMap = { "시": "-si", "군": "-gun", "구": "-gu" };
  const suffix = suffixMap[part.slice(-1)];
  if (suffix) return `${_titleCaseRoman(_hangulToRoman(part.slice(0, -1)))}${suffix}`;
  return _titleCaseRoman(_hangulToRoman(part));
}

function _areaDisplayLabel(name) {
  if (!name) return "";
  if (SIDO_DISPLAY_LABELS[name]) return SIDO_DISPLAY_LABELS[name];
  return String(name)
    .split(" ")
    .map((part) => {
      return _romanizedAreaLabel(part);
    })
    .join(" ");
}

function _selectedOptionLabel(selectId) {
  const el = $(selectId);
  if (!el || !el.value) return "";
  return el.options[el.selectedIndex]?.textContent || _areaDisplayLabel(el.value);
}

function _buildAccomDisplayBase() {
  return [_selectedOptionLabel("addrSido"), _selectedOptionLabel("addrSigungu")]
    .filter(Boolean)
    .join(" ");
}

// ── PLAN GENERATION ───────────────────────────────────────────────────────
let _planRerollCount = 0;
const _USED_PLAN_PLACE_LIMIT = 80;

const PLAN_MSGS = [
  "情報を整理しています...",
  "旅行データを分析しています...",
  "K-Cultureデータベースを参照中...",
  "プランを生成しています...",
  "仕上げを準備しています...",
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

function _collectUsedPlanPlaces(reply, places) {
  const now = new Date().toISOString();
  const linked = _placesLinkedInPlan(reply, places);
  const byName = new Map();
  for (const p of linked) {
    const name = (p.name || "").trim();
    if (!name) continue;
    const key = _normalizePlaceName(name);
    if (!key || byName.has(key)) continue;
    byName.set(key, {
      name,
      url: p.google_maps_uri || p.maps_url || "",
      category: _isMealPlaceForRefs(p) ? "meal" : _isCafePlaceForRefs(p) ? "cafe" : "place",
      area: p.search_area || p.address || "",
      used_at: now,
    });
  }
  const existing = Array.isArray(wizardData.used_plan_places)
    ? wizardData.used_plan_places
    : [];
  const merged = new Map();
  for (const item of existing) {
    const name = (item?.name || "").trim();
    if (!name) continue;
    const key = _normalizePlaceName(name) || name.toLowerCase();
    if (key) merged.set(key, item);
  }
  for (const [key, item] of byName.entries()) merged.set(key, item);
  return [...merged.values()].slice(-_USED_PLAN_PLACE_LIMIT);
}

function _planMemoryAvoidNames() {
  const names = new Set();
  for (const item of wizardData.used_plan_places || []) {
    if (item?.name) names.add(String(item.name).trim());
  }
  for (const name of wizardData.avoid_place_names || []) {
    if (name) names.add(String(name).trim());
  }
  return [...names].filter(Boolean).slice(-_USED_PLAN_PLACE_LIMIT);
}

function _collectLockedPlanItems() {
  if (!window.PlanMapView?.getLockedItems) return [];
  return window.PlanMapView.getLockedItems()
    .filter((it) => it?.name)
    .slice(0, 20);
}

function _buildPlanAutoDefaults(d) {
  const days = Math.max(1, Number(d.days || 3));
  return {
    additional: {
      companion: "friends",
      pace: days >= 4 ? "relaxed" : "packed",
      foodPreferences: [],
      travelStyles: [],
      auto: true,
    },
  };
}

async function generatePlan(isReroll = false) {
  // transport step removed — set reasonable default so LLM can plan accordingly
  if (!wizardData.transport?.length) {
    wizardData.transport = ["rail", "taxi", "bus"];
  }

  const barEl    = $("planBar");
  const pctEl    = $("planPct");
  const statusEl = $("planStatus");
  $("planTitle").textContent     = _planLoadingTitle(currentUser || {});
  $("planLoadingArea").style.display = "block";
  $("planOutputArea").style.display  = "none";
  $("planErrorArea").style.display   = "none";
  wizardData.planShareUrl = "";
  wizardData.currentPlanText = "";
  wizardData.currentPlanMeta = {};
  wizardData.currentPlanProfilePayload = null;
  wizardData.planDirty = false;
  delete wizardData.planEditedText;
  delete wizardData.currentPlanSnapshotId;
  _syncPlanShareActions();
  if (!isReroll && window.PlanMapView?.clearLocks) window.PlanMapView.clearLocks();
  if (window.PlanMapView?.destroy) window.PlanMapView.destroy();

  let progress = 0;
  const timer = setInterval(() => {
    if      (progress < 45) progress += Math.random() * 5 + 2;
    else if (progress < 78) progress += Math.random() * 2.2 + 0.8;
    else if (progress < 92) progress += 0.55;
    else if (progress < 97) progress += 0.18;
    else if (progress < 99) progress += 0.04;
    progress = Math.min(progress, 99);
    const idx = progress < 25 ? 0 : progress < 50 ? 1 : progress < 75 ? 2 : progress < 94 ? 3 : 4;
    statusEl.textContent = PLAN_MSGS[idx];
    barEl.style.width    = progress + "%";
    pctEl.textContent    = Math.floor(progress) + "%";
  }, 300);

  if (isReroll) {
    _planRerollCount += 1;
    wizardData.plan_reroll = _planRerollCount;
    wizardData.plan_variant_seed = Date.now();
  } else {
    const hasUsedMemory = Array.isArray(wizardData.used_plan_places) && wizardData.used_plan_places.length > 0;
    _planRerollCount = hasUsedMemory ? Math.max(_planRerollCount, 1) : 0;
    wizardData.plan_reroll = hasUsedMemory ? _planRerollCount : 0;
    delete wizardData.plan_variant_seed;
    wizardData.avoid_place_names = _planMemoryAvoidNames();
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
    additional: mergedAdditional,
    plan_auto_defaults: {
      foodPreferences: !userAdditional.foodPreferences?.length,
      details: !userAdditional.companion || !userAdditional.pace || !userAdditional.travelStyles?.length,
    },
    plan_mode: true,
    arrival_airport: wizardData.flight?.arrival_airport || getArrivalAirportIata(),
    departure_airport: wizardData.flight?.departure_airport || getDepartureAirportIata(),
    locked_plan_items: _collectLockedPlanItems(),
    used_plan_places: wizardData.used_plan_places || [],
    avoid_place_names: _planMemoryAvoidNames(),
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
          progress = Math.max(progress, 90);
          barEl.style.width = progress + "%";
          pctEl.textContent = Math.floor(progress) + "%";
          statusEl.textContent = "プランを書いています... (0 文字)";
        } else if (msg.type === "token") {
          fullReply += msg.delta || "";
          charCount += (msg.delta || "").length;
          const tokenProgress = Math.min(99, 90 + Math.floor(charCount / 180));
          if (tokenProgress > progress) {
            progress = tokenProgress;
            barEl.style.width = progress + "%";
            pctEl.textContent = Math.floor(progress) + "%";
          }
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

    if (!fullReply.trim()) {
      throw new Error("プラン本文が空でした。もう一度生成してください。");
    }

    setTimeout(async () => {
      $("planLoadingArea").style.display = "none";
      $("planTitle").textContent = _planResultTitle(currentUser || {});
      $("planOutputArea").style.display = "block";
      _displayPlanOutput({ ...metaData, reply: fullReply }).catch((err) => {
        console.warn("plan display enhancement failed", err);
      });
      wizardData.currentPlanProfilePayload = profilePayload;
      wizardData.currentPlanText = fullReply;
      wizardData.currentPlanMeta = metaData || {};
      wizardData.planDirty = false;
      _syncPlanShareActions();
    }, 180);

  } catch {
    clearInterval(timer);
    $("planLoadingArea").style.display = "none";
    $("planErrorArea").style.display   = "block";
    $("btnRetryPlan").onclick = generatePlan;
  }
}

async function _savePlanSnapshot(profilePayload, reply, metaData) {
  if (!reply?.trim()) return;
  const regions = _regionAreaLabels(profilePayload.regionAreaKeys || profilePayload.regions || []);
  const city = profilePayload.regionCities || profilePayload.regionCitiesOther || "";
  const days = profilePayload.days ? `${profilePayload.days}日` : "";
  const title = [regions[0], city, days].filter(Boolean).join(" · ") || "韓国旅行プラン";
  try {
    const payload = {
      title,
      profile: profilePayload,
      plan_text: reply,
      places: metaData.places || [],
      metadata: {
        visitkorea_stays: metaData.visitkorea_stays || [],
        visitkorea_festivals: metaData.visitkorea_festivals || [],
        visitkorea_attractions: metaData.visitkorea_attractions || [],
        sports_events: metaData.sports_events || [],
        gyeonggi_events: metaData.gyeonggi_events || [],
        ticket_platform_events: metaData.ticket_platform_events || [],
      },
    };
    if (wizardData.currentPlanSnapshotId) {
      payload.snapshot_id = wizardData.currentPlanSnapshotId;
    }
    const res = await fetch("/api/plan-snapshot/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    });
    if (!res.ok) return null;
    return await res.json().catch(() => null);
  } catch (err) {
    console.warn("plan snapshot save failed", err);
    return null;
  }
}

async function saveCurrentPlanManually() {
  const reply = (wizardData.currentPlanText || wizardData.planEditedText || "").trim();
  if (!reply) return;
  const btn = $("btnSavePlan");
  const prevLabel = btn?.textContent || "";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "💾 保存中...";
  }
  const profilePayload = wizardData.currentPlanProfilePayload || wizardData;
  const metaData = wizardData.currentPlanMeta || {};
  const snapshot = await _savePlanSnapshot(profilePayload, reply, metaData);
  if (snapshot?.snapshot_id) {
    wizardData.currentPlanSnapshotId = snapshot.snapshot_id;
    wizardData.planShareUrl = snapshot.share_url || "";
    wizardData.planDirty = false;
    if (btn) btn.textContent = "💾 保存済み";
    _syncPlanShareActions();
    return;
  }
  if (btn) {
    btn.disabled = false;
    btn.textContent = prevLabel || "💾 プランを保存";
  }
  window.alert("プランを保存できませんでした。");
}

function _savedPlanDateLabel(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function openSavedPlansPanel() {
  const overlay = $("savedPlansOverlay");
  if (!overlay) return;
  overlay.hidden = false;
  loadSavedPlans();
}

function closeSavedPlansPanel() {
  const overlay = $("savedPlansOverlay");
  if (overlay) overlay.hidden = true;
}

async function loadSavedPlans() {
  const listEl = $("savedPlansList");
  const detailEl = $("savedPlanDetail");
  const statusEl = $("savedPlansStatus");
  if (listEl) listEl.innerHTML = '<p class="saved-plan-empty">読み込み中...</p>';
  if (detailEl) detailEl.innerHTML = '<p class="saved-plan-empty">左の一覧からプランを選択してください。</p>';
  try {
    const res = await fetch("/api/plan-snapshots/", { credentials: "same-origin" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "load_failed");
    const plans = data.plans || [];
    if (statusEl) {
      statusEl.textContent = data.authenticated
        ? `アカウントに保存されたプラン: ${plans.length}件`
        : `このブラウザセッションの保存プラン: ${plans.length}件`;
    }
    renderSavedPlansList(plans);
  } catch (err) {
    if (statusEl) statusEl.textContent = "保存済みプランを読み込めませんでした。";
    if (listEl) listEl.innerHTML = `<p class="saved-plan-empty">${escHtml(err.message || "読み込みエラー")}</p>`;
  }
}

async function clearSavedPlans() {
  if (!window.confirm("保存済みプランをすべて削除しますか？")) return;
  const statusEl = $("savedPlansStatus");
  const btn = $("btnClearSavedPlans");
  const prevLabel = btn?.textContent || "";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "初期化中...";
  }
  try {
    const res = await fetch("/api/plan-snapshots/", {
      method: "DELETE",
      headers: { "X-CSRFToken": getCsrfToken() },
      credentials: "same-origin",
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "clear_failed");
    delete wizardData.currentPlanSnapshotId;
    wizardData.planShareUrl = "";
    _syncPlanShareActions();
    if (statusEl) statusEl.textContent = `保存済みプランを初期化しました（${data.deleted || 0}件）。`;
    await loadSavedPlans();
  } catch (err) {
    if (statusEl) statusEl.textContent = `初期化できませんでした: ${err.message || "error"}`;
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = prevLabel || "初期化";
    }
  }
}

function renderSavedPlansList(plans) {
  const listEl = $("savedPlansList");
  if (!listEl) return;
  if (!plans.length) {
    listEl.innerHTML = '<p class="saved-plan-empty">保存済みプランはまだありません。</p>';
    return;
  }
  listEl.innerHTML = plans.map((p) => `
    <button type="button" class="saved-plan-item" data-id="${escHtml(String(p.id))}">
      <strong>${escHtml(p.title || "韓国旅行プラン")}</strong>
      <span class="saved-plan-meta">${escHtml(_savedPlanDateLabel(p.updated_at))}</span>
      ${p.excerpt ? `<span class="saved-plan-excerpt">${escHtml(p.excerpt)}</span>` : ""}
    </button>
  `).join("");
  listEl.querySelectorAll(".saved-plan-item").forEach((btn) => {
    btn.addEventListener("click", () => loadSavedPlanDetail(btn.dataset.id));
  });
}

async function loadSavedPlanDetail(id) {
  if (!id) return;
  const detailEl = $("savedPlanDetail");
  if (detailEl) detailEl.innerHTML = '<p class="saved-plan-empty">読み込み中...</p>';
  document.querySelectorAll(".saved-plan-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.id === String(id));
  });
  try {
    const res = await fetch(`/api/plan-snapshot/${encodeURIComponent(id)}/`, { credentials: "same-origin" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "load_failed");
    renderSavedPlanDetail(data.plan);
  } catch (err) {
    if (detailEl) detailEl.innerHTML = `<p class="saved-plan-empty">${escHtml(err.message || "読み込みエラー")}</p>`;
  }
}

function renderSavedPlanDetail(plan) {
  const detailEl = $("savedPlanDetail");
  if (!detailEl || !plan) return;
  const shareUrl = plan.share_url || "";
  detailEl.innerHTML = `
    <div class="saved-plan-detail-head">
      <div>
        <h3>${escHtml(plan.title || "韓国旅行プラン")}</h3>
        <p class="saved-plan-meta">${escHtml(_savedPlanDateLabel(plan.updated_at))}</p>
      </div>
      <div class="saved-plan-detail-actions">
        <button type="button" class="btn btn-sm primary" id="btnLoadSavedPlan">読み込む</button>
        <button type="button" class="btn btn-sm secondary" id="btnCopySavedPlan">リンクコピー</button>
        <button type="button" class="btn btn-sm ghost" id="btnDeleteSavedPlan">削除</button>
      </div>
    </div>
    <div class="saved-plan-detail-text">${escHtml(plan.plan_text || "")}</div>
  `;
  $("btnLoadSavedPlan")?.addEventListener("click", () => loadSavedPlanIntoWizard(plan));
  $("btnCopySavedPlan")?.addEventListener("click", async () => {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
      $("btnCopySavedPlan").textContent = "コピー済み";
    } catch {
      window.prompt("共有リンク", shareUrl);
    }
  });
  $("btnDeleteSavedPlan")?.addEventListener("click", async () => {
    if (!window.confirm("この保存済みプランを削除しますか？")) return;
    await deleteSavedPlan(plan.id);
  });
}

async function loadSavedPlanIntoWizard(plan) {
  if (!plan?.plan_text) return;
  const profile = plan.profile && typeof plan.profile === "object" ? { ...plan.profile } : {};
  const meta = plan.metadata && typeof plan.metadata === "object" ? { ...plan.metadata } : {};
  if (Array.isArray(plan.places) && !Array.isArray(meta.places)) meta.places = plan.places;
  meta.reply = plan.plan_text;

  wizardData = {
    ...profile,
    currentPlanSnapshotId: Number(plan.id) || null,
    planShareUrl: plan.share_url || "",
    currentPlanText: plan.plan_text,
    currentPlanMeta: meta,
    currentPlanProfilePayload: { ...profile },
    planDirty: false,
  };
  delete wizardData.planEditedText;

  closeSavedPlansPanel();
  if (window.PlanMapView?.destroy) window.PlanMapView.destroy();
  goToStep(TOTAL_STEPS, { skipGenerate: true });

  $("planLoadingArea").style.display = "none";
  $("planErrorArea").style.display = "none";
  $("planOutputArea").style.display = "block";
  $("planTitle").textContent = plan.title || _planResultTitle(currentUser || {});

  try {
    await _displayPlanOutput(meta);
  } catch (err) {
    console.warn("saved plan display enhancement failed", err);
    $("planContent").innerHTML = _renderPlanHtml(plan.plan_text, {}, {});
  }
  wizardData.currentPlanSnapshotId = Number(plan.id) || null;
  wizardData.planShareUrl = plan.share_url || "";
  wizardData.planDirty = false;
  _syncPlanShareActions();
}

async function deleteSavedPlan(id) {
  if (!id) return;
  try {
    const res = await fetch(`/api/plan-snapshot/${encodeURIComponent(id)}/`, {
      method: "DELETE",
      headers: { "X-CSRFToken": getCsrfToken() },
      credentials: "same-origin",
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "delete_failed");
    }
    if (wizardData.currentPlanSnapshotId === Number(id)) {
      delete wizardData.currentPlanSnapshotId;
      wizardData.planShareUrl = "";
      _syncPlanShareActions();
    }
    await loadSavedPlans();
  } catch (err) {
    const statusEl = $("savedPlansStatus");
    if (statusEl) statusEl.textContent = `削除できませんでした: ${err.message || "error"}`;
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
  const lockedItems = _collectLockedPlanItems();
  const aMap = { food:"グルメ", shopping:"ショッピング", nightview:"夜景", tradition:"伝統文化",
                 festival:"祭り", hallyu:"韓流・K-pop", drama:"公演", kpop:"K-pop", cafe:"カフェ巡り",
                 nature:"自然", photo:"フォトスポット", sports:"スポーツ観戦", vacation:"バカンス" };
  const vacMap = { poolvilla:"プールヴィラ", camping:"キャンピング", beach:"ビーチ・海水浴場" };
  const tsMap = {
    experience:"体験・アクティビティ", sns_hot:"SNS人気スポット", nature:"自然と一緒に",
    must_see:"有名観光地は必須", healing:"ゆったり癒し", culture:"文化・芸術・歴史",
    local_vibe:"旅行地の雰囲気たっぷり", shop_hard:"ショッピングは本気", food_first:"観光よりグルメ",
  };
  const tMap = { rail:"鉄道・地下鉄（AREX・広域鉄道）", taxi:"タクシー", bus:"空港バス", rental:"レンタカー",
                 arex:"鉄道・地下鉄（AREX）", subway:"鉄道・地下鉄" }; // 하위호환
  const cMap = { solo:"一人旅", couple:"カップル", friends:"友人", family:"ファミリー", parents:"親との旅行" };
  const pMap = { packed:"びっしり", relaxed:"のんびり" };


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
    const typeMap = { decided:"宿泊先決定済み", undecided:"未定（候補あり）", friend:"宿泊先決定済み" };
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
  const _transport = d.transport?.length ? d.transport : _autoTransportForAirport();
  if (_transport.length) {
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
    const tInfo = _transport.map((t) => tTimeMap[t] || t).join(" または ");
    lines.push(`【空港→宿泊先の移動】${tInfo}${accomDest ? ` → ${accomDest}` : ""}`);
    if (d.flight?.selectedReturn) {
      const airportCode = d.flight?.to || "ICN";
      lines.push(
        `【最終日 宿泊先→空港】${accomDest || "宿泊先"} → ${airportCode}（${tInfo}。出発便の2〜3時間前までに到着）`
      );
    }
  }
  const selectedAreaLabels = _regionAreaLabels(d.regionAreaKeys?.length ? d.regionAreaKeys : d.regions);
  if (selectedAreaLabels.length)
    lines.push(`【希望エリア】${selectedAreaLabels.join("・")}`);
  if (d.regionCityIds?.length && window.REGION_CITY_OPTIONS) {
    const cityLabels = [];
    for (const id of d.regionCityIds) {
      const [reg, val] = id.split(":");
      const opt = (window.REGION_CITY_OPTIONS[reg] || []).find((c) => c.id === val);
      if (opt) cityLabels.push(opt.label);
    }
    if (cityLabels.length) {
      lines.push(`【訪問したい市・郡・区】${cityLabels.join("・")}（ユーザーが明示選択した下位地域。広域名から他都市へ勝手に広げず、この市・郡・区を旅行の中心にする。旅行日数と動線に合う範囲で優先）`);
    }
  }
  if (d.regionCities)
    lines.push(`【検索・Places用キーワード】${d.regionCities}`);
  else if (selectedAreaLabels.length)
    lines.push("【市・郡・区の扱い】ユーザーは下位地域を指定していないため、希望エリア内で旅行日数・移動動線・食事/観光候補に合う市・郡・区をAIが選定する。");
  const spMap = { soccer:"サッカー観戦", baseball:"野球観戦", basketball:"バスケ観戦", volleyball:"バレー観戦", sports:"スポーツ観戦（全競技）" };
  const legacyHallyu = (d.additional?.hallyu || []).filter((h) => h !== "traditional");
  const actMerged = [...(d.activities || [])];
  for (const h of legacyHallyu) {
    const v = h === "hallyu" ? "kpop" : h;
    if (v && !actMerged.includes(v)) actMerged.push(v);
  }
  const hasCafePlan = actMerged.includes("cafe");
  const actFiltered = actMerged.filter((a) => a !== "sports");
  const activityParts = actFiltered.map((a) => aMap[a] || a);
  const sportParts = (d.sports || []).map((s) => spMap[s] || s);
  if (activityParts.length) {
    lines.push(`【やりたいこと】${activityParts.join("・")}`);
    const actSet = new Set(actMerged);
    const activityIntents = [
      actSet.has("shopping") && "shopping",
      actSet.has("nightview") && "nightview",
      actSet.has("tradition") && "tradition",
      actSet.has("drama") && "performance",
      actSet.has("nature") && "nature",
      actSet.has("photo") && "photo",
    ].filter(Boolean);
    const timedEventIntents = [
      actSet.has("kpop") && "kpop",
      (actSet.has("sports") || (d.sports || []).length > 0) && "sports",
      actSet.has("vacation") && "vacation",
    ].filter(Boolean);
    const mealDetailLevel = actSet.has("food") ? "high" : "normal";
    lines.push(
      `【内部方針 meal_policy】lunch_required=true / dinner_required=true / gourmet_selected=${actSet.has("food")} / meal_detail_level=${mealDetailLevel} / cafe_as_afternoon_stop=${hasCafePlan}`,
      `【内部方針 activity_intents】${activityIntents.length ? activityIntents.join(", ") : "none"}`,
      `【内部方針 timed_event_intents】${timedEventIntents.length ? timedEventIntents.join(", ") : "none"}`
    );
  }
  if (sportParts.length) {
    lines.push(`【スポーツ観戦】${sportParts.join("・")} — Reference Dataの試合日程をプランに組み込むこと`);
  }
  const vacTypes = d.vacationTypes || [];
  const vacParts = vacTypes.map((v) => vacMap[v] || v);
  if (vacParts.length || actMerged.includes("vacation")) {
    const VACS_REF_ONLY = "【厳守】プールヴィラ・キャンピング場などのバカンス宿泊施設名は、日程本文（Day1〜最終日）の各コマに記載しないこと。各日の日程には「プールヴィラでリゾート体験」「해변에서 휴식」等の概要のみ記述すること。【必須出力】全日程終了後に「## バカンス宿泊候補」という独立したセクションを絶対に作成すること。参照データ（宿泊候補リスト）がある場合はその施設を使う。参照データが空またはない場合でも、AIが確実に知っている該当エリアの実在する宿泊施設（プールヴィラ・ペンション・キャンプ場・해수욕장인근숙소）を5件以上リストアップすること（架空名・想像名は禁止）。形式: 種別見出し＋番号付きリスト（例: **풀빌라** \\n1. 〇〇펜션 | 住所 \\n**캠핑장** \\n1. 〇〇글램핑 | 住所）。このセクションを省略・スキップすることは絶対禁止。";
    lines.push(`【バカンス】${vacParts.length ? vacParts.join("・") : "バカンス"} — バカンス気分を意識した日程にすること。${VACS_REF_ONLY}`);
  }

  const add = promptAdditional;
  if (add) {
    const parts = [];
    if (add.companion)              parts.push(cMap[add.companion]||add.companion);
    if (add.pace)                   parts.push(pMap[add.pace]||add.pace);
    const prefMap = {
      grilled_meat: "焼肉・サムギョプサル", bossam: "ポッサム・チョッパル・豚クッパ",
      soup: "スープ・チゲ・クッパ", noodles: "麺料理",
      seafood: "海鮮・刺身", chicken: "韓国チキン",
      snack: "粉食・軽食", cafe: "カフェ・スイーツ",
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
      "【到着日】1日目は入国・移動・チェックイン・休息を優先。到着・チェックインが遅い場合は観光・食事を出さない。到着が早く夕食時間が物理的に取れる場合のみ、宿泊近郊の夕食1件まで可。希望エリア観光は2日目以降に配置（宿泊先の市区だけで観光エリアを決めない）。",
      "【宿泊先と観光エリアの距離】宿泊先の市区と希望エリアが異なる場合は、2日目冒頭に片道移動時間の目安を1行で明記し、その日の観光地は同一方面にまとめる。毎日同じ遠方エリアへ往復する日程は禁止。移動負担が大きい場合は、観光地数を減らすか宿泊地変更を提案する。",
      "【遠方移動日の地図】2日目に宿泊先から遠方観光地へ移動する場合、2日目の最初のブロックは必ず「宿泊先→目的地エリアの主要駅/最初の観光地」への移動にし、本文にも経路を明記する。地図ルート上でも宿泊先を出発点として扱える構成にする。",
      "【遠方移動日の食事】宿泊先から遠方観光エリアへ移動する日も、到着後の昼食1件（具体的な店名＋地図URL）と夕食1件（具体的な店名＋地図URL）を必ず含める。「移動に充てる」「到着後は休憩」だけで食事を省略することを禁止する。",
      "【帰還日の構成】遠方エリアから宿泊先へ戻る日は、午前〜昼食までは目的地エリア内で具体スポット1件＋具体昼食1件を入れ、午後に宿泊先へ戻る。帰還日を「移動」「休息」「周辺で食事」だけで終わらせない。",
      "【場所重複禁止】同一の観光スポット・食事店を複数の日に重複させない。Reference Dataの候補数が不足する場合は、候補リスト外の実在する周辺スポットを補完してよい（創作・架空名は禁止）。候補不足を理由に「スポットなし」「リスト外のため省略」とだけ書いて日程を空欄にすることを禁止する。【URL必須】リスト外スポット・食事店を使用する場合も必ず次行に地図URLを書くこと。Reference DataにURLがない場合は「https://map.naver.com/v5/search/장소명」形式（韓国語名をURLエンコード）で生成すること。URLなしで場所名だけ書くことは禁止。",
      "【遠方観光地の扱い】宿泊先と希望エリアが遠い場合（例: ソウル/仁川/京畿の宿泊先から釜山・光州・江原・済州など）は、毎日宿泊先から日帰り往復させない。2日目に遠方エリアへ移動した後は、その地域に滞在している前提で連続日程を組む。3日目以降に「元の宿泊先から遠方へ出発」と書くことは禁止。出国前日に元の宿泊先または出国空港圏へ戻る移動ブロックを1回だけ入れる。最終日は元の宿泊先/空港圏から出国する。"
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
  if (lockedItems.length) {
    lines.push(
      "【固定スポット — 最優先】ユーザーが固定した以下の場所は必ず同じ日程内・同じ時間帯に残す。前回スポットの除外対象にしない。固定スポット以外だけ差し替えてよい。",
      ...lockedItems.map((it, idx) => {
        const daySlot = `Day ${it.day || "?"}${it.slot ? ` [${it.slot}]` : ""}`;
        const parts = [`${idx + 1}. ${daySlot}`, it.name];
        if (it.category) parts.push(`種別:${it.category}`);
        if (it.address) parts.push(`住所:${it.address}`);
        if (it.url) parts.push(`URL:${it.url}`);
        if (it.note) parts.push(`メモ:${it.note}`);
        return parts.join(" / ");
      })
    );
  }
  lines.push(
    "\n地図アプリへの検索依頼は禁止。",
    "【言語】本文は必ず日本語。韓国語の説明文（■1일째、한식점で 等）は禁止。店名の韓国語表記のみ可。",
    "【表示形式】時刻レンジ（例:[10:00〜11:00]）は書かない。各日は「1日目」「2日目」見出し＋「①②③」または「午前」「昼食」「午後」「夕食」。",
    "【日程密度】観光可能な旅行日は、観光/体験2〜3件＋昼食1件＋夕食1件を基本上限にする。食事は昼食・夕食の2回だけ。車移動でも同一市内という理由だけで観光地・イベント・食事を詰め込みすぎない。イベント/スポーツ観戦日は観光を1〜2件に減らす。",
    "【夜スロット絶対禁止】[夜]スロットには飲食店・カフェ・バー・屋台・食事場所を一切置かない。[夜]は夜景・散歩・公園・文化エリア・宿泊休憩のみ。夕食は[夕食]スロットで済ませる。夕食後の追加飲食は禁止。",
    "【カード表示用ノイズ禁止】本文に「外観写真」「評価」「営業中」「住所」「地図」「経路」「지도」「통로」「この日の動線上の候補」「予算の目安」を場所名の直前直後に書かない。場所名の直後はReference Dataの地図URL（map.naver.com）だけを書く。",
    "【食事 — 厳守】朝食は入れない。観光可能な旅行日の食事は昼食1件・夕食1件の2回だけ。到着が遅い入国日・出国が早い最終日は食事ブロックを書かない。食事は昼食・夕食スロット以外で絶対に使わない。「近郊で食事」「店名は記載しない」「한식店」「現地のレストラン」「別の韓国料理店」「コンビニ」「軽食」「間食」「候補が足りない/全部終わった」「(식사 후보 리스트에 해당하는 가게가 없습니다)」は絶対禁止。【通常】Reference Dataの「食事候補」リストの店名＋次行にその地図URL（map.naver.com）を書く。候補が足りない場合は同一エリアまたは近接エリアの検証済み候補から選ぶ。帰還日・宿泊エリア候補は帰還後の夕食だけ使用可。【例外：食事候補ゼロ件】Reference Dataの「食事候補」が全エリア合計0件の場合のみ、AIが確実に知っているその都市の実在飲食店を使用可。店名は韓国語正式表記、地図URLは「https://map.naver.com/v5/search/店名（URL-encode）」形式。架空・想像の店名は引き続き禁止。",
    "【観光】「観光スポット候補」リストの施設名＋URLのみが基本。候補不足時は実在スポット補完可（架空禁止）。「〇〇周辺を散策」「〇〇 일대/주변 산책」「近くを歩く」「ショッピングや散策」だけの抽象予定は禁止。散策でも必ず具体施設名・公園名・通り名・モール名を書く。【URL絶対必須】全ての観光スポット・散策地点は必ず名称の次行に地図URL（map.naver.com）を書くこと。Reference Dataにある場合はそのURL、ない場合は「https://map.naver.com/v5/search/한국어장소명」形式で生成。URLなしで場所名だけ書くことは絶対禁止。",
    "【スポーツ】Sports Schedule Resultsの試合またはオフシーズン案内をそのまま記載。ジム・ストリートへの置き換え禁止。",
    "営業時間・料金・チケットは必要な場合だけ文末で一言。本文に「時間外の可能性」「営業時間外かもしれません」は書かない。",
    "【朝の扱い】午前に観光地・公園・展望台・体験施設を入れるのは可。ただし朝食・朝ごはん・朝カフェ・ブランチ・食堂・レストラン・カフェは入れない。朝の飲食店訪問は禁止。食事店は昼食と夕食だけ。"
  );
  lines.push(
    "【食事込みの1日構成 — 絶対】観光可能な旅行日は必ずこの順番で作る: 午前=観光/体験1件（飲食店不可） → 昼食=実在店名+地図URL → 午後=観光/体験1〜2件 → 夕食=昼食と別の実在店名+地図URL → 夜=宿泊先へ戻る、または夜景/軽い散策1件。入国が遅い日・出国が早い日はこの食事構成を使わず、移動・休息だけにする。",
    "【昼食直後の飲食店禁止 — 最重要】昼食を入れたら、その次の予定（午後ブロック、②③などの番号付き次項目、昼食直後の行）に食堂・レストラン・カフェ・デザート・軽食店・市場グルメを絶対に置かない。昼食の次は必ず観光スポット候補の施設、体験、自然、買い物、移動、または休憩にする。その後ならカフェ巡り希望時に限り、カフェ候補の具体店名＋地図URLを1件入れてよい。",
    hasCafePlan
      ? "【カフェ巡り — 位置情報UI必須】「午後: カフェ休憩」「カフェタイム」「周辺カフェで休憩」だけのテキストは禁止。必ずReference Dataの「カフェ候補」から店名を1つ選び、直後の行に地図URL（map.naver.com）を書く。これによりカフェも場所カード/UIとして表示される。"
      : "【カフェ巡り未選択】カフェ・喫茶店・커피・coffee・dessert・bakery・カフェ候補の店名/URLを、午前・午後・夜・昼食・夕食のどこにも出さない。",
    "【飲食店連続禁止】昼食と夕食の間には必ず非飲食の観光/体験/自然/買い物/移動/休憩を1件以上挟む。飲食店・カフェ・デザート・屋台・市場グルメを2件以上連続させない。カフェ候補は昼食/夕食とは別の午後スポット扱いで、午前・夜には置かない。",
    "【夕方・夜の具体スポット】夕食後または夜ブロックは、候補に夜景・川沿い散策・市場・公園・文化通りなど夜に向く具体スポットがあり、利用可能と判断できる場合だけ、場所名＋地図URLで推薦する。「ロッテワールドタワー周辺を散策」のような周辺散策文だけで終わらせず、必ず具体地点を出す。",
    "【夜の抽象文禁止】候補があるのに『宿泊先で休息』『静かな夜を満喫』『宿泊先周辺のレストランやカフェで軽食・休息』『宿泊施設または民泊で宿泊・休息』だけで済ませない。使える候補がない場合だけ、理由を説明せず宿泊先で休息にする。",
    "観光可能な日に昼食・夕食を抜くのは不完全。ただし入国が遅い日・出国が早い日は食事を出さない。『近郊で食事』『現地で探す』『店名は記載しない』『候補が足りない』『候補が全部終わった』『コンビニ』『軽食』『間食』は禁止。候補が少ない日は観光数を減らしてでも昼食と夕食だけを入れる。",
    "夜景や宿泊先復帰は夕食の後に置く。食事前に宿泊先へ戻ってその日の夕食を省略しない。"
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
<div class="ti-links-note">地方移動・都市鉄道リンク</div>
<a href="https://english1.visitkorea.or.kr/common_intl/subway.kto?lang=1" target="_blank" rel="noopener">韓国観光公社 地下鉄ルート検索</a>
<div class="ti-links-note">※ 一部の交通公社公式サイトは日本から開けない場合があります。</div>`;

const KORAIL_REGIONAL_NOTE = `<div class="ti-card"><strong>🚄 KTX・KORAIL（地方都市への長距離移動）</strong>
仁川空港から釜山・大邱・大田・光州など地方都市へはKTX（高速鉄道）・ITX-セマウルが便利です。<br>
仁川空港駅または光明（こうみょう）駅からKTXに乗車することで、地方都市へ直行できます（例: ソウル↔釜山 約2時間20分）。<br>
<strong>⚠️ ご注意:</strong> KORAIL公式サイト（korail.com）は日本国内から安全保障上の制限でアクセスできない場合があります。<br>
出発前に<strong>韓国内の代理購入サービス</strong>（Klook・KTXラボ等）やKTX駅窓口でのご購入をお勧めします。</div>`;

const TRANSPORT_RAIL_BY_AIRPORT = {
  ICN: `<div class="ti-card"><strong>🚆 鉄道・地下鉄（AREX・広域鉄道）</strong>
仁川空港↔ソウル駅 AREX直通約43分 / 一般約51分。乗換で広域鉄道・地下鉄（1・9号線等）<br>
<a href="https://www.arex.or.kr/" target="_blank" rel="noopener">▶ AREX 公式</a> ·
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
<a href="https://www.kakaomobility.com/service-kakaot" target="_blank" rel="noopener">▶ KakaoTaxi</a></div>`,
  bus: TRANSPORT_BUS_BY_AIRPORT.ICN,
  rental: `<div class="ti-card"><strong>🚗 レンタカー</strong>
<a href="https://www.lotterentacar.net/" target="_blank" rel="noopener">▶ 各社レンタカー</a></div>`,
  arex: TRANSPORT_RAIL_BY_AIRPORT.ICN,
};

const _KORAIL_REGION_SIDOS = ["부산광역시", "울산광역시", "경상남도", "대구광역시", "대전광역시", "광주광역시"];

function _accomIsKorailRegion() {
  const addr = (wizardData.accommodation?.address || "") + " " + (wizardData.accommodation?.region || "");
  return _KORAIL_REGION_SIDOS.some((sido) => addr.includes(sido));
}

// 교통 단계 제거 후 도착 공항 기반 자동 교통수단 추론
// wizardData.transport가 미설정일 때 프롬프트 생성·지도 렌더에서 사용
function _autoTransportForAirport() {
  const iata = getArrivalAirportIata();
  const isKorail = _accomIsKorailRegion();
  const defaults = {
    ICN: isKorail ? ["rail", "bus"] : ["arex", "bus"],
    GMP: ["subway", "bus"],
    PUS: ["bus"],
    CJU: ["bus"],
  };
  return defaults[iata] || ["bus"];
}

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

  const isKorailRegion = _accomIsKorailRegion();
  const showRail = iata === "ICN" || iata === "GMP" || isKorailRegion;

  if (chipRail) {
    chipRail.style.display = showRail ? "" : "none";
    if (isKorailRegion && iata === "ICN") {
      chipRail.textContent = "🚆 KTX・鉄道・地下鉄（AREX・広域鉄道）";
    } else if (iata === "GMP") {
      chipRail.textContent = "🚆 地下鉄・広域鉄道";
    } else if (isKorailRegion) {
      chipRail.textContent = "🚆 鉄道・地方鉄道";
    } else {
      chipRail.textContent = "🚆 鉄道・地下鉄（AREX・広域鉄道）";
    }
    if (!showRail && chipRail.classList.contains("selected")) chipRail.classList.remove("selected");
    TRANSPORT_INFO.rail = TRANSPORT_RAIL_BY_AIRPORT[iata] || TRANSPORT_RAIL_BY_AIRPORT.ICN;
    if (isKorailRegion) {
      TRANSPORT_INFO.rail = (TRANSPORT_RAIL_BY_AIRPORT[iata] || TRANSPORT_RAIL_BY_AIRPORT.ICN) + KORAIL_REGIONAL_NOTE;
    }
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
  renderTransportInfoPanel();
}

function renderTransportInfoPanel() {
  const panel = $("transportInfoPanel");
  if (!panel) return;
  const selected = chips("transportChips");
  if (!selected.length) {
    panel.style.display = "none";
    panel.innerHTML = "";
    return;
  }
  panel.innerHTML = selected.map((t) => TRANSPORT_INFO[t] || "").join("");
  panel.style.display = "block";
}

function setupTransportInfo() {
  const el = $("transportChips");
  const panel = $("transportInfoPanel");
  if (!el || !panel) return;

  syncTransportChipsForAirport();

  el.addEventListener("click", () => {
    requestAnimationFrame(() => {
      const selected = chips("transportChips");
      const err = $("transportError");
      if (selected.length && err) err.hidden = true;
      renderTransportInfoPanel();
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
    opt.value = d;
    opt.textContent = _areaDisplayLabel(d);
    sido.appendChild(opt);
  });

  sido.addEventListener("change", () => {
    const districts = ADDR_DATA[sido.value] || [];
    sigungu.innerHTML = `<option value="">-- 選択 --</option>` +
      districts.map((d) => `<option value="${_escapeAttr(d)}">${escHtml(_areaDisplayLabel(d))}</option>`).join("");
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
  const label   = [_selectedOptionLabel("addrSidoUnd"), _selectedOptionLabel("addrSigunguUnd")]
    .filter(Boolean)
    .join(" ");
  let query = "";
  if (sigungu && sido) query = `${sido} ${sigungu} 호텔`;
  else if (sigungu) query = `${sigungu} 호텔`;
  else if (sido) query = `${sido} 호텔`;
  return { sido, sigungu, label, query };
}

function _hotelSearchParams(ctx, mode = "recommend") {
  const params = new URLSearchParams({ all: "1", type: "hotel", mode });
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

  // 영문 label 대신 한글 sido/sigungu로 쿼리 구성 (Naver 검색 정확도)
  const koreaPrefix = [ctx.sido, ctx.sigungu].filter(Boolean).join(" ").trim();
  const query = q
    ? (koreaPrefix ? `${koreaPrefix} ${q}` : q)
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
    const res = await fetch(`/api/places/search/?${_hotelSearchParams(manualCtx, "search")}`);
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
      const photoSrc = p.photo_name
        ? `/api/photo/?name=${encodeURIComponent(p.photo_name)}`
        : (p.photo_url || "");
      const photoHtml = photoSrc
        ? `<img class="hotel-photo" src="${escHtml(photoSrc)}" loading="lazy" alt="${escHtml(p.name)}" onerror="this.style.display='none'" />`
        : "";
      const ratingHtml = p.rating
        ? `<span class="hotel-rating">⭐ ${Number(p.rating).toFixed(1)}<span class="hotel-rating-cnt">${p.user_rating_count ? ` (${p.user_rating_count.toLocaleString()}件)` : ""}</span></span>`
        : "";
      const priceHtml = p.price_level
        ? `<span class="hotel-price">${escHtml(p.price_level)}</span>`
        : "";
      const mapsHtml = p.maps_url
        ? `<a href="${escHtml(p.maps_url)}" target="_blank" rel="noopener" class="hotel-maps-link">📍 地図で見る</a>`
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
    btn.addEventListener("click", () => {
      el.querySelectorAll(".hotel-select-btn").forEach((b) => {
        b.classList.remove("selected");
        b.textContent = "このホテルを選択";
      });
      btn.classList.add("selected");
      btn.textContent = "✅ 選択中";
      _selectHotelFromList(_allHotels[+btn.dataset.idx]);
    });
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
    opt.value = d;
    opt.textContent = _areaDisplayLabel(d);
    sido.appendChild(opt);
  });

  sido.addEventListener("change", () => {
    const districts = ADDR_DATA[sido.value] || [];
    sigungu.innerHTML = `<option value="">-- 選択 --</option>` +
      districts.map((d) => `<option value="${_escapeAttr(d)}">${escHtml(_areaDisplayLabel(d))}</option>`).join("");
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
  const displayBase = _buildAccomDisplayBase();
  const displayDetail = _stripAccomBase(full, _buildAccomBase());
  const displayFull = [displayBase || _buildAccomBase(), displayDetail].filter(Boolean).join(" ");
  if ($("accomAddress")) $("accomAddress").value = full;

  const name   = ($("accomName")?.value || "").trim();
  const infoEl = $("accomSelectedInfo");
  if (!infoEl) return;

  if (name || full) {
    infoEl.style.display = "flex";
    const nameEl = $("accomSelectedName");
    const addrEl = $("accomSelectedAddr");
    if (nameEl) nameEl.textContent = name || "選択済み住所";
    if (addrEl) {
      const selectedAddr = (_selectedAccomPlace?.address || "").trim();
      const selectedEng = (_selectedAccomPlace?.english_address || "").trim();
      const sameSelectedAddress = selectedAddr && full && (
        full === selectedAddr || full.includes(selectedAddr) || selectedAddr.includes(full)
      );
      if (selectedEng && sameSelectedAddress && selectedEng !== selectedAddr) {
        addrEl.innerHTML =
          `<span class="accom-sel-address-main">${escHtml(selectedEng)}</span>` +
          `<span class="accom-sel-address-sub">韓国語住所: ${escHtml(selectedAddr)}</span>`;
      } else {
        addrEl.textContent = displayFull;
      }
    }
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
  const english = (addr.english_road_addr || "").trim();
  const jibun = (addr.jibun_addr || "").trim();
  const selectedAddress = road || jibun || english;
  if ($("accomDetailManual")) {
    $("accomDetailManual").value = _stripAccomBase(selectedAddress, _buildAccomBase()) || selectedAddress;
  }
  if ($("accomAddress")) $("accomAddress").value = selectedAddress;
  if (addr.building_name && $("accomName") && !($("accomName").value || "").trim()) {
    $("accomName").value = addr.building_name;
  }
  _storeAccomPlace({
    name: addr.building_name || "",
    address: selectedAddress,
    english_address: english,
    jibun_address: jibun,
    english_jibun_address: addr.english_jibun_addr || "",
    zip_no: addr.zip_no || "",
    source: addr.source || "juso",
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
    '<p class="accom-search-msg accom-search-msg--hint">行政安全部 道路名住所 API の結果です。英語住所と韓国語住所を確認して選択してください。</p>' +
    addresses
      .map((a, i) => {
        const primary = a.english_road_addr || a.display_name || a.road_addr || "住所";
        const korean = a.road_addr && a.road_addr !== primary
          ? `<span class="accom-result-addr accom-result-addr--ko">韓国語住所: ${escHtml(a.road_addr)}</span>`
          : "";
        const jibun = a.jibun_addr
          ? `<span class="accom-result-addr">地番住所: ${escHtml(a.jibun_addr)}</span>`
          : "";
        const engJibun = a.english_jibun_addr
          ? `<span class="accom-result-addr">英語地番住所: ${escHtml(a.english_jibun_addr)}</span>`
          : "";
        return `
    <button type="button" class="accom-result-item accom-result-item--juso" data-idx="${i}">
      <strong>${escHtml(primary)}</strong>
      ${korean}
      ${jibun}
      ${engJibun}
      ${a.zip_no ? `<span class="accom-result-zip">〒${escHtml(a.zip_no)}</span>` : ""}
    </button>`;
      })
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
          '<p class="accom-search-msg">広域エリア・宿泊エリアを選んでから検索するか、施設名を入力してください。</p>';
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
          '<p class="accom-search-msg">広域エリア・宿泊エリアを選ぶか、詳細キーワードを入力してください。</p>';
      }
      return;
    }

    btn.disabled = true;
    btn.textContent = "検索中…";
    try {
      const { addresses, error, configured } = await _fetchJusoAddresses(query);
      _renderJusoResults(addresses, { resultsEl, error, configured });
    } catch {
      _renderJusoResults([], { resultsEl, error: "network_error", configured: true });
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
    english_address: p.english_address || "",
    jibun_address: p.jibun_address || "",
    english_jibun_address: p.english_jibun_address || "",
    zip_no: p.zip_no || "",
    source: p.source || "",
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
const _PLAN_MAPS_URL_RE = /^https?:\/\/(?:maps\.google\.com|www\.google\.com\/maps|goo\.gl\/maps|maps\.app\.goo\.gl|map\.naver\.com)\/\S+/i;
const _PLAN_MAPS_URL_EXTRACT =
  /https?:\/\/(?:maps\.google\.com|www\.google\.com\/maps|goo\.gl\/maps|maps\.app\.goo\.gl|map\.naver\.com)\/[^\s\]<")]+/gi;
const _PLAN_TICKET_URL_RE = /^https?:\/\/(?:www\.kopis\.or\.kr|tickets?\.interpark\.com|ticket\.interpark\.com|www\.ticket\.interpark\.com|www\.ticketlink\.co\.kr|ticketlink\.co\.kr|ticket\.yes24\.com|ticket\.melon\.com|www\.ticketmelon\.co\.kr|ticket\.ssg\.com|www\.ssglanders\.com|www\.giantsclub\.com|ticket\.ncdinos\.com)\/\S+/i;

function _escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function _mapsUrlKey(url) {
  const s = String(url || "");
  const naverPlaceM = /map\.naver\.com/i.test(s) && s.match(/\/place\/(\d{6,})/i);
  if (naverPlaceM) return `naver-place:${naverPlaceM[1]}`;
  if (/map\.naver\.com/i.test(s)) {
    const base = s.split("?")[0].replace(/\/$/, "");
    try { return decodeURIComponent(base); } catch { return base; }
  }
  const m = s.match(/[?&]cid=(\d+)/);
  return m ? `cid:${m[1]}` : s.split("&g_mp=")[0].split("&")[0];
}

function _normalizePlaceName(s) {
  return String(s || "")
    .replace(/[『』「」'"`\u2018\u2019\u201C\u201D]/g, "")
    .replace(/\s+/g, "")
    .toLowerCase();
}

function _cleanPlanPlaceLabel(label) {
  let t = String(label || "").replace(/\s+/g, " ").trim();
  t = t.replace(/^[\uFE0E\uFE0F\u200D\s]+/u, "");
  t = t.replace(/^(?:[-・*①②③④⑤⑥⑦⑧⑨⑩]|\p{Extended_Pictographic}|[\uFFFD�])+[\uFE0E\uFE0F\u200D\s]*/u, "");
  t = t.replace(/^(?:여기기ㅇ|여기|요기|저기|추천|おすすめ|固定)\s+/i, "");
  t = t.replace(/^[^\p{L}\p{N}가-힣ぁ-んァ-ヶ一-龯]+/u, "");
  return t.trim();
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

const _REGION_PLACE_ADDRESS_MARKERS = {
  seoul: ["seoul", "서울"],
  busan: ["busan", "부산"],
  daegu: ["daegu", "대구"],
  incheon: ["incheon", "인천"],
  gwangju: ["gwangju", "광주광역", "광주"],
  daejeon: ["daejeon", "대전"],
  ulsan: ["ulsan", "울산"],
  sejong: ["sejong", "세종"],
  gyeonggi: ["gyeonggi", "경기", "고양", "수원", "성남", "용인", "부천", "안산", "안양"],
  gangwon: ["gangwon", "강원", "강릉", "속초", "양양", "춘천", "원주", "평창", "정선", "동해", "삼척", "고성"],
  chungbuk: ["chungcheongbuk", "chungbuk", "충청북", "충북", "청주", "충주", "제천", "단양"],
  chungnam: ["chungcheongnam", "chungnam", "충청남", "충남", "천안", "아산", "공주", "부여", "보령", "태안"],
  jeonbuk: ["jeonbuk", "jeollabuk", "전북", "전라북", "전주", "군산", "익산", "남원", "고창"],
  jeonnam: ["jeonnam", "jeollanam", "전남", "전라남", "여수", "목포", "순천", "담양", "보성", "해남"],
  gyeongbuk: ["gyeongbuk", "gyeongsangbuk", "경북", "경상북", "경주", "포항", "안동", "영주"],
  gyeongnam: ["gyeongnam", "gyeongsangnam", "경남", "경상남", "창원", "통영", "거제", "진주", "남해"],
  jeju: ["jeju", "제주", "서귀포"],
};

function _placeMatchesSelectedArea(place) {
  const selected = wizardData.regionAreaKeys?.length ? wizardData.regionAreaKeys : [];
  if (!selected.length) return true;
  const addr = `${place?.address || ""} ${place?.name || ""}`.toLowerCase();
  return selected.some((key) =>
    (_REGION_PLACE_ADDRESS_MARKERS[key] || []).some((m) => addr.includes(m.toLowerCase()))
  );
}

function _buildPlaceIndexes(apiPlaces) {
  const byUrl = {};
  const byName = {};
  for (const p of apiPlaces || []) {
    const uri = p.google_maps_uri || p.maps_url;
    if (uri) byUrl[_mapsUrlKey(uri)] = p;
    const names = [p.name, p.name_ja].filter(Boolean);
    if (p.name && p.name_ja) names.push(`${p.name_ja} (${p.name})`);
    for (const name of names) {
      const nk = _normalizePlaceName(name);
      if (nk && !byName[nk]) byName[nk] = p;
    }
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

const _BAD_PLAN_PLACE_QUERY_RE =
  /^(?:곳|장소|지점|스팟|후보|카페|식당|맛집|관광|명소|주변|근처|일대|에리어|エリア|スポット|場所|カフェ|レストラン|観光|名所)$/i;

function _isBadPlanPlaceQuery(value) {
  const q = String(value || "").replace(/\s+/g, " ").trim();
  if (!q) return true;
  const compact = q.replace(/\s+/g, "");
  if (compact.length < 2) return true;
  if (_BAD_PLAN_PLACE_QUERY_RE.test(compact)) return true;
  if (/(?:지역|에리어|エリア|근처|주변|일대|近く|周辺).{0,12}(?:음식점|식당|맛집|한국음식|요리|レストラン|食堂|食事)/i.test(q)) return true;
  if (/(?:현지|当地|地元|한국\s*같은|韓国らしい).{0,12}(?:맛|요리|음식|グルメ|料理|食事)/i.test(q)) return true;
  if (/(?:공원|公園|타워|タワー|관광지|観光地).{0,10}(?:근처|주변|近く|周辺).{0,12}(?:음식점|식당|맛집|食事|レストラン)/i.test(q)) return true;
  if (/^\d+\s*곳$/.test(q)) return true;
  if (/^(?:具体|구체|현지|人気|有名|추천|人気の)?\s*(?:곳|장소|スポット|場所)$/i.test(q)) return true;
  if (/실제.{0,20}(?:요리점|음식점|식당|레스토랑)/i.test(q)) return true;
  if (/을\s*사용$/.test(q)) return true;
  // 시간대 슬롯 레이블 단독(오전/오후/점심/저녁 등)은 장소명 아님
  if (/^(?:午前|午後|昼食|夕食|朝食|夜|ランチ|ディナー|朝|昼|食事|점심|저녁|아침|오전|오후|식사|모닝|브런치)$/.test(compact)) return true;
  // 장소명은 50자 이내 — 그 이상은 설명문으로 간주
  if (q.length > 50) return true;
  // 문장 종결어미·조사로 끝나면 설명문 (보고, 마쳐, 하며, 합니다, ます, てください 등)
  if (/(?:하고|하며|하여|하기|마쳐|마치고|보고|보며|즐기고|즐기며|합니다|합시다|ます|ました|ください|て下さい|とおり|ながら)[.。，,]?\s*$/.test(q)) return true;
  return false;
}

function _autoPlaceQueriesFromLine(line) {
  const s = String(line || "").toLowerCase();
  const out = [];
  const add = (q) => {
    if (q && !out.includes(q)) out.push(q);
  };

  if (/명동|明洞|myeongdong/i.test(s)) {
    add("명동거리");
    add("명동성당");
    if (/카페|cafe|coffee/i.test(s)) add("명동 카페");
  }
  if (/경복궁|gyeongbok|景福宮?/i.test(s)) add("경복궁");
  if (/북촌|bukchon|北村/i.test(s)) add("북촌한옥마을");
  if (/익선|익성|ikseon/i.test(s)) add("익선동 한옥거리");
  if (/인사동|insadong|仁寺洞/i.test(s)) {
    add("쌈지길");
    add("인사동길");
  }
  if (/삼청동|samcheong|三清洞/i.test(s)) add("삼청동 카페거리");
  if (/광화문|gwanghwamun|光化門/i.test(s)) add("광화문광장");
  if (/청계천|cheonggye|清渓川/i.test(s)) add("청계천");
  if (/남산|namsan|南山/i.test(s)) add("남산공원");
  if (/동대문|dongdaemun|東大門/i.test(s)) add("동대문디자인플라자");
  if (/창덕궁|changdeok|昌徳宮/i.test(s)) add("창덕궁");
  if (/덕수궁|deoksugung|徳寿宮/i.test(s)) add("덕수궁 돌담길");
  if (/홍대|弘大|홍익|hongdae/i.test(s)) add("홍대입구역");
  if (/이태원|itaewon|梨泰院/i.test(s)) add("이태원");
  if (/강남|gangnam|江南/i.test(s)) add("강남역");
  if (/쌈지길|サムジキル/i.test(s)) add("쌈지길");
  if (/전통.*(잡화|쇼핑|공예)|雑貨|工芸/.test(s)) {
    add("쌈지길");
    add("인사동 전통문화의 거리");
  }
  if (/카페\s*타임|카페에서|cafe time/.test(s)) {
    if (/명동|myeongdong/.test(s)) add("명동 카페");
    else if (/북촌|삼청|경복/.test(s)) add("북촌 한옥카페");
    else if (/대구|daegu/.test(s)) add("대구 카페");
    else if (/김광석/.test(s)) add("김광석거리 카페");
    else if (/간송|미술관|museum|gallery/.test(s)) add("대구간송미술관 카페");
    else add("인사동 한옥카페");
  }
  if (/카페\s*순회|カフェ巡り|cafe hopping/.test(s)) {
    if (/대구|daegu/.test(s)) {
      add("김광석거리 카페");
      add("대구 동성로 카페");
    } else {
      add("한옥카페");
    }
  }
  return out;
}

function _nameKeysFromLine(line) {
  const keys = [];
  const quoted = [...line.matchAll(/[『「']([^』」']+)[』」']|[「『]([^」』]+)[」』]/g)];
  for (const m of quoted) keys.push(_normalizePlaceName(m[1] || m[2]));
  // 일본어명（한국어명） 형식 — 괄호 안 한국어도 직접 조회
  const parenKo = line.match(/[（(]([가-힣][가-힣\s·]{0,30})[）)]/);
  if (parenKo) keys.push(_normalizePlaceName(parenKo[1]));
  for (const q of _autoPlaceQueriesFromLine(line)) keys.push(_normalizePlaceName(q));
  const bare = line.match(    /([ㄱ-힝]{2,}(?:한우|마을|궁|거리|길|식당|카페|공원|역|몰|호텔|박물관|시장|맛집|레스토랑|정원|사|절|성당|성|산성|왕릉|능|고택|서원|향교|유적|기념관|전시관|전망대|온천|폭포|계곡|해변|해수욕장|수목원|식물원|항구|등대|미술관|테마파크|워터파크|놀이공원|경기장|수족관|restaurant|cafe|park|station))/i );
  if (bare) keys.push(_normalizePlaceName(bare[1]));
  return keys.filter(Boolean);
}

function _candidatePlaceNamesFromPlanLine(line) {
  let t = _normalizeQueryLabelForEnrich(line);
  t = _cleanPlanPlaceLabel(t);
  if (!t || _isEchoCardLine(t) || _isBadPlanPlaceQuery(t)) return [];
  t = t.replace(/^[①②③④⑤⑥⑦⑧⑨⑩]\s*/, "");
  if (
    /(?:入国|出国|チェックイン|ホテル|宿泊|空港|移動|休息|休憩|到着|出発|手荷物|審査|税関|AREX|乗換|下車|徒歩|タクシー|リムジン|コンビニ|軽食|間食|편의점|간식)/i.test(t)
  ) return [];
  const parts = t.split(/[、。・]|→|⇒/).map((p) => p.trim()).filter(Boolean);
  const out = [];
  for (const part of parts.length ? parts : [t]) {
    let name = part.replace(/^(?:昼食|午後|午前|夕食|朝食|夜|ランチ|ディナー|朝|昼|食事)[:：\s]*/, "").trim();
    name = name.replace(/^(?:観光|散策|訪問|見学|ショッピング|カフェ|食事)\s*[:：-]?\s*/, "").trim();
    name = name.replace(/\s+(?:周辺|近く|エリア).*$/u, "").trim();
    if (name.length >= 2 && name.length <= 36 && !_ATTR_FOOD_SKIP_RE.test(name) && !_isBadPlanPlaceQuery(name)) out.push(name);
  }
  return [...new Set(out)].slice(0, 3);
}

const _PLAN_SLOT_PREFIX_RE =
  /^(?:昼食|午後|午前|夕食|朝食|夜|ランチ|ディナー|朝|昼|食事|점심|저녁|아침|오전|오후|식사)[：:\s]+/u;

function _normalizeQueryLabelForEnrich(label) {
  let t = String(label || "").replace(/\s+/g, " ").trim();
  t = t.replace(/^예\)\s*/u, "").replace(/^例\)\s*/, "");  // "예) 장소명" placeholder strip
  t = _cleanPlanPlaceLabel(t);
  t = t.replace(_PLAN_SLOT_PREFIX_RE, "");
  t = t.replace(/^【[^】]*】\s*/, "");
  t = _cleanPlanPlaceLabel(t);
  const paren = t.match(/^(.+?)[（(]([^）)]+)[）)]/);
  if (paren) {
    const a = paren[1].trim();
    const b = paren[2].trim();
    t = a.length >= 2 ? a : b;
  }
  t = t.replace(/[（(][^）)]*[）)]/g, "").trim();
  t = t.replace(/\s*본점.*$/g, "").replace(/\s*本店.*$/g, "").trim();
  return _isBadPlanPlaceQuery(t) ? "" : t;
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
  const prefix = _cleanPlanPlaceLabel(same.split(url)[0].replace(/[:：]\s*$/, "").trim());
  if (prefix && prefix.length >= 2 && prefix.length < 80 && !_isEchoCardLine(prefix)) {
    return prefix;
  }
  const suffix = _cleanPlanPlaceLabel(same.split(url)[1]?.replace(/^[:：\s]+/, "").trim() || "");
  if (suffix && suffix.length >= 2 && suffix.length < 80 && !_isEchoCardLine(suffix)) {
    return suffix;
  }
  for (let j = i - 1; j >= 0; j--) {
    const t = _cleanPlanPlaceLabel(lines[j].trim());
    if (!t || _isEchoCardLine(t)) continue;
    if (_extractUrlsFromLine(t).length) continue;
    // 슬롯 레이블(오전/오후/점심/저녁 등)은 장소명이 아님 — 건너뜀
    if (_isPlanSlotLabel(lines[j].trim())) continue;
    const candidate = t.replace(/^\[[\d:〜~\-]+\]\s*/, "").replace(/^[-・*]\s*/, "").trim();
    // 36자 초과는 설명문(散文)으로 간주 — 장소명으로 사용하지 않고 스캔 종료
    if (candidate.length > 36) break;
    if (_isBadPlanPlaceQuery(candidate)) break;
    return candidate;
  }
  return "";
}

function _mapsOpenOpts() {
  return {
    regions: wizardData.regions || [],
    regionCities: wizardData.regionCities || wizardData.regionCitiesOther || "",
    regionCityIds: wizardData.regionCityIds || [],
    regionCityMeta: wizardData.regionCityMeta || [],
  };
}

function _mapOpenUrl(p) {
  if (window.MapsOpenUrl?.build) {
    return MapsOpenUrl.build(p || {}, _mapsOpenOpts());
  }
  return p?.google_maps_uri || p?.maps_url || "#";
}

function _hasJapanesePlaceText(text) {
  const s = String(text || "");
  return /[\u3040-\u30ff]/.test(s) || (/[\u3400-\u9fff]/.test(s) && !/[가-힣]/.test(s));
}

// 한글+한자 혼재 이름(예: "명동교자 本店")에서 CJK 한자 제거 -> Naver 검색 호환성
function _stripMixedCJK(str) {
  const s = String(str || "");
  if (/[가-힣]/.test(s) && /[㐀-鿿]/.test(s)) {
    return s.replace(/[㐀-鿿]+s*/g, "").replace(/s{2,}/g, " ").trim();
  }
  return s;
}

function _extractKoreanPlaceName(text) {
  const m = String(text || "").match(/[（(]([가-힣][가-힣\s·]{0,40})[)）]/);
  return m ? m[1].trim() : "";
}

function _koreanPlaceName(p) {
  const name = String(p?.name || "").trim();
  const fromName = _extractKoreanPlaceName(name);
  if (fromName) return fromName;
  const fromJa = _extractKoreanPlaceName(p?.name_ja || "");
  if (fromJa) return fromJa;
  if (/[가-힣]/.test(name) && !_hasJapanesePlaceText(name)) return _stripMixedCJK(name);
  return "";
}

function _displayPlaceName(p) {
  const ko = _koreanPlaceName(p);
  const ja = String(p?.name_ja || "").trim();
  const raw = String(p?.name || p?.address || "").trim();
  // name_ja가 실제 일본어(히라가나·카타카나·한자)를 포함할 때만 "ja (ko)" 형식 사용
  // 한국어가 name_ja에 들어온 경우(삼지킬, 키자니아 서울 등) raw를 그대로 반환
  if (ja && ko && _hasJapanesePlaceText(ja) && ja.replace(/\s+/g, "") !== ko.replace(/\s+/g, "")) {
    // ja가 이미 "(ko)" 포함 시 중복 방지
    const koEsc = ko.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (new RegExp(`[（(]${koEsc}[)）]`).test(ja)) return ja;
    return `${ja} (${ko})`;
  }
  if (raw && _hasJapanesePlaceText(raw)) {
    const fromRaw = _extractKoreanPlaceName(raw);
    if (fromRaw) return raw;
  }
  return raw || ja || ko;
}

function _naverSearchTermFromUrl(url) {
  try {
    const m = String(url).match(/\/search\/([^?#]+)/i);
    return m ? decodeURIComponent(m[1].replace(/\+/g, " ")).trim() : "";
  } catch { return ""; }
}

function _renderMapsUnresolvedFallback(url, queryLabel, slotKind = "") {
  const proseTerm = _normalizeQueryLabelForEnrich(queryLabel);
  const urlTerm = _naverSearchTermFromUrl(url);
  const urlHasKorean = /[가-힣]/.test(urlTerm || "");
  const proseIsJapanese = _hasJapanesePlaceText(proseTerm || queryLabel || "");
  // URL path의 한국어를 prose 일본어보다 우선 (검색·카드명 모두)
  const searchTerm = (urlHasKorean && proseIsJapanese) ? urlTerm : (proseTerm || urlTerm || "");
  // 일본어 한자로만 된 검색어 → 한국어 대응어로 변환 (Naver 검색 품질 향상)
  let q = searchTerm;
  if (q && _hasJapanesePlaceText(q) && !/[가-힣]/.test(q)) {
    const koAlt = _autoPlaceQueriesFromLine(q)[0];
    if (koAlt) q = koAlt;
  }
  if (_isBadPlanPlaceQuery(q)) return "";
  // 식사 슬롯 미해결 URL: 한국어 장소명이 확실하면 앵커 카드 표시 (완전 공백 방지)
  if (slotKind === "meal") {
    if (q && /[가-힣]/.test(q)) return _renderAnchorPlaceCard(q, (urlHasKorean && proseIsJapanese) ? (proseTerm || "") : "");
    return "";
  }
  console.debug?.("Plan place link omitted: unresolved place detail", { url, query: q });
  if (q && /map\.naver\.com[^\s]*\/search\//i.test(url)) {
    const isCoordQuery = /^-?[\d.]+,-?[\d.]+$/.test(q.trim());
    if (isCoordQuery) {
      // 좌표 URL: prose label이 한국어면 카드, 아니면 링크
      const displayLabel = proseTerm || urlTerm;
      if (displayLabel && !_hasJapanesePlaceText(displayLabel) && !/^-?[\d.]+,-?[\d.]+$/.test(displayLabel.trim())) {
        return _renderAnchorPlaceCard(displayLabel);
      }
      return `<a class="plan-place-search-link" href="${_escapeHtml(url)}" target="_blank" rel="noopener">🔍 ${_escapeHtml(displayLabel || q)}</a>`;
    }
    // 일본어 prose + 한국어 URL → "JA (KO)" 표시, 한국어로 지도 검색
    const displayJa = (urlHasKorean && proseIsJapanese) ? (proseTerm || "") : "";
    return _renderAnchorPlaceCard(q, displayJa);
  }
  // /p/place/ URL이지만 itinerary_places에 없는 경우:
  // route map은 URL만 있으면 스톱을 만들기 때문에, 텍스트플랜도 anchor card로 일치시킴
  if (q && /[가-힣]/.test(q)) return _renderAnchorPlaceCard(q, proseIsJapanese ? (proseTerm || "") : "");
  return "";
}

function _lookupPlace(indexes, url) {
  return indexes.byUrl[_mapsUrlKey(url)] || null;
}

function _placeRenderKey(place) {
  const uri = place?.google_maps_uri || place?.maps_url;
  return uri ? _mapsUrlKey(uri) : _normalizePlaceName(place?.name);
}

function _naverCoordsFromPlaceOrUrl(p) {
  const lat = p?.latitude != null && p.latitude !== "" ? Number(p.latitude) : null;
  const lng = p?.longitude != null && p.longitude !== "" ? Number(p.longitude) : null;
  if (lat != null && lng != null && !Number.isNaN(lat) && !Number.isNaN(lng)) {
    return { lat, lng };
  }
  const raw = String(p?.maps_url || p?.google_maps_uri || "");
  const m = raw.match(/[?&]c=([0-9.]+),([0-9.]+),/);
  if (!m) return null;
  const parsedLng = Number(m[1]);
  const parsedLat = Number(m[2]);
  if (Number.isNaN(parsedLat) || Number.isNaN(parsedLng)) return null;
  return { lat: parsedLat, lng: parsedLng };
}

function _directionsUrl(p) {
  const label = _koreanPlaceName(p) || String(p?.name || p?.address || "").trim();
  const coords = _naverCoordsFromPlaceOrUrl(p);
  if (coords) {
    const q = encodeURIComponent(label || `${coords.lat},${coords.lng}`);
    return `https://map.naver.com/p/directions/-/${coords.lng},${coords.lat},${q},PLACE_POI/-/transit?c=${coords.lng},${coords.lat},15,0,0,0,dh`;
  }
  if (/map\.naver\.com|naver\.me/i.test(p?.maps_url || p?.google_maps_uri || "")) {
    const q = encodeURIComponent(`${label} 경로`.trim());
    return q ? `https://map.naver.com/p/search/${q}` : (p.maps_url || p.google_maps_uri || "#");
  }
  const q = encodeURIComponent(`${label} 경로`.trim());
  return q ? `https://map.naver.com/p/search/${q}` : "#";
}

function _placeGuideLine(p) {
  const blob = `${p?.name || ""} ${p?.address || ""} ${p?.category || ""} ${p?.primary_type || ""}`.toLowerCase();
  const has = (...needles) => needles.some((n) => blob.includes(String(n).toLowerCase()));
  // Exclude food places from being labelled as cafe (e.g. "전포카페거리" in address)
  const isFoodByName = _CAFE_EXCLUDE_NAME_RE.test((p?.name || "").toLowerCase());

  if (has("insadong", "인사동")) {
    if (has("ssamziegil", "쌈지길")) return "伝統雑貨・工芸品・小さなギャラリーをまとめて見やすいスポット。";
    return "韓国らしい工芸品、茶屋、路地写真を楽しみやすい伝統散策エリア。";
  }
  if (has("myeongdong", "명동")) {
    if (has("cathedral", "성당")) return "明洞散策の目印になる歴史的建築で、写真休憩にも使いやすい場所。";
    return "コスメ、屋台、K-pop系ショップを歩いて回りやすいソウル定番の買い物エリア。";
  }
  if (has("gyeongbok", "경복궁")) return "王宮建築と守門将交代式が見どころの、ソウル歴史観光の中心スポット。";
  if (has("bukchon", "북촌")) return "韓屋の路地景観が残るフォトスポット。歩きやすい靴がおすすめ。";
  if (has("ikseon", "익선")) return "韓屋を改装したカフェや雑貨店が集まる、写真向きの路地エリア。";
  if (has("cheonggye", "청계천")) return "都心の水辺散歩に向いた休憩スポット。夜の散策にも使いやすいです。";
  if (has("gwanghwamun", "광화문")) return "広場、宮殿、博物館をつなげやすいソウル中心部のランドマーク。";
  if (has("찜닭", "jjimdak", "チムタク")) return "甘辛い醤油だれの鶏煮込みが名物。辛さは注文時に調整すると安心。";
  if (has("chicken", "치킨", "후라이드", "fried")) return "韓国式フライドチキン向き。ビールや軽い夜食にも合わせやすい店。";
  if (!isFoodByName && has("cafe", "coffee", "커피", "카페")) return "散策の途中で休憩しやすいカフェ候補。写真と営業時間を見て選ぶと安心。";
  if (has("restaurant", "식당", "맛집")) return "この日の動線上で食事を取りやすい候補。代表メニューは現地メニューで確認。";
  if (has("museum", "gallery", "미술관", "박물관")) return "展示鑑賞向きのスポット。所要時間は展示内容に合わせて調整しやすいです。";
  if (has("market", "시장", "mall", "store", "거리", "길")) return "買い物と写真を組み合わせやすい立ち寄りスポット。";
  return "この日の移動ルートに組み込みやすい、参照データで確認済みのスポット。";
}

const _CATEGORY_LABEL_JA = {
  tourist_attraction: "観光スポット",
  point_of_interest: "観光スポット",
  park: "公園",
  museum: "博物館",
  art_gallery: "美術館",
  aquarium: "水族館",
  amusement_park: "遊園地",
  zoo: "動物園",
  natural_feature: "自然",
  stadium: "スタジアム",
  campground: "キャンプ場",
  lodging: "ホテル",
  restaurant: "レストラン",
  cafe: "カフェ",
  shopping_mall: "ショッピングモール",
  store: "ショップ",
  establishment: "施設",
};

function _translateCategoryJa(cat) {
  const key = String(cat || "").trim().toLowerCase().replace(/\s+/g, "_");
  return _CATEGORY_LABEL_JA[key] || cat;
}

function _renderInlinePlaceCard(p, proseHint) {
  const name = _escapeHtml(_displayPlaceName(p));
  // Guide: category badge + description extracted from LLM prose
  // Fallback so every card always shows at least a category label
  const _defaultCat = _isMealPlaceForRefs(p) ? "飲食店" : _isCafePlaceForRefs(p) ? "カフェ" : "観光スポット";
  const rawCategory = _translateCategoryJa((p.category || "").split(/[,/・|]/)[0].trim()) || _defaultCat;
  let guideDesc = "";
  if (proseHint) {
    let desc = String(proseHint)
      .replace(/^\[[\d:〜~\-]+\]\s*/, "")
      .replace(/^[-・*①②③④⑤⑥⑦⑧⑨⑩]\s*/, "")
      .trim();
    desc = desc.replace(/[「『][^」』]{1,40}[」』]/g, "").trim();
    desc = desc.replace(/（[^）]{1,40}）/g, "").trim();
    if (p.name) {
      const pNorm = p.name.replace(/\s+/g, "").toLowerCase();
      const dNorm = desc.toLowerCase().replace(/\s+/g, "");
      if (pNorm.length > 1 && dNorm.startsWith(pNorm)) {
        desc = desc.slice(p.name.length).trim();
      }
    }
    desc = desc.replace(/^[でをにはがのへ]\s*/, "").trim();
    desc = desc.replace(/^에서\s+/, "").trim();
    // 이름 제거 후 남은 선두 "(장소명)" 패턴 제거 (e.g. "(키자니아 서울)でのアクティビティ" → "でのアクティビティ")
    if (desc.startsWith("(") || desc.startsWith("（")) {
      desc = desc.replace(/^\s*[（(][^)）]{0,40}[)）]\s*/, "").trim();
    }
    // Mismatch guard: "장소A：설명" prose가 다른 장소 카드에 붙은 경우 버림
    // e.g. prose="유성불고기：ユソン..." 가 "버거킹" 카드에 할당될 때
    const colonMatch = desc.match(/^([^：:]{2,25})[：:]/);
    if (colonMatch) {
      const proseLabelNorm = colonMatch[1].replace(/\s+/g, "").toLowerCase();
      const cardNameNorm = (p.name || "").replace(/\s+/g, "").toLowerCase();
      if (proseLabelNorm && cardNameNorm && !cardNameNorm.includes(proseLabelNorm) && !proseLabelNorm.includes(cardNameNorm)) {
        desc = "";  // 다른 장소 설명이므로 버림
      }
    }
    // strip orphaned parens that remain after bracket-removal (e.g. standalone "）")
    desc = desc.replace(/^[（(）)]+$/, "").trim();
    guideDesc = desc;
  }
  const guideParts = [rawCategory, guideDesc].filter(Boolean);
  const guide = guideParts.join(guideParts.length > 1 ? " · " : "");
  const guideHtml = guide ? `<p class="plan-place-card__guide">${_escapeHtml(guide)}</p>` : "";
  const rating = p.rating ? `★${Number(p.rating).toFixed(1)}` : "";
  const reviews = p.user_rating_count
    ? `<span class="plan-place-card__reviews">(${Number(p.user_rating_count).toLocaleString()}件)</span>`
    : "";
  const naverScore = p.naver_score ? `Naver ${Number(p.naver_score).toFixed(1)}` : "";
  const blogRefs = p.blog_review_count
    ? `<span class="plan-place-card__reviews">Blog ${Number(p.blog_review_count).toLocaleString()}</span>`
    : "";
  const _showReviewKeywords = /식당|맛집|restaurant|레스토랑|카페|커피|cafe|coffee|베이커리|디저트|해물|대게|칼국수|막국수|순두부|짬뽕/i
    .test(`${p.name || ""} ${p.category || ""}`);
  const keywordHtml = _showReviewKeywords && Array.isArray(p.review_keywords) && p.review_keywords.length
    ? `<span class="plan-place-card__price">${_escapeHtml(p.review_keywords.slice(0, 2).join(" / "))}</span>`
    : "";
  let openBadge = "";
  if (p.is_open_now === true) openBadge = '<span class="plan-place-card__open">営業中</span>';
  else if (p.is_open_now === false) openBadge = "";
  const priceLabel = p.price_level
    ? `<span class="plan-place-card__price">${_escapeHtml(p.price_level)}</span>`
    : "";
  const naverQuery = [_stripMixedCJK(p.name || "") || p.name, p.address].filter(Boolean).join(" ");
  const naverCoord = p.latitude != null && p.longitude != null
    ? `&lat=${encodeURIComponent(p.latitude)}&lng=${encodeURIComponent(p.longitude)}`
    : "";
  // naver_score 없는 카드(geocode fallback)는 image_fallback 사용 안 함
  // → 사진 없으면 서버가 404 반환 → onerror 발동 → 📍 표시
  const _photoFallback = p.naver_score != null ? "&image_fallback=1" : "";
  const naverPhotoUrl = p.photo_url || p.naver_photo_url
    || ((p.maps_url || p.google_maps_uri || "").includes("map.naver.com")
      ? `/api/naver-photo/?url=${encodeURIComponent(p.maps_url || p.google_maps_uri)}&q=${encodeURIComponent(naverQuery)}${naverCoord}${_photoFallback}`
      : "")
    || (naverQuery ? `/api/naver-photo/?q=${encodeURIComponent(naverQuery)}${naverCoord}&image_fallback=1` : "");
  const fallbackThumb = '<span class="plan-place-card__img plan-place-card__img--fallback" aria-hidden="true">📍</span>';
  const fallbackThumbAttr = fallbackThumb.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  const thumb = naverPhotoUrl
    ? `<img class="plan-place-card__img" src="${_escapeHtml(naverPhotoUrl)}" alt="" loading="lazy" onerror="this.outerHTML='${fallbackThumbAttr}'" />`
    : p.photo_name
    ? `<img class="plan-place-card__img" src="/api/photo/?name=${encodeURIComponent(p.photo_name)}" alt="" loading="lazy" onerror="this.outerHTML='${fallbackThumbAttr}'" />`
    : fallbackThumb;
  const addr = p.address
    ? `<p class="plan-place-card__addr">${_escapeHtml(p.address)}</p>`
    : "";
  const mapsUri = _mapOpenUrl(p);
  const dirUri = _directionsUrl(p);
  const meta = [rating && `<span class="plan-place-card__rating">${rating}${reviews}</span>`, naverScore && `<span class="plan-place-card__rating">${naverScore}${blogRefs}</span>`, keywordHtml, openBadge, priceLabel]
    .filter(Boolean).join("");
  const thumbLink = mapsUri || dirUri;
  return `<div class="plan-inline-spot"><article class="plan-place-card"><a class="plan-place-card__thumb-link" href="${_escapeHtml(thumbLink)}" target="_blank" rel="noopener">${thumb}<span class="plan-place-card__photo-label">${p.photo_name || naverPhotoUrl ? "外観写真" : "Naver"}</span></a><div class="plan-place-card__body"><h4 class="plan-place-card__name">${name}</h4>${guideHtml}${meta ? `<div class="plan-place-card__meta">${meta}</div>` : ""}${addr}<div class="plan-place-card__actions">${mapsUri ? `<a href="${_escapeHtml(mapsUri)}" target="_blank" rel="noopener" class="plan-place-card__btn">地図</a>` : ""}<a href="${_escapeHtml(dirUri)}" target="_blank" rel="noopener" class="plan-place-card__btn plan-place-card__btn--route">経路</a></div></div></article></div>`;
}

function _renderAnchorPlaceCard(name, displayJa = "") {
  if (!name) return "";
  // displayJa: 일본어 표시명 (e.g. "香湖海辺"), name: 한국어 검색명 (e.g. "항호해변")
  // 일본어 한자로만 된 이름은 한국어 대응어로 검색 (Naver 검색 품질)
  let searchName = name;
  if (_hasJapanesePlaceText(name) && !/[가-힣]/.test(name)) {
    const koAlt = _autoPlaceQueriesFromLine(name)[0];
    if (koAlt) searchName = koAlt;
  }
  const displayName = displayJa ? `${displayJa} (${name})` : name;
  const eName = _escapeHtml(displayName);
  const searchHref = _escapeHtml(`https://map.naver.com/p/search/${encodeURIComponent(searchName)}`);
  const photoSrc = _escapeHtml(`/api/naver-photo/?q=${encodeURIComponent(searchName)}&image_fallback=1`);
  const fallbackSpan = `<span class="plan-place-card__img plan-place-card__img--fallback" aria-hidden="true">📍</span>`;
  const fallbackAttr = fallbackSpan.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  const thumb = `<img class="plan-place-card__img" src="${photoSrc}" alt="" loading="lazy" onerror="this.outerHTML='${fallbackAttr}'" />`;
  return `<div class="plan-inline-spot"><article class="plan-place-card"><a class="plan-place-card__thumb-link" href="${searchHref}" target="_blank" rel="noopener">${thumb}<span class="plan-place-card__photo-label">Naver</span></a><div class="plan-place-card__body"><h4 class="plan-place-card__name">${eName}</h4><p class="plan-place-card__guide">観光スポット</p><div class="plan-place-card__actions"><a href="${searchHref}" target="_blank" rel="noopener" class="plan-place-card__btn">地図</a></div></div></article></div>`;
}

const _PLAN_CLOCK_RE = /\[[\d０-９]{1,2}\s*[:：]\s*[\d０-９]{2}[^\]]*\]/g;
const _PLAN_DAY_HEAD_RE = /^(【\s*)?(\d+)\s*日目|^(【\s*)?最終日|帰国日|最終\s*日|^#{1,3}\s*\d+\s*日目/i;
const _PLAN_SLOT_RE = /^(?:\[(午前|午後|昼食|夕食|夜|朝食|朝|ランチ|ディナー|カフェ|오전|오후|점심|저녁|밤|아침|카페)\]|(午前|午後|昼食|夕食|夜|朝食|朝|ランチ|ディナー|カフェ|오전|오후|점심|저녁|밤|아침|카페)(?=$|\s|[:：]))/;
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

function _planSlotKind(line) {
  const match = String(line || "").trim().match(_PLAN_SLOT_RE);
  const label = match?.slice(1).find(Boolean) || "";
  if (/^(?:昼食|ランチ|점심|夕食|ディナー|저녁)$/.test(label)) return "meal";
  if (/^(?:カフェ|카페)$/.test(label)) return "cafe";
  return label ? "activity" : "";
}

function _formatPlanTextLine(line) {
  return _escapeHtml(_stripPlanClocks(line)).replace(/【(.*?)】/g, "<strong>【$1】</strong>");
}

function _tryRenderPlaceCard(indexes, rendered, url, renderedScope, slotKind = "", globalScope = null, cafeGuard = null) {
  const key = _mapsUrlKey(url);
  if (rendered.has(key)) return false;
  if (renderedScope?.has(key)) return false;
  const place = _lookupPlace(indexes, url);
  if (!place) return false;
  // Anchor/search-query placeholder places must not render as real place cards
  const pid = place.place_id || "";
  if (pid.startsWith("anchor:") || pid.startsWith("cafe-anchor:")) {
    rendered.add(key); // mark consumed so the fallback link is also skipped
    return false;
  }
  // LLM-generated generic placeholder names ("광주광역시의 실재점" etc.) are not real places
  if (/의\s*실재[점店]?$|の実在[店점]?$|실재점$|実在店$/i.test(place.name || "")) {
    rendered.add(key);
    return false;
  }
  if (_isBadPlanPlaceQuery(place.name || "")) {
    rendered.add(key);
    return false;
  }
  // Personal care businesses (hair salons, nail salons, etc.) are not tourist spots
  const _catLow = (place.category || "").toLowerCase();
  if (/미용실|헤어샵|헤어살롱|헤어숍|네일샵|네일아트|왁싱|속눈썹|반영구화장|세탁소|hair\s*salon|beauty\s*salon|nail\s*salon|barber\s*shop/i.test(_catLow)) {
    rendered.add(key);
    return false;
  }
  // 식사 슬롯에 관광 명소(비음식) 카드 차단
  if (slotKind === "meal" && !_isMealPlaceForRefs(place) && !_isCafePlaceForRefs(place)) {
    rendered.add(key);
    return false;
  }
  const _isFoodCard = _isMealPlaceForRefs(place) || _isCafePlaceForRefs(place);
  // 주소 없는 식당·카페: Naver 점수나 이름이라도 있으면 최소 카드 허용.
  // 완전 미매칭(이름·주소·점수 모두 없음)만 차단한다.
  if (_isFoodCard && !place.address && place.naver_score == null && !place.name) {
    rendered.add(key);
    return false;
  }
  // 주소도 Naver 점수도 없는 비음식 장소 = 엔리치 완전 실패 → 탈락
  // 단, URL이 있는 경우(공원·사찰·정원 등 자연/문화 관광지)는 허용
  if (!_isFoodCard && !place.address && place.naver_score == null) {
    if (!(place.maps_url || place.google_maps_uri)) {
      rendered.add(key);
      return false;
    }
  }
  const pk = _placeRenderKey(place);
  if (pk && rendered.has(pk)) { rendered.add(key); return false; }
  if (pk && renderedScope?.has(pk)) { rendered.add(key); return false; }
  // 카페·식당은 날짜 구분 없이 동일 장소 중복 표시 금지 (셀렉티드닉스가 2일, 3일 모두 나오는 문제 방지)
  if (_isFoodCard && pk && globalScope?.has(pk)) { rendered.add(key); return false; }
  if (_isFoodCard && globalScope?.has(key)) { rendered.add(key); return false; }
  // 하루 카페 1개 상한 — cafeGuard 객체의 .used가 true면 두 번째 카페 차단
  const isCafe = _isCafePlaceForRefs(place);
  if (isCafe && cafeGuard?.used) { rendered.add(key); return false; }
  rendered.add(key);
  if (pk) rendered.add(pk);
  renderedScope?.add(key);
  if (pk) renderedScope?.add(pk);
  if (_isFoodCard && globalScope) { globalScope.add(key); if (pk) globalScope.add(pk); }
  if (isCafe && cafeGuard) cafeGuard.used = true;
  return true;
}

function _renderVacationCards(items) {
  const byCategory = {};
  const catOrder = [];
  for (const { category, name, addr } of items) {
    const cat = category || "";
    if (!byCategory[cat]) { byCategory[cat] = []; catOrder.push(cat); }
    byCategory[cat].push({ name, addr });
  }
  const catEmoji = { "풀빌라": "🏊", "캠핑장": "⛺", "글램핑": "⛺", "펜션": "🏡", "해수욕장인근숙소": "🏖" };
  let html = '<div class="plan-refs-section">';
  for (const cat of catOrder) {
    const emoji = catEmoji[cat] || "🏖";
    if (cat) html += `<div class="plan-vacs-category-label">${emoji} ${_escapeHtml(cat)}</div>`;
    html += '<div class="plan-vk-grid">';
    for (const { name, addr } of byCategory[cat]) {
      const naverUrl = `https://map.naver.com/p/search/${encodeURIComponent(name)}`;
      const addrHtml = addr ? `<div class="plan-vk-addr">${_escapeHtml(addr)}</div>` : "";
      html += `<a class="plan-vk-card" href="${_escapeHtml(naverUrl)}" target="_blank" rel="noopener"><div class="plan-vk-thumb-wrap"><span class="plan-vk-thumb plan-vk-thumb--fallback" aria-hidden="true">${emoji}</span></div><div class="plan-vk-text"><div class="plan-vk-name">${_escapeHtml(name)}</div>${addrHtml}</div></a>`;
    }
    html += '</div>';
  }
  html += '</div>';
  return html;
}

function _renderPlanHtml(text, placeIndexes, ticketEventIndex) {
  const lines = text.split(/\r?\n/);
  const out = [];
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

  let _pendingProse = null;
  let renderedCardNames = new Set(); // 렌더된 카드명 → 이후 동일 텍스트 줄 억제
  const emitCard = (place) => {
    const prose = _pendingProse;
    _pendingProse = null;
    // 카드 이름 키를 모두 등록해 이후 echo 줄 억제
    const _cn = place?.name ? _normalizePlaceName(place.name) : "";
    if (_cn) renderedCardNames.add(_cn);
    const _cja = place?.name_ja ? _normalizePlaceName(place.name_ja) : "";
    if (_cja) renderedCardNames.add(_cja);
    return _renderInlinePlaceCard(place, prose);
  };

  const ticketIdx = ticketEventIndex || {};
  const LP = window.LinkPreview;
  const renderedAllPlaces = new Set(); // 카페·식당 날짜 간 중복 방지 (플랜 전체 생애)
  let renderedDayPlaces = new Set();
  let cafeGuard = { used: false }; // 하루 카페 1개 상한 (LLM이 여러 개 출력해도 첫 번째만 표시)
  let currentSlotKind = "";

  const _ticketCardsForUrls = (urls, eventLabel = "") => {
    const _ticketExternalCard = (url, label) => {
      const displayLabel = label || "チケット予約";
      // 지도 버튼: 레이블로 네이버 검색 (경기장명 포함된 레이블이면 정확히 찾힘)
      const mapsSearchUrl = label
        ? `https://map.naver.com/p/search/${encodeURIComponent(label)}`
        : "";
      return (
        `<div class="plan-ticket-external">` +
        `<div class="plan-ticket-external-label">${_escapeHtml(displayLabel)}</div>` +
        `<div class="plan-ticket-external-buttons">` +
        `<a href="${_escapeHtml(mapsSearchUrl || "#")}" target="_blank" rel="noopener" class="plan-place-btn plan-place-btn--map">地図</a>` +
        `<a href="${_escapeHtml(url)}" target="_blank" rel="noopener" class="plan-place-btn plan-place-btn--ticket">🎫 チケット</a>` +
        `</div></div>`
      );
    };
    if (!LP) {
      return urls.map((url) => _ticketExternalCard(url, eventLabel));
    }
    return urls.map((rawUrl) => {
      const url = LP.normalizeUrl(rawUrl);
      const known = ticketIdx[url] || ticketIdx[url.split("?")[0]];
      if (known) {
        const venueCard = known.venue_place ? _renderInlinePlaceCard(known.venue_place) : "";
        return LP.renderCard(LP.eventToPreview(known, url)) + venueCard;
      }
      // KOPIS 미등록 티켓 URL (스포츠 경기 등): 커스텀 카드로 처리
      const label = _normalizeQueryLabelForEnrich(eventLabel) || eventLabel || "";
      return _ticketExternalCard(url, label);
    });
  };

  const isUnresolvedMapsUrl = (url) => {
    const key = _mapsUrlKey(url);
    return Boolean(placeIndexes.unresolved?.[key] && !_lookupPlace(placeIndexes, url));
  };

  const lineLooksLikePlaceLabelBeforeUrl = (rawLine, nextRawLine) => {
    // 슬롯 레이블(午前/昼食/오전/점심 등)은 절대 prose로 취급하지 않음.
    // URL 앞 줄이어도 슬롯 헤더로 처리해야 currentSlotKind가 올바르게 설정된다.
    if (_isPlanSlotLabel(String(rawLine || "").trim())) return false;
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
      const place = _lookupPlace(placeIndexes, url);
      const q = _normalizePlaceName(
        place?.name || placeIndexes.unresolved?.[_mapsUrlKey(url)] || ""
      );
      if (q && (current === q || current.includes(q) || q.includes(current))) {
        return true;
      }
      // 이름이 불일치해도 URL이 실제 장소 카드로 해결되면 prose 억제.
      // LLM이 "장소A" 라고 쓰고 URL은 "장소B"를 가리킬 때
      // "장소A 설명 + 장소B 카드" 이중 출력을 막는다.
      if (place) return true;
    }
    // 다음 줄이 티켓 URL이면 현재 줄을 이벤트 레이블로 캡처 (_pendingProse에 저장)
    if (_PLAN_TICKET_URL_RE.test((nextRawLine || "").trim())) return true;
    return false;
  };

  const processContentLine = (rawLine) => {
    const line = _stripPlanClocks(rawLine);
    const trimmed = line.trim();
    if (!trimmed || _isEchoCardLine(trimmed)) return;
    // 이미 렌더된 카드와 동일한 장소명 텍스트 줄 억제 (카드 아래에 같은 이름 중복 방지)
    const _trimmedKeys = [_normalizePlaceName(trimmed), ..._nameKeysFromLine(trimmed)];
    if (_trimmedKeys.some(k => k && k.length >= 2 && renderedCardNames.has(k))) return;
    const rendered = new Set();

    const ticketUrls = LP ? LP.extractTicketUrls(line) : [];
    if (ticketUrls.length) {
      // _pendingProse = 이전 줄에서 캡처한 이벤트 레이블 (lineLooksLikePlaceLabelBeforeUrl이 캡처)
      const savedLabel = _pendingProse || "";
      _pendingProse = null;
      const cardParts = _ticketCardsForUrls(ticketUrls, savedLabel);
      pushStep(cardParts.join(""));
      return;
    }

    if (_PLAN_TICKET_URL_RE.test(trimmed)) {
      const ticketUrl = LP ? LP.normalizeUrl(trimmed.split(/\s/)[0]) : trimmed.split(/\s/)[0];
      const savedLabel = _pendingProse || "";
      _pendingProse = null;
      pushStep(_ticketCardsForUrls([ticketUrl], savedLabel).join(""));
      return;
    }

    const urls = _extractUrlsFromLine(line);
    if (urls.length) {
      let prose = line;
      const cardParts = [];
      for (const url of urls) {
        const place = _lookupPlace(placeIndexes, url);
        if (place && _tryRenderPlaceCard(placeIndexes, rendered, url, renderedDayPlaces, currentSlotKind, renderedAllPlaces, cafeGuard)) {
          cardParts.push(emitCard(place));
        } else if (place) {
          rendered.add(_mapsUrlKey(url));
          const _pid = place.place_id || "";
          if (_pid.startsWith("anchor:") || _pid.startsWith("cafe-anchor:")) {
            // For anchor places, prefer structured place.name over prose description text
            const _anchorName = place.name || _pendingProse || "";
            if (_anchorName) {
              cardParts.push(
                _pid.startsWith("cafe-anchor:")
                  ? `<a class="plan-place-search-link" href="${_escapeHtml(`https://map.naver.com/p/search/${encodeURIComponent(_anchorName)}`)}" target="_blank" rel="noopener">🔍 ${_escapeHtml(_anchorName)}</a>`
                  : _renderAnchorPlaceCard(_anchorName)
              );
            }
          } else if (_pendingProse !== null) {
            // その他のブロック（品質フィルタ等）: 場所名をテキストで表示（最終フォールバック）
            cardParts.push(`<p class="plan-line">${_formatPlanTextLine(_pendingProse)}</p>`);
          }
          _pendingProse = null;
        } else if (!rendered.has(_mapsUrlKey(url))) {
          rendered.add(_mapsUrlKey(url));
          if (!(currentSlotKind === "cafe" && cafeGuard.used)) {
            const _fbLabel1 = _pendingProse || line.replace(/https?:\/\/[^\s]+/g, "").trim() || placeIndexes.unresolved?.[_mapsUrlKey(url)];
            const fbp = _renderMapsUnresolvedFallback(url, _fbLabel1, currentSlotKind);
            if (fbp) {
              if (currentSlotKind === "cafe") cafeGuard.used = true;
              cardParts.push(fbp);
            }
          }
        }
        prose = prose.replace(url, "");
      }
      if (!cardParts.join("").trim() && urls.every(isUnresolvedMapsUrl)) {
        // 未解決URLかつカード出力なしでも、pendingProse（場所名）があれば表示する
        if (_pendingProse !== null) {
          pushStep(`<p class="plan-line">${_formatPlanTextLine(_pendingProse)}</p>`);
          _pendingProse = null;
        }
        return;
      }
      prose = prose.replace(/^\s*[^:：\n]{1,40}[:：]\s*$/u, "").trim();
      if (prose && !_isEchoCardLine(prose)) {
        // URL 제거 후 남은 prose가 방금 렌더된 카드명과 동일하면 중복 억제
        const _proseKey = _normalizePlaceName(prose.replace(/^[-・*①②③④⑤⑥⑦⑧⑨⑩]\s*/, "").trim());
        if (_proseKey && _proseKey.length >= 2 && renderedCardNames.has(_proseKey)) {
          if (cardParts.length) pushStep(cardParts.join(""));
        } else {
          pushStep(`<p class="plan-line">${_formatPlanTextLine(prose)}</p>${cardParts.join("")}`);
        }
      } else if (cardParts.length) {
        pushStep(cardParts.join(""));
      }
      return;
    }

    if (_PLAN_MAPS_URL_RE.test(trimmed)) {
      const url = trimmed.split(/\s/)[0];
      if (isUnresolvedMapsUrl(url)) {
        rendered.add(_mapsUrlKey(url));
        const fallback = _renderMapsUnresolvedFallback(url, placeIndexes.unresolved?.[_mapsUrlKey(url)], currentSlotKind);
        if (fallback) {
          if (currentSlotKind === "cafe" && cafeGuard.used) {
            // 하루 카페 1개 상한 초과 — 미해결 anchor 카드도 차단
          } else {
            if (currentSlotKind === "cafe") cafeGuard.used = true;
            pushStep(fallback);
          }
        } else if (_pendingProse !== null) {
          // フォールバックなし（食事スロット等）でもpendingProseがあれば場所名を表示する
          pushStep(`<p class="plan-line">${_formatPlanTextLine(_pendingProse)}</p>`);
          _pendingProse = null;
        }
        return;
      }
      const place = _lookupPlace(placeIndexes, url);
      if (place && _tryRenderPlaceCard(placeIndexes, rendered, url, renderedDayPlaces, currentSlotKind, renderedAllPlaces, cafeGuard)) {
        pushStep(emitCard(place));
      } else if (place) {
        rendered.add(_mapsUrlKey(url));
        const _pid2 = place.place_id || "";
        if (_pid2.startsWith("anchor:") || _pid2.startsWith("cafe-anchor:")) {
          const _anchorName2 = place.name || _pendingProse || "";
          if (_anchorName2) {
            pushStep(
              _pid2.startsWith("cafe-anchor:")
                ? `<a class="plan-place-search-link" href="${_escapeHtml(`https://map.naver.com/p/search/${encodeURIComponent(_anchorName2)}`)}" target="_blank" rel="noopener">🔍 ${_escapeHtml(_anchorName2)}</a>`
                : _renderAnchorPlaceCard(_anchorName2)
            );
          }
        } else if (_pendingProse !== null) {
          pushStep(`<p class="plan-line">${_formatPlanTextLine(_pendingProse)}</p>`);
        }
        _pendingProse = null;
      } else if (!rendered.has(_mapsUrlKey(url))) {
        rendered.add(_mapsUrlKey(url));
        if (!(currentSlotKind === "cafe" && cafeGuard.used)) {
          const _fbLabel3 = _pendingProse || placeIndexes.unresolved?.[_mapsUrlKey(url)];
          const f3 = _renderMapsUnresolvedFallback(url, _fbLabel3, currentSlotKind);
          if (f3) {
            if (currentSlotKind === "cafe") cafeGuard.used = true;
            _pendingProse = null;
            pushStep(f3);
          }
        }
      }
      return;
    }

    for (const nk of _nameKeysFromLine(trimmed)) {
      const place = placeIndexes.byName[nk];
      if (!place) continue;
      const uri = place.google_maps_uri || place.maps_url;
      if (uri && _tryRenderPlaceCard(placeIndexes, rendered, uri, renderedDayPlaces, currentSlotKind, renderedAllPlaces, cafeGuard)) {
        pushStep(emitCard(place));
        return;
      }
    }

    // suffix 목록에 없는 관광지 처리: byName 직접 조회 (Reference Data에 있을 때만 카드화, 없으면 텍스트)
    if (trimmed.length >= 2 && trimmed.length <= 30) {
      const _tryDirectLookup = (text) => {
        const k = _normalizePlaceName(text);
        if (!k) return false;
        const p = placeIndexes.byName[k];
        if (!p) return false;
        const u = p.google_maps_uri || p.maps_url;
        if (!u) return false;
        if (_tryRenderPlaceCard(placeIndexes, rendered, u, renderedDayPlaces, currentSlotKind, renderedAllPlaces, cafeGuard)) {
          pushStep(emitCard(p));
          return true;
        }
        return false;
      };
      // 1) 줄 전체 직접 조회
      if (_tryDirectLookup(trimmed)) return;
      // 2) 괄호 안 내용 조회 (예: カヤ庭園（가야정원）→ 가야정원)
      const _parenInner = trimmed.match(/[（(]([^）)]{2,})[）)]/)?.[1];
      if (_parenInner && _tryDirectLookup(_parenInner)) return;
      // 3) 괄호 앞 부분 조회 (예: 曹渓山道立公園（조계산도립공원）→ 曹渓山道立公園)
      const _parenBefore = trimmed.match(/^(.{2,}?)[（(]/)?.[1]?.trim();
      if (_parenBefore && _tryDirectLookup(_parenBefore)) return;
    }

    if (_isPlanSlotLabel(trimmed)) {
      const match = trimmed.match(_PLAN_SLOT_RE);
      const slot = match?.slice(1).find(Boolean) || trimmed;
      currentSlotKind = _planSlotKind(trimmed);
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

  let _inVacSection = false;
  const _vacItems = [];
  let _vacCategory = "";

  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim();
    if (!trimmed) continue;

    // バカンス宿泊候補 섹션 감지
    if (/^##\s*バカンス宿泊候補/.test(trimmed)) {
      _inVacSection = true;
      closeTimeline();
      continue;
    }
    if (_inVacSection) {
      if (/^##/.test(trimmed)) { _inVacSection = false; } // 다른 ## 섹션이 오면 종료
      else {
        const boldM = trimmed.match(/^\*\*(.+?)\*\*:?$/);
        if (boldM) { _vacCategory = boldM[1].trim(); continue; }
        const numM = trimmed.match(/^\d+\.\s+(.+?)(?:\s*[|｜]\s*(.+))?$/);
        if (numM) { _vacItems.push({ category: _vacCategory, name: numM[1].trim(), addr: (numM[2] || "").trim() }); }
        continue;
      }
    }

    // 빈 줄을 건너뛰고 다음 비어있지 않은 줄을 찾아서 URL 존재 여부 확인
    let nextNonEmpty = "";
    for (let j = i + 1; j < lines.length; j++) {
      if (lines[j].trim()) { nextNonEmpty = lines[j]; break; }
    }
    if (lineLooksLikePlaceLabelBeforeUrl(lines[i], nextNonEmpty)) {
      // 前のpendingProseが消費されていない場合（カードブロック等）、先にテキスト出力する
      if (_pendingProse !== null) {
        pushStep(`<p class="plan-line">${_formatPlanTextLine(_pendingProse)}</p>`);
      }
      _pendingProse = trimmed;
      continue;
    }

    if (_isPlanDayHeader(trimmed)) {
      _pendingProse = null;
      renderedDayPlaces = new Set();
      cafeGuard = { used: false };
      renderedCardNames = new Set();
      currentSlotKind = "";
      openTimeline(`<h3 class="plan-day-heading">${_formatPlanTextLine(trimmed)}</h3>`);
      continue;
    }

    processContentLine(lines[i]);
  }

  closeTimeline();
  if (_vacItems.length > 0) out.push(_renderVacationCards(_vacItems));
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
    const hasVacation = (wizardData.activities || []).includes("vacation") || (wizardData.vacationTypes || []).length > 0;
    const title = hasVacation ? "🏖 バカンス宿泊候補" : "🏨 宿泊施設（韓国観光公社）";
    html += `<div class="plan-refs-section"><h3 class="plan-refs-title">${title}</h3><div class="plan-vk-grid">${buildCards(stays, "🏨", false)}</div></div>`;
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

const _FORTUNE_PLACE_RE = /(점집|유명한점집|사주|신점|무당|보살|선녀|만신|철학관|작명|타로|운세|굿당|천궁|신궁|용궁|산신|도사|법사|무속|애동제자|연화암|천신암|선녀암)/i;
const _AM_SHRINE_RE = /(?:^|[\s,·/])[\w가-힣]{1,12}암(?:$|[\s,·/])/i;

function _isFortunePlaceForRefs(place) {
  const blob = `${place?.name || ""} ${place?.address || ""} ${place?.category || ""} ${place?.primary_type || ""}`.toLowerCase();
  if (_FORTUNE_PLACE_RE.test(blob)) return true;
  if (_AM_SHRINE_RE.test(blob) && !/카페|커피|coffee|cafe|베이커리|디저트/.test(blob)) return true;
  return false;
}

// 식당 키워드가 이름에 있으면 카페 분류 금지 (카페거리 주소 포함 식당 방지)
const _CAFE_EXCLUDE_NAME_RE = /국밥|설렁탕|순댓국|삼겹살|갈비(?!천)|삼계탕|칼국수|냉면|해장국|곱창|막창|횟집|생선구이|어탕|추어탕|감자탕|부대찌개|닭갈비|족발|보쌈|고깃집|정육|치킨|돼지(?:국밥|고기|갈비)|닭(?:강정|발|볶음)|짬뽕|짜장|탕수육|해물|낙지|오징어|게장|요리주점|이자카야|선술집|호프집|한정식|한상차림/i;

function _isCafePlaceForRefs(place) {
  if (_isFortunePlaceForRefs(place)) return false;
  const name = (place?.name || "").toLowerCase();
  if (_CAFE_EXCLUDE_NAME_RE.test(name)) return false;
  // 카페 여부는 이름 + 카테고리만 기준 (주소/search_area 제외)
  const nameCat = `${name} ${(place?.category || "")} ${(place?.primary_type || "")}`.toLowerCase();
  // カフェ・スイーツ + 伝統茶・韓菓 (제공된 음식 카테고리 기준)
  return /카페|커피|coffee|cafe|베이커리|디저트|빙수|스이츠|スイーツ|ベーカリー|전통차|한과|다방|찻집/.test(nameCat);
}

function _isMealPlaceForRefs(place) {
  if (_isFortunePlaceForRefs(place)) return false;
  if (_isCafePlaceForRefs(place)) return false;
  const blob = `${place?.name || ""} ${place?.address || ""} ${place?.category || ""} ${place?.primary_type || ""}`.toLowerCase();
  return (
    // 일반 식당 키워드
    /식당|맛집|레스토랑|restaurant|한식|일식|중식|양식/.test(blob) ||
    // 焼肉・구이류
    /구이|불고기|숯불|야키니쿠|바베큐|바비큐/.test(blob) ||
    // 牛・소고기류
    /한우|소고기|갈비|갈빗살|등심|안심|우삼겹|육회|스테이크/.test(blob) ||
    // 豚・돼지류
    /삼겹살|항정살|돼지갈비|돼지고기|보쌈|족발|감자탕|뼈다귀/.test(blob) ||
    // 鶏・닭류
    /치킨|닭갈비|닭한마리|닭볶음|삼계탕|백숙|닭강정|닭발/.test(blob) ||
    // 海鮮・해산물류
    /해물|해산물|횟집|회\b|조개구이|굴|낙지|쭈꾸미|문어|대게|새우|게장|전복|꽃게|오징어/.test(blob) ||
    // 鍋・スープ・탕찌개류
    /탕\b|찌개|국밥|설렁탕|해장국|순댓국|도가니|추어탕|뼈해장국|전골|부대찌개|순두부|김치찌개|된장찌개|곰탕|사골/.test(blob) ||
    // ご飯・お粥・밥죽류
    /백반|비빔밥|돌솥|쌈밥|덮밥|밥집|뷔페|죽\b|죽집|솥밥/.test(blob) ||
    // 韓定食
    /한정식|한상차림/.test(blob) ||
    // 麺・면류
    /냉면|칼국수|짜장|짬뽕|탕수육|수제비|라면|라멘|우동|파스타|쌀국수/.test(blob) ||
    // 屋台・軽食・분식류
    /분식|떡볶이|순대|만두|튀김|포장마차|라볶이/.test(blob) ||
    // バー・居酒屋・요리주점 (제공된 카테고리에 포함)
    /요리주점|이자카야|선술집|호프집|주점/.test(blob) ||
    // 日本料理
    /스시|사시미|야키토리|돈카츠|오마카세|텐동|카이센동/.test(blob) ||
    // 기타 식사 키워드
    /찜\b|곱창|막창|두부요리|도시락|정식\b|고깃집|콩나물/.test(blob)
  );
}

function _isActivityPlaceForRefs(place) {
  return !_isFortunePlaceForRefs(place) && !_isMealPlaceForRefs(place) && !_isCafePlaceForRefs(place);
}

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
  const allPlaces = places || [];
  if (!allPlaces.length) return "";
  const linked = _placesLinkedInPlan(reply, allPlaces);
  const linkedKeys = new Set(linked.map((p) => `${p.name || ""}|${p.address || ""}`));
  const preferLinked = (list) => {
    const linkedSubset = list.filter((p) => linkedKeys.has(`${p.name || ""}|${p.address || ""}`));
    return linkedSubset.length ? linkedSubset.concat(list.filter((p) => !linkedKeys.has(`${p.name || ""}|${p.address || ""}`))) : list;
  };
  const acts = new Set((wizardData.activities || []).map((a) => String(a).toLowerCase()));
  const sections = [];
  const pushSection = (title, list, note, limit = 8) => {
    const seen = new Set();
    const toShow = preferLinked(list).filter((p) => {
      const key = `${p.name || ""}|${p.address || ""}`;
      if (!p.name || seen.has(key)) return false;
      // anchor/fallback places have search queries as names — skip them
      const pid = p.place_id || "";
      if (pid.startsWith("anchor:") || pid.startsWith("cafe-anchor:")) return false;
      seen.add(key);
      return true;
    }).slice(0, limit);
    if (!toShow.length) return;
    const cards = toShow.map((p) => _renderInlinePlaceCard(p)).join("");
    sections.push(`<div class="plan-refs-section"><h3 class="plan-refs-title">${title}</h3>
      <div class="plan-place-grid">${cards}</div>
      <p class="plan-refs-note">${note}</p></div>`);
  };

  if (acts.has("food")) {
    pushSection(
      "🍜 グルメ位置情報",
      allPlaces.filter((p) => _isMealPlaceForRefs(p) && _placeMatchesUserFoodPref(p)),
      "※ 選択したグルメ希望に合わせた昼食・夕食候補です。カードの地図リンクから位置を確認できます。"
    );
  }
  if (acts.has("cafe") || (wizardData.additional?.foodPreferences || []).includes("cafe")) {
    pushSection(
      "☕ カフェ位置情報",
      allPlaces.filter(_isCafePlaceForRefs),
      "※ カフェ巡り用の候補です。本文に入らなかった候補も、位置情報カードとして確認できます。"
    );
  }
  if (["shopping", "nightview", "tradition", "nature", "photo", "kpop", "drama"].some((a) => acts.has(a))) {
    pushSection(
      "📍 やりたいこと周辺スポット",
      allPlaces.filter(_isActivityPlaceForRefs),
      "※ 選択した観光テーマに使える周辺スポットです。自然・フォト・文化・K-pop/公演系の動線確認に使えます。",
      10
    );
  }
  if (!sections.length) {
    pushSection(
      "📍 エリア周辺のスポット",
      allPlaces,
      linked.length
        ? "※ 本文で引用された場所を優先表示しています。"
        : "※ エリア周辺の検索候補です。写真・住所・地図リンクは参照データです。"
    );
  }
  return sections.join("");
}

function _dateLabelJa(dateStr) {
  if (!dateStr) return "";
  const d = new Date(`${dateStr}T00:00:00`);
  if (Number.isNaN(d.getTime())) return dateStr;
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function _hasAnySelected(keys, values) {
  const set = new Set((values || []).map((v) => String(v).toLowerCase()));
  return keys.some((k) => set.has(k));
}

function _buildTravelChecklistItems(meta = {}) {
  const d = wizardData || {};
  const add = d.additional || {};
  const flight = d.flight || {};
  const transport = d.transport || [];
  const activities = d.activities || [];
  const styles = add.travelStyles || [];
  const avoid = add.foodAvoid || add.foodRestrictions || [];
  const hasSports = activities.includes("sports") || (d.sports || []).length > 0;
  const hasTickets = hasSports || (meta.ticket_platform_events || []).length > 0 || (meta.gyeonggi_events || []).length > 0;
  const items = [];
  const push = (group, text, detail = "", priority = "normal") => {
    items.push({ group, text, detail, priority });
  };

  const arrival = flight.selected || {};
  const ret = flight.selectedReturn || {};
  push("航空", "航空券・パスポート名・搭乗時刻を確認", [
    arrival.flight_no ? `往路 ${arrival.flight_no}` : "",
    arrival.dep_time && arrival.arr_time ? `${arrival.dep_time}→${arrival.arr_time}` : "",
    ret.flight_no ? `復路 ${ret.flight_no}` : "",
  ].filter(Boolean).join(" / "), "high");
  if (flight.depart || flight.returnDate) {
    push("航空", "旅行日程をカレンダーに保存", `${_dateLabelJa(flight.depart)}${flight.returnDate ? `〜${_dateLabelJa(flight.returnDate)}` : ""}`);
  }
  push("入国", "パスポート残存期間・入国条件を確認", "出発前に最新条件を確認");
  push("入国", "Q-CODE/税関申告など入国前手続きを確認", "必要な場合は出発前に登録");

  const accomName = d.accommodation?.name || d.accommodation?.address || d.accommodation?.region;
  push("宿泊", "宿泊予約・チェックイン時刻を確認", accomName || "ホテル名・住所・連絡先を保存", "high");
  push("宿泊", "宿泊先住所を韓国語で保存", "タクシー・配送・緊急時に使いやすい形で保存");

  if (_hasAnySelected(["bus"], transport)) {
    push("交通", "空港バスの乗り場・最終便を確認", "仁川空港T1/T2の乗り場番号も確認");
  }
  if (_hasAnySelected(["arex", "subway", "rail"], transport) || !transport.length) {
    push("交通", "T-money/交通カードまたはWOWPASSを準備", "空港・コンビニ・駅でチャージ");
  }
  if (_hasAnySelected(["taxi"], transport)) {
    push("交通", "Kakao T用の宿泊先住所を保存", "韓国語住所と地図リンクを用意");
  }
  if (_hasAnySelected(["rental"], transport)) {
    push("交通", "国際運転免許証・レンタカー予約を確認", "受取場所・返却時間・保険を確認", "high");
  }

  push("通信", "eSIM/ローミング/Wi-Fiを準備", "空港到着後すぐ使えるよう事前設定");
  push("決済", "クレジットカード・現金・WOWPASS/両替を準備", "屋台・市場用に少額現金も用意");
  push("電源", "韓国用C/SEタイプ変換プラグを準備", "モバイルバッテリーも持参");
  push("天気", "出発前日に天気と服装を確認", "雨具・日焼け止め・歩きやすい靴");

  if (hasTickets) {
    push("チケット", "公演・スポーツ観戦チケットを確認", "QR/予約番号・会場・開始時間を保存", "high");
  }
  if (_hasAnySelected(["shop_hard"], styles) || activities.includes("shopping")) {
    push("買い物", "免税・荷物スペース・決済上限を確認", "コスメ/グッズ購入用の余裕を確保");
  }
  if (_hasAnySelected(["no_spicy", "allergy", "vegetarian", "no_pork"], avoid)) {
    push("食事", "苦手な食材・アレルギー説明文を準備", "韓国語/日本語で見せられるメモを保存", "high");
  }
  if (["wheelchair", "stroller", "stairs"].includes(add.mobility || "")) {
    push("移動", "エレベーター・段差・駅出口を事前確認", "無理な徒歩移動を避ける");
  }
  return items;
}

function _renderTravelChecklist(meta = {}) {
  const items = _buildTravelChecklistItems(meta);
  if (!items.length) return "";
  const groups = [];
  const seen = new Set();
  for (const item of items) {
    if (!seen.has(item.group)) {
      seen.add(item.group);
      groups.push(item.group);
    }
  }
  const body = groups.map((group) => {
    const rows = items.filter((it) => it.group === group).map((it, idx) => {
      const id = `travel-check-${_normalizePlaceName(group)}-${idx}`;
      const badge = it.priority === "high" ? `<span class="travel-checklist__badge">重要</span>` : "";
      const detail = it.detail ? `<p>${_escapeHtml(it.detail)}</p>` : "";
      return `<label class="travel-checklist__item" for="${id}">
        <input id="${id}" type="checkbox">
        <span class="travel-checklist__box"></span>
        <span class="travel-checklist__copy"><strong>${_escapeHtml(it.text)}</strong>${detail}</span>
        ${badge}
      </label>`;
    }).join("");
    return `<section class="travel-checklist__group">
      <h4>${_escapeHtml(group)}</h4>
      <div class="travel-checklist__items">${rows}</div>
    </section>`;
  }).join("");
  return `<div class="travel-checklist">
    <div class="travel-checklist__head">
      <h3>旅行チェックリスト</h3>
      <p>出発前に確認しておくと安心な項目です。</p>
    </div>
    <div class="travel-checklist__grid">${body}</div>
  </div>`;
}

// 플랜 텍스트에서 URL 없는 관광지 이름 추출 (괄호형 또는 **bold** 형식)
// 식당/카페 키워드가 포함된 이름은 제외 (food 카드에서 이미 처리)
const _ATTR_PAREN_RE = /([가-힣A-Za-z][가-힣A-Za-z0-9\s]{1,25})\(([가-힣A-Za-z][가-힣A-Za-z0-9\s]{1,25})\)/gu;
const _ATTR_BOLD_RE = /\*{1,2}([가-힣][가-힣A-Za-z0-9\s·]{2,24})\*{1,2}/gu;
const _ATTR_FOOD_SKIP_RE = /식당|레스토랑|맛집|카페|커피|치킨|갈비|국밥|냉면|삼겹|보쌈|보섬|족발|식사|음식|restaurant|cafe|lunch|dinner/i;
const _MAPS_URL_LINE_RE = /https?:\/\/(?:maps\.google\.com|goo\.gl|map\.naver\.com)/;
// 단어 1~2개짜리 에리어 이름(홍대, 강남 등)은 건너뜀 — 너무 범용적
const _ATTR_AREA_SKIP_RE = /^(홍대|명동|강남|인사동|동대문|이태원|한강|성수|압구정|광장시장|여의도|해운대|부산|제주|대전|전주|경주|속초|강릉)$/;
const _ATTR_PROSE_SKIP_RE =
  /(?:おすすめ|推奨|人気|有名|地元|現地|代表|確認|利用|楽し|撮影|散策|移動|候補|動線|経路|満点|愛され|できます|できる|です|ます|합니다|있습니다|추천|인기|현지|대표|확인|이용|즐길|사랑|평판|후보|동선|경로|만점|좋습니다|입니다|있다)/i;

function _looksLikeStandalonePlaceName(name) {
  const t = String(name || "").trim();
  if (!t || t.length < 2 || t.length > 32) return false;
  if (_ATTR_FOOD_SKIP_RE.test(t) || _ATTR_PROSE_SKIP_RE.test(t)) return false;
  if (/[。.!?！？]/.test(t)) return false;
  if (/\s/.test(t) && t.length > 18) return false;
  return true;
}

function _planDetailTextOnly(text) {
  const lines = String(text || "").split(/\r?\n/);
  let start = -1;
  const planHeadIdx = lines.findIndex((line) =>
    /(?:テキスト詳細計画|텍스트\s*상세\s*계획|詳細計画|상세\s*계획)/i.test(line)
  );
  if (planHeadIdx >= 0) {
    start = planHeadIdx + 1;
  } else {
    const dayHeadRe = /(\d+)\s*日目|第\s*(\d+)\s*日|Day\s*(\d+)|최종일|첫날/i;
    const firstDayIdx = lines.findIndex((line) => dayHeadRe.test(line.trim()));
    start = firstDayIdx >= 0 ? firstDayIdx : 0;
  }
  const out = [];
  for (let i = start; i < lines.length; i++) {
    const t = lines[i].trim();
    if (
      /^(?:旅行チェックリスト|旅のチェックリスト|여행\s*체크리스트|チェックリスト|체크리스트)$/i.test(t) ||
      /^🔗/.test(t) ||
      /^🎫/.test(t) ||
      /(?:参照データ|Reference Data|지역\s*주변\s*명소|旅行地周辺|旅行地\s*周辺|スポーツ・イベント・観光|チケット・公演)/i.test(t)
    ) break;
    out.push(lines[i]);
  }
  return out.join("\n");
}

function _extractUnlinkedAttrNames(text, placeIndexes) {
  const results = new Map(); // name → normalizedKey
  const urlLines = new Set();
  const lines = _planDetailTextOnly(text).split(/\r?\n/);

  // 먼저 URL이 있는 라인 바로 윗줄(장소 이름 줄)을 마킹 — 해당 줄은 건너뜀
  for (let i = 0; i < lines.length; i++) {
    if (_MAPS_URL_LINE_RE.test(lines[i])) {
      urlLines.add(i);
      if (i > 0) urlLines.add(i - 1); // 직전 이름 줄도 skip
    }
  }

  const tryAdd = (name, force = false) => {
    name = _cleanPlanPlaceLabel(name);
    if (name.length < 3) return;
    if (!_looksLikeStandalonePlaceName(name)) return;
    if (!force && (_ATTR_FOOD_SKIP_RE.test(name) || _ATTR_AREA_SKIP_RE.test(name))) return;
    const nk = _normalizePlaceName(name);
    if (!nk || placeIndexes.byName[nk]) return;
    results.set(name, nk);
  };

  for (let i = 0; i < lines.length; i++) {
    if (urlLines.has(i)) continue;
    const line = lines[i];
    for (const q of _autoPlaceQueriesFromLine(line)) {
      tryAdd(q, true);
    }
    for (const q of _candidatePlaceNamesFromPlanLine(line)) {
      tryAdd(q, true);
    }
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
  return [...results.keys()].slice(0, 16);
}

async function _enrichUnlinkedAttractions(names, placeIndexes) {
  if (!names.length) return;
  const regionHint = _regionAreaLabels(wizardData.regionAreaKeys?.length ? wizardData.regionAreaKeys : wizardData.regions).join(" ") + " " +
    (wizardData.regionCities || wizardData.regionCitiesOther || "");
  await Promise.allSettled(names.map(async (name) => {
    try {
      const q = encodeURIComponent(`${name} ${regionHint}`.trim());
      const res = await fetch(`/api/places/search/?q=${q}&limit=1&type=general`, {
        credentials: "same-origin",
      });
      if (!res.ok) return;
      const body = await res.json();
      const p = (body.places || [])[0];
      if (!p || !p.maps_url || _isJpAddress(p) || !_placeMatchesSelectedArea(p)) return;
      // Reject results where the place name has NO character overlap with the query.
      // e.g. "대한민국떡방" returned for "김광석 다시그리기길 대구" → completely unrelated.
      const qChars = _normalizePlaceName(name);
      const pChars = _normalizePlaceName(p.name || "");
      const hasOverlap = qChars.length >= 3 && pChars.length >= 3 && (
        qChars.includes(pChars.slice(0, 3)) || pChars.includes(qChars.slice(0, 3))
      );
      if (!hasOverlap) return;
      const enriched = { ...p, google_maps_uri: p.maps_url };
      const nk = _normalizePlaceName(p.name || name);
      const queryKey = _normalizePlaceName(name);
      if (nk) placeIndexes.byName[nk] = enriched;
      // Only alias the query key when the result name is clearly related to the query.
      // Unconditional aliasing caused Naver's off-topic results (e.g., 칠암사계 returned
      // for "감천문화마을 부산") to be indexed under the query key, producing wrong stop labels.
      if (queryKey && queryKey !== nk && (nk.startsWith(queryKey) || queryKey.startsWith(nk))) {
        placeIndexes.byName[queryKey] = enriched;
      }
      if (p.maps_url) placeIndexes.byUrl[_mapsUrlKey(p.maps_url)] = enriched;
    } catch (_) { /* 무시 */ }
  }));
}

async function _enrichTicketVenuePlaces(events, placeIndexes) {
  const list = (events || []).filter((ev) => ev?.venue && !ev.venue_place);
  if (!list.length) return;
  await Promise.allSettled(list.slice(0, 8).map(async (ev) => {
    try {
      const q = encodeURIComponent(`${ev.venue} ${ev.place_region || ""} 韓国`.trim());
      const res = await fetch(`/api/places/search/?q=${q}&limit=1&type=general`, {
        credentials: "same-origin",
      });
      if (!res.ok) return;
      const body = await res.json();
      const p = (body.places || [])[0];
      if (!p || !p.maps_url || _isJpAddress(p) || !_placeMatchesSelectedArea(p)) return;
      const enriched = { ...p, google_maps_uri: p.maps_url };
      ev.venue_place = enriched;
      const nk = _normalizePlaceName(p.name || ev.venue);
      const venueKey = _normalizePlaceName(ev.venue);
      if (nk) placeIndexes.byName[nk] = enriched;
      if (venueKey && venueKey !== nk && (nk.startsWith(venueKey) || venueKey.startsWith(nk))) {
        placeIndexes.byName[venueKey] = enriched;
      }
      if (p.maps_url) placeIndexes.byUrl[_mapsUrlKey(p.maps_url)] = enriched;
    } catch (_) { /* ignore venue enrichment */ }
  }));
}

function _buildPlanConditionTagsHtml() {
  const add = wizardData.additional || {};
  const COMPANION = {
    solo: "🧍 一人旅", couple: "💑 カップル", friends: "👫 友人",
    family: "👨‍👩‍👧 ファミリー", parents: "👴 親との旅行",
  };
  const FOOD_PREF = {
    grilled_meat: "🥩 焼肉・BBQ", bossam: "🐷 ポッサム・チョッパル", soup: "🍲 スープ・チゲ",
    noodles: "🍜 麺料理", seafood: "🦐 海鮮・刺身", chicken: "🍗 韓国チキン",
    snack: "🌭 粉食・軽食", cafe: "☕ カフェ・スイーツ",
  };
  const FOOD_AVOID = {
    no_spicy: "🌶 辛みNG", allergy: "⚕ アレルギー", vegan: "🥗 ベジタリアン", no_pork: "🐷 豚肉なし",
  };
  const PACE = { packed: "⚡ びっしり詰め込む", relaxed: "☁ のんびり余裕" };
  const STYLE = {
    experience: "🎯 体験", sns_hot: "📱 SNS人気", nature: "🌲 自然",
    must_see: "📍 有名観光地", healing: "🧘 癒し", culture: "🎨 文化・歴史",
    local_vibe: "✨ 雰囲気", shop_hard: "🛒 ショッピング", food_first: "🍽 グルメ優先",
  };
  function tag(cls, text) {
    return `<span class="plan-cond-tag plan-cond-tag--${cls}">${text}</span>`;
  }

  const tags = [];
  if (add.companion && COMPANION[add.companion]) tags.push(tag("companion", COMPANION[add.companion]));
  for (const v of (add.foodPreferences || [])) {
    if (FOOD_PREF[v]) tags.push(tag("food", FOOD_PREF[v]));
  }
  for (const v of (add.foodAvoid || [])) {
    if (FOOD_AVOID[v]) tags.push(tag("avoid", FOOD_AVOID[v]));
  }
  if (add.pace && PACE[add.pace]) tags.push(tag("pace", PACE[add.pace]));
  for (const v of (add.travelStyles || [])) {
    if (STYLE[v]) tags.push(tag("style", STYLE[v]));
  }
  if (!add.auto && add.note && add.note.trim()) {
    const short = _escapeHtml(add.note.trim().slice(0, 28)) + (add.note.trim().length > 28 ? "…" : "");
    tags.push(tag("note", `📝 ${short}`));
  }

  if (!tags.length) return "";
  return `<span class="plan-cond-label">生成条件</span>` + tags.join("");
}

async function _displayPlanOutput(data) {
  const condEl = $("planConditionTags");
  if (condEl) {
    const html = _buildPlanConditionTagsHtml();
    condEl.innerHTML = html;
    condEl.style.display = html ? "flex" : "none";
  }

  let reply = data.reply || "";
  const placeIndexes = _buildPlaceIndexes(data.places || []);
  const lines = reply.split(/\r?\n/);
  const initialTicketIdx = window.LinkPreview
    ? LinkPreview.buildEventIndex(data.ticket_platform_events || [])
    : {};
  $("planContent").innerHTML = _renderPlanHtml(reply, placeIndexes, initialTicketIdx);

  const refsEmptyInitial = $("planRefsEmpty");
  if (refsEmptyInitial) refsEmptyInitial.style.display = "none";

  const missing = [];
  for (const url of _extractMapsUrlsFromPlan(reply)) {
    if (_lookupPlace(placeIndexes, url)) continue;
    const idx = lines.findIndex((ln) => ln.includes(url));
    const rawQ = _queryLabelForUrl(lines, url, idx >= 0 ? idx : undefined);
    const query = _normalizeQueryLabelForEnrich(rawQ);
    placeIndexes.unresolved[_mapsUrlKey(url)] = query || rawQ;
    if (_isBadPlanPlaceQuery(query || rawQ)) continue;
    // "광주광역시의 실재점" etc. — LLM-generated generic placeholder that can't be enriched
    if (/의\s*실재[점店]?$|の実在[店점]?$|실재점$|実在店$/i.test(query || "")) continue;
    const matched = _findPlaceByName(placeIndexes, query);
    if (matched) {
      placeIndexes.byUrl[_mapsUrlKey(url)] = matched;
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
          region_city_ids: wizardData.regionCityIds || [],
          region_city_meta: wizardData.regionCityMeta || [],
        }),
      });
      const body = await res.json();
      if (res.ok && body.places) {
        for (const [url, p] of Object.entries(body.places)) {
          if (_isJpAddress(p)) continue;
          placeIndexes.byUrl[_mapsUrlKey(url)] = p;
          for (const name of [p.name, p.name_ja].filter(Boolean)) {
            const nk = _normalizePlaceName(name);
            if (nk) placeIndexes.byName[nk] = p;
          }
        }
      }
    } catch (_) { /* プラン本文のみ */ }
  }
  // URL 없는 관광지 이름(괄호형) 2차 Places 검색
  const unlinkedAttrNames = _extractUnlinkedAttrNames(reply, placeIndexes);
  await _enrichUnlinkedAttractions(unlinkedAttrNames, placeIndexes);
  await _enrichTicketVenuePlaces(data.ticket_platform_events || [], placeIndexes);

  const ticketIdx = window.LinkPreview
    ? LinkPreview.buildEventIndex(data.ticket_platform_events || [])
    : {};
  $("planContent").innerHTML = _renderPlanHtml(reply, placeIndexes, ticketIdx);
  wizardData.currentPlanText = reply;
  wizardData.currentPlanMeta = data || {};
  if (!wizardData.currentPlanProfilePayload) wizardData.currentPlanProfilePayload = { ...wizardData };
  wizardData.planDirty = false;
  _syncPlanShareActions();
  const rerenderPlanText = (nextReply) => {
    if (!nextReply || nextReply === reply) return;
    reply = nextReply;
    wizardData.planEditedText = reply;
    wizardData.currentPlanText = reply;
    wizardData.currentPlanMeta = data || {};
    wizardData.planDirty = true;
    $("planContent").innerHTML = _renderPlanHtml(reply, placeIndexes, ticketIdx);
    if (window.LinkPreview) {
      LinkPreview.hydrate($("planContent"), ticketIdx).catch((err) => {
        console.warn("link preview hydrate failed after route edit", err);
      });
    }
    wizardData.avoid_place_names = _collectPlanPlaceNames(reply, data.places || []);
    wizardData.planShareUrl = "";
    _syncPlanShareActions();
  };
  const hydratePromise = window.LinkPreview
    ? LinkPreview.hydrate($("planContent"), ticketIdx).catch((err) => {
        console.warn("link preview hydrate failed", err);
      })
    : Promise.resolve();

  if (window.PlanMapView) {
    const regions = _regionAreaLabels(wizardData.regionAreaKeys?.length ? wizardData.regionAreaKeys : wizardData.regions);
    const stay = regions.length ? regions.join("·") : "韓国";
    const nights = wizardData.nights || "";
    const days = wizardData.days || "";
    const title =
      nights && days
        ? `${stay}、${nights}泊${days}日のおすすめルート`
        : `${stay}の旅行ルート`;
    const arrivalIata = wizardData.flight?.arrival_airport || getArrivalAirportIata();
    const departureIata = wizardData.flight?.departure_airport || getDepartureAirportIata();
    window.PlanMapView.render(reply, placeIndexes.byUrl, {
      placeIndex: placeIndexes,
      days: wizardData.days,
      nights: wizardData.nights,
      title,
      subtitle: "Dayタブで日程を切り替え。番号順にルートを表示します。",
      arrivalAirport: arrivalIata,
      departureAirport: departureIata,
      accommodation: wizardData.accommodation || null,
      transport: wizardData.transport?.length ? wizardData.transport : _autoTransportForAirport(),
      regions: wizardData.regions || [],
      regionCities: wizardData.regionCities || wizardData.regionCitiesOther || "",
      regionCityIds: wizardData.regionCityIds || [],
      regionCityMeta: wizardData.regionCityMeta || [],
    }).then(() => {
      setTimeout(() => window.PlanMapView?.refreshMapLayout?.(), 450);
      setTimeout(() => window.PlanMapView?.refreshMapLayout?.(), 1200);
    }).catch((err) => {
      console.warn("plan map render failed", err);
    });
  }

  const places = data.places || [];
  const showReferenceSections = false;
  const placesEl = $("planPlacesArea");
  const placesHtml = showReferenceSections ? _renderPlanPlacesRefSection(places, reply) : "";
  if (placesEl) {
    placesEl.innerHTML = placesHtml;
    placesEl.style.display = placesHtml ? "block" : "none";
  }

  const vkEl = $("planVisitKoreaArea");
  const vkHtml = vkEl && showReferenceSections
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
  const eventsHtml = eventsEl && showReferenceSections ? _renderPlanEventsCards(data.gyeonggi_events || []) : "";
  if (eventsEl) {
    eventsEl.innerHTML = eventsHtml;
    eventsEl.style.display = eventsHtml ? "block" : "none";
  }

  const ticketEl = $("planTicketArea");
  const ticketHtml = ticketEl && showReferenceSections
    ? (_renderTicketPlatformCards(data.ticket_platform_events || []) || _renderSelectedKpopNotice(data))
    : "";
  if (ticketEl) {
    ticketEl.innerHTML = ticketHtml;
    ticketEl.style.display = ticketHtml ? "block" : "none";
  }

  const sportsEl = $("planSportsArea");
  const lckHtml = _renderLckVenueCard();
  const sportsCardsHtml = sportsEl ? _renderPlanSportsCards(data.sports_events || []) : "";
  const sportsHtml = lckHtml + sportsCardsHtml + (sportsCardsHtml || lckHtml ? "" : _renderSelectedSportsNotice(data));
  if (sportsEl) {
    sportsEl.innerHTML = sportsHtml;
    sportsEl.style.display = sportsHtml ? "block" : "none";
  }

  const checklistEl = $("planChecklistArea");
  const checklistHtml = checklistEl ? _renderTravelChecklist(data) : "";
  if (checklistEl) {
    checklistEl.innerHTML = checklistHtml;
    checklistEl.style.display = checklistHtml ? "block" : "none";
  }

  const refsEmpty = $("planRefsEmpty");
  const refsBlock = $("planRefsBlock");
  if (refsEmpty) {
    const hasRefs = Boolean(placesHtml || vkHtml || eventsHtml || ticketHtml || sportsHtml);
    refsEmpty.style.display = "none";
    if (refsBlock) refsBlock.style.display = hasRefs ? "block" : "none";
  }

  wizardData.avoid_place_names = _collectPlanPlaceNames(reply, places);
  wizardData.used_plan_places = _collectUsedPlanPlaces(reply, places);

  // 후보 데이터 부족 배너
  const sparseNotice = $("planDataSparseNotice");
  if (sparseNotice) {
    if (data.data_sparse) {
      const alts = (data.alternative_regions || []).map((r) => _escapeHtml(r));
      const altHtml = alts.length
        ? `<div class="plan-sparse-alts">${alts.map((r) =>
            `<button class="plan-sparse-alt-btn" onclick="_addRegionAndRegenerate('${r}')">${r}</button>`
          ).join("")}</div>`
        : "";
      sparseNotice.innerHTML = `
        <div class="plan-sparse-banner">
          <span class="plan-sparse-icon">⚠️</span>
          <span class="plan-sparse-msg">このエリアの観光スポット・飲食店データが少なめです。近隣エリアも候補に含めると、より充実したプランになります。</span>
          ${altHtml}
          <button class="plan-sparse-dismiss" onclick="this.closest('#planDataSparseNotice').style.display='none'">✕</button>
        </div>`;
      sparseNotice.style.display = "block";
    } else {
      sparseNotice.style.display = "none";
    }
  }

  await hydratePromise;
}

function _addRegionAndRegenerate(region) {
  // 근접 지역을 여행 지역에 추가하고 플랜 재생성
  if (!wizardData.regionCities) {
    wizardData.regionCities = region;
  } else if (!wizardData.regionCities.includes(region)) {
    wizardData.regionCities = wizardData.regionCities + "," + region;
  }
  const btn = $("generatePlanBtn") || $("reGeneratePlanBtn");
  if (btn) btn.click();
}

const _LEAGUE_LABELS = {
  kbo: "KBO（野球）",
  kbl: "KBL（バスケ）",
  kovo: "KOVO（バレー）",
  kleague: "Kリーグ（サッカー）",
  kleague2: "K2（サッカー）",
  lck: "LCK（e-スポーツ）",
};

function _renderTicketPlatformCards(events) {
  if (!events || !events.length || !window.LinkPreview) return "";
  const cards = events.slice(0, 8).map((ev) => {
    const url = LinkPreview.normalizeUrl(ev.ticket_url || "");
    const venueCard = ev.venue_place ? _renderInlinePlaceCard(ev.venue_place) : "";
    return `<div class="plan-ticket-with-venue">${LinkPreview.renderCard(LinkPreview.eventToPreview(ev, url))}${venueCard}</div>`;
  }).join("");
  return `<div class="plan-refs-section">
    <h3 class="plan-refs-title">🎫 公演情報（KOPIS）</h3>
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
    const source = _src.startsWith("kintex") ? "KINTEX" : _src === "kpop_web" ? "K-pop公演" : "全国イベント";
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

function _selectedActivitiesSet() {
  return new Set((wizardData.activities || []).map((a) => String(a).toLowerCase()));
}

function _renderSelectedKpopNotice(data) {
  const acts = _selectedActivitiesSet();
  if (!acts.has("kpop")) return "";
  const hasEvents = (data?.ticket_platform_events || []).length || (data?.gyeonggi_events || []).length;
  if (hasEvents) return "";
  return `<div class="plan-refs-section">
    <h3 class="plan-refs-title">🎵 K-pop・公演情報</h3>
    <div class="sport-event-card sport-event-card--notice">
      <span class="sport-league">KOPIS</span>
      <p class="sport-notice-title">K-popが選択されています</p>
      <p class="sport-notice-body">旅行期間・地域に一致するKOPIS大衆音楽候補を取得できませんでした。一般の都市案内やWikiページは公演カードとして表示しません。</p>
    </div>
  </div>`;
}

function _renderSelectedSportsNotice(data) {
  const acts = _selectedActivitiesSet();
  const selectedSports = wizardData.sports || [];
  if (!acts.has("sports") && !selectedSports.length) return "";
  if ((data?.sports_events || []).length) return "";
  const sportText = selectedSports.length
    ? selectedSports.map((s) => _LEAGUE_LABELS[s] || String(s)).join(" / ")
    : "KBO / K League / KBL / KOVO";
  return `<div class="plan-refs-section">
    <h3 class="plan-refs-title">🏟 スポーツ観戦</h3>
    <div class="sport-event-card sport-event-card--notice">
      <span class="sport-league">${_escapeHtml(sportText)}</span>
      <p class="sport-notice-title">スポーツ観戦が選択されています</p>
      <p class="sport-notice-body">旅行期間・地域に一致する公式試合候補を取得できませんでした。条件に合う試合がない場合でも、この選択状態は結果画面に残します。</p>
    </div>
  </div>`;
}

function _renderPlanSportsCards(events) {
  if (!events.length) return "";
  const leagueOrder = ["kbo", "kleague", "kleague2", "kbl", "kovo", "lck"];
  const byLeague = new Map();
  for (const ev of events) {
    const key = ev.league || "other";
    if (!byLeague.has(key)) byLeague.set(key, []);
    byLeague.get(key).push(ev);
  }
  const renderCard = (ev) => {
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
  };
  const renderDateGroup = (date, items) => {
    const label = date || "日程未定";
    return `<div class="sport-date-group">
      <h5 class="sport-date-title">${_escapeHtml(label)}</h5>
      <div class="plan-sport-grid">${items.map(renderCard).join("")}</div>
    </div>`;
  };
  const sections = [...byLeague.entries()]
    .sort(([a], [b]) => {
      const ai = leagueOrder.indexOf(a);
      const bi = leagueOrder.indexOf(b);
      if (ai !== -1 || bi !== -1) return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
      return String(a).localeCompare(String(b), "ja");
    })
    .map(([league, items]) => {
      const leagueLabel = _LEAGUE_LABELS[league] || league || "スポーツ";
      const byDate = new Map();
      const sorted = [...items].sort((a, b) =>
        String(a.date || "").localeCompare(String(b.date || "")) ||
        String(a.time || "").localeCompare(String(b.time || ""))
      );
      for (const ev of sorted) {
        const dateKey = ev.status === "off_season_notice" ? "お知らせ" : (ev.date || "日程未定");
        if (!byDate.has(dateKey)) byDate.set(dateKey, []);
        byDate.get(dateKey).push(ev);
      }
      return `<section class="sport-league-group">
        <h4 class="sport-league-title">${_escapeHtml(leagueLabel)}</h4>
        ${[...byDate.entries()].map(([date, dayItems]) => renderDateGroup(date, dayItems)).join("")}
      </section>`;
    });
  return `<div class="plan-refs-section"><h3 class="plan-refs-title">⚽ 試合日程（宿泊先近郊・公式データ参照）</h3>
    <div class="plan-sport-groups">${sections.join("")}</div>
    <p class="plan-refs-note">※ 宿泊先近くで開催される試合のみ表示。最新日程・チケットは各公式サイトでご確認ください。</p></div>`;
}

function _renderLckVenueCard() {
  const cityIds = wizardData.regionCityIds || [];
  const acts = wizardData.activities || [];
  if (!cityIds.includes("jongno") || !acts.includes("sports")) return "";
  const ticketUrl = "https://ticket.interpark.com/Contents/Sports/GoodsInfo?SportsCode=07032";
  return `<div class="plan-refs-section">
    <h3 class="plan-refs-title">🎮 e-スポーツ観戦 — LCK（鍾路）</h3>
    <div class="plan-sport-grid">
      <div class="sport-event-card">
        <span class="sport-league">LCK（League of Legends Champions Korea）</span>
        <strong class="sport-venue-name">그랑서울 LoL Park</strong>
        <span class="sport-venue">서울 종로구 새문안로 68, 그랑서울타워 B1</span>
        <a href="${_escapeHtml(ticketUrl)}" target="_blank" rel="noopener" class="sport-official">チケットを見る →</a>
      </div>
    </div>
    <p class="plan-refs-note">※ LCKは인터파크티켓で販売。シーズン・試合日程は公式サイト（lck.kr）でご確認ください。</p>
  </div>`;
}

// ── UTILS ─────────────────────────────────────────────────────────────────
function fmtDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
}
function fmtDateJa(d) {
  return `${d.getFullYear()}年${d.getMonth()+1}月${d.getDate()}日`;
}

init();
