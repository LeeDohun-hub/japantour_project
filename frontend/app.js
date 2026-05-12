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

function appendBubble(role, content, extraHtml = "") {
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  const label = role === "user" ? "You" : "Guide";
  div.innerHTML = `<div class="label">${label}</div>${escapeHtml(content)}${extraHtml}`;
  chatLog.appendChild(div);
  chatLog.scrollTop = chatLog.scrollHeight;
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
      ? "API: 接続済み（OpenAI キーあり）"
      : "API: 接続済み（OpenAI キーなし — 応答はプレースホルダ）";
  } catch {
    healthStatus.textContent = "API: 未接続";
    healthStatus.classList.add("error");
  }
}

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = messageInput.value.trim();
  if (!text) return;

  appendBubble("user", text);
  messageInput.value = "";
  btnSend.disabled = true;

  try {
    const res = await fetch("/api/chat/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        reply_language: replyLanguage.value,
        history: history.map(({ role, content }) => ({ role, content })),
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      appendBubble("assistant", data.detail || `HTTP ${res.status}`);
      return;
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
    appendBubble("assistant", String(err));
  } finally {
    btnSend.disabled = false;
    messageInput.focus();
  }
});

btnReset.addEventListener("click", () => {
  history = [];
  chatLog.innerHTML = "";
});

fetchHealth();
