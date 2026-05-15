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
  div.innerHTML = `<div class="label">${label}</div>${escapeHtml(content)}${extraHtml}`;
  chatLog.appendChild(div);

  if (role === "assistant") {
    requestAnimationFrame(() => {
      if (div.scrollHeight > COLLAPSE_HEIGHT) {
        div.classList.add("collapsed");
        const btn = document.createElement("button");
        btn.className = "expand-btn";
        btn.textContent = "もっと見る ▼";
        btn.addEventListener("click", () => {
          div.classList.remove("collapsed");
          btn.textContent = "折りたたむ ▲";
          btn.addEventListener("click", () => {
            div.classList.add("collapsed");
            btn.textContent = "もっと見る ▼";
          }, { once: true });
        }, { once: true });
        div.appendChild(btn);
      }
      chatLog.scrollTop = chatLog.scrollHeight;
    });
  } else {
    chatLog.scrollTop = chatLog.scrollHeight;
  }
}

const LOADING_MESSAGES = [
  "여행 관련 요구사항을 확인중입니다",
  "관련 정보를 검색하고 있습니다",
  "답변을 생성중입니다",
];

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

    const msgIdx = progress < 35 ? 0 : progress < 70 ? 1 : 2;
    statusEl.textContent = LOADING_MESSAGES[msgIdx] + dots;
    barEl.style.width = progress + "%";
    pctEl.textContent = Math.floor(progress) + "%";
  }, 250);

  return {
    remove() {
      clearInterval(timer);
      barEl.style.width = "100%";
      pctEl.textContent = "100%";
      statusEl.textContent = "완료";
      setTimeout(() => div.remove(), 300);
    },
  };
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
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
    if (!res.ok) {
      appendBubble("assistant", data.detail || `HTTP ${res.status}`);
      return;
    }
    if (data.session_id) {
      sessionId = data.session_id;
    }

    let extra = "";
    if (data.translated_ko) {
      extra = `<div class="translation"><h4>한국어 번역</h4>${escapeHtml(data.translated_ko)}</div>`;
    }
    appendBubble("assistant", data.reply || "", extra);

    history.push({ role: "user", content: text });
    history.push({ role: "assistant", content: data.reply || "" });
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
