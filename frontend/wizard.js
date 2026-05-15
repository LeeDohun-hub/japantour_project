/* Korea Travel Wizard — single-page 9-step flow */

const TOTAL_STEPS = 8;
let currentStep = 1;
let currentUser = null;
let wizardData = {};

const $ = (id) => document.getElementById(id);
const wizFill    = $("wizFill");
const wizStepsRow = $("wizStepsRow");
const wizNavBar  = $("wizNavBar");
const wizBtnBack = $("wizBtnBack");
const wizBtnNext = $("wizBtnNext");

const STEP_LABELS = ["ログイン","フライト","宿泊","交通","観光","予算","詳細","プラン"];

// ── INIT ──────────────────────────────────────────────────────────────────
function init() {
  buildStepDots();
  checkAuthState();
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
  setupStep6();
  setupNavigation();

  // OAuth error param
  if (location.search.includes("oauth_error=1")) {
    const el = $("oauthErrorMsg");
    if (el) el.style.display = "block";
  }

  goToStep(1);
}

// ── STEP DOTS ─────────────────────────────────────────────────────────────
function buildStepDots() {
  wizStepsRow.innerHTML = STEP_LABELS.map((label, i) => `
    <div class="wiz-dot" data-step="${i + 1}">
      <div class="wiz-dot-circle">${i + 1}</div>
      <div class="wiz-dot-label">${label}</div>
    </div>`).join("");
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
    goToStep(1);
  });
}

// ── VALIDATION ────────────────────────────────────────────────────────────
function validate(step) {
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
      wizardData.flight = {
        from:       $("flightFrom").value,
        to:         $("flightTo").value,
        depart:     $("flightDepart").value,
        returnDate: $("flightReturn").value,
        passengers: +$("passengerStepper").querySelector(".step-val").textContent || 1,
      };
      wizardData.nights = nights;
      wizardData.days   = days;
      break;
    }
    case 3: {
      const sel = document.querySelector("#accomOptions .option-card.selected");
      wizardData.accommodation = {
        type:    sel?.dataset.val || "",
        address: $("accomAddress")?.value || "",
        region:  $("accomRegion")?.value  || "",
      };
      break;
    }
    case 4:
      wizardData.transport = chips("transportChips");
      break;
    case 5:
      wizardData.regions    = chips("regionChips");
      wizardData.activities = chips("activityChips");
      break;
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

function setLoggedIn(user) {
  currentUser = user;
  wizardData.user = user;
  $("authSection").style.display = "none";
  $("loggedInSection").style.display = "block";
  $("s1Avatar").textContent = user.username[0].toUpperCase();
  $("s1Name").textContent = `${user.username} さん`;
  const lbl = $("navUserLabel");
  if (lbl) lbl.textContent = user.username;
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
    const res = await fetch("/api/auth/me/");
    if (res.ok) {
      const data = await res.json();
      if (data.authenticated) setLoggedIn(data.user);
    }
  } catch { /* ignore */ }
}

// ── STEP 2: FLIGHTS ───────────────────────────────────────────────────────
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
    $("accomDetailDecided").style.display   = val === "decided"   ? "block" : "none";
    $("accomDetailUndecided").style.display = val === "undecided" ? "block" : "none";
    $("accomDetailFriend").style.display    = val === "friend"    ? "block" : "none";
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
  const userName = currentUser?.username || "ゲスト";

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

    setTimeout(() => {
      $("planLoadingArea").style.display = "none";
      $("planTitle").textContent = `${userName}さんの旅行プラン`;
      $("planContent").textContent = data.reply || "";
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
                 hallyu:"韓流", nature:"自然", photo:"フォトスポット" };
  const tMap = { arex:"空港鉄道", taxi:"タクシー", bus:"空港バス", rental:"レンタカー" };
  const cMap = { solo:"一人旅", couple:"カップル", friends:"友人", family:"ファミリー", parents:"親孝行" };
  const pMap = { packed:"びっしり", relaxed:"のんびり" };
  const sMap = { budget:"コスパ重視", normal:"バランス", premium:"プレミアム" };

  const lines = [
    `${currentUser?.username || "ゲスト"}さんの韓国旅行プランを日本語で作成してください。以下の情報を基に、日程ごとの具体的なプランを提案してください。`,
  ];

  if (d.flight) {
    const f = d.flight;
    lines.push(`【フライト】${f.from}→${f.to}、出発:${f.depart||"未定"}、帰国:${f.returnDate||"未定"}、${f.passengers}名`);
  }
  if (d.nights) lines.push(`【日程】${d.nights}泊${d.days}日`);

  if (d.accommodation?.type) {
    const typeMap = { decided:"予約済み", undecided:"未定", friend:"友人・家族宅" };
    const loc = d.accommodation.address || d.accommodation.region || "";
    lines.push(`【宿泊】${typeMap[d.accommodation.type]}${loc ? " " + loc : ""}`);
  }
  if (d.transport?.length)
    lines.push(`【空港交通】${d.transport.map((t)=>tMap[t]||t).join("・")}`);
  if (d.regions?.length)
    lines.push(`【希望エリア】${d.regions.map((r)=>rMap[r]||r).join("・")}`);
  if (d.activities?.length)
    lines.push(`【やりたいこと】${d.activities.map((a)=>aMap[a]||a).join("・")}`);

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
    if (add.foodRestrictions?.length) parts.push(`食事制限:${add.foodRestrictions.join("・")}`);
    if (add.note)                   parts.push(add.note);
    if (parts.length) lines.push(`【その他】${parts.join("、")}`);
  }

  lines.push(`\n「K-Culture 관광 콘텐츠 특화 일본어 말뭉치 데이터」を活用した、観光スポット・食事・交通・予算の目安を含む日程別プランを日本語で作成してください。`);
  return lines.join("\n");
}

// ── UTILS ─────────────────────────────────────────────────────────────────
function fmtDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
}
function fmtDateJa(d) {
  return `${d.getFullYear()}年${d.getMonth()+1}月${d.getDate()}日`;
}

init();
