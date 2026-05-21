/**
 * Interpark ticket link previews — shared by wizard plan & chat.
 */
(function (global) {
  const TICKET_URL_RE =
    /https?:\/\/(?:tickets\.)?interpark\.com\/[^\s\]<")\]\u3001\u3002.,]+/gi;

  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  function normalizeUrl(url) {
    return String(url || "").replace(/[).,。、\]]+$/g, "").trim();
  }

  function extractTicketUrls(text) {
    const found = new Set();
    const re = new RegExp(TICKET_URL_RE.source, "gi");
    let m;
    while ((m = re.exec(text)) !== null) {
      const u = normalizeUrl(m[0]);
      if (u) found.add(u);
    }
    return [...found];
  }

  function goodsCodeFromUrl(url) {
    const m = String(url).match(/\/goods\/(\d+)/i);
    return m ? m[1] : null;
  }

  function buildEventIndex(events) {
    const byUrl = {};
    for (const ev of events || []) {
      const raw = ev.ticket_url || "";
      if (!raw) continue;
      const key = normalizeUrl(raw.split("?")[0]);
      byUrl[key] = ev;
      const code = ev.goods_code || goodsCodeFromUrl(key);
      if (code) {
        byUrl[`https://tickets.interpark.com/goods/${code}`] = ev;
      }
    }
    return byUrl;
  }

  function eventToPreview(ev, url) {
    const start = ev.play_start || "";
    const end = ev.play_end || "";
    const period =
      start && end && start !== end ? `${start}〜${end}` : start || end || "";
    const parts = [period, ev.venue, ev.place_region].filter(Boolean);
    return {
      url: url || ev.ticket_url,
      title: ev.title || "公演・イベント",
      description: parts.join(" · ") || ev.genre_label_ko || "",
      image: null,
      site_name: "INTERPARK TICKET",
      from_api: true,
    };
  }

  function renderCard(preview) {
    const url = escapeHtml(preview.url || "");
    const title = escapeHtml(preview.title || "チケット詳細");
    const desc = preview.description
      ? `<p class="ticket-preview-desc">${escapeHtml(preview.description)}</p>`
      : "";
    const site = escapeHtml(preview.site_name || "INTERPARK TICKET");
    const img = preview.image
      ? `<div class="ticket-preview-thumb"><img src="${escapeHtml(preview.image)}" alt="" loading="lazy" decoding="async" onerror="this.parentElement.classList.add('ticket-preview-thumb--fallback')"/></div>`
      : `<div class="ticket-preview-thumb ticket-preview-thumb--fallback" aria-hidden="true">🎫</div>`;
    return `<a class="ticket-preview-card" href="${url}" target="_blank" rel="noopener noreferrer">${img}<div class="ticket-preview-body"><span class="ticket-preview-site">${site}</span><strong class="ticket-preview-title">${title}</strong>${desc}<span class="ticket-preview-cta">チケットを見る →</span></div></a>`;
  }

  function renderSkeleton(url) {
    const u = escapeHtml(normalizeUrl(url));
    return `<div class="ticket-preview-card ticket-preview-card--loading" data-preview-url="${u}"><div class="ticket-preview-thumb ticket-preview-thumb--fallback" aria-hidden="true">🎫</div><div class="ticket-preview-body"><span class="ticket-preview-site">INTERPARK TICKET</span><strong class="ticket-preview-title">プレビューを読み込み中…</strong></div></div>`;
  }

  async function fetchPreview(url) {
    const res = await fetch(`/api/link-preview/?url=${encodeURIComponent(normalizeUrl(url))}`);
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || body.error || `HTTP ${res.status}`);
    return body;
  }

  function stripUrlsFromProse(text, urls) {
    let prose = text;
    for (const url of urls) {
      const esc = url.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      prose = prose.replace(new RegExp(`\\(\\s*${esc}\\s*\\)`, "g"), "");
      prose = prose.replace(url, "");
    }
    return prose.replace(/\s{2,}/g, " ").replace(/\(\s*\)/g, "").trim();
  }

  async function hydrate(root, eventIndex) {
    if (!root) return;
    const nodes = root.querySelectorAll("[data-preview-url]");
    const idx = eventIndex || {};
    await Promise.all(
      [...nodes].map(async (el) => {
        const url = normalizeUrl(el.getAttribute("data-preview-url"));
        if (!url || el.dataset.previewDone === "1") return;
        el.dataset.previewDone = "1";
        const known = idx[url] || idx[url.split("?")[0]];
        try {
          const preview = known
            ? eventToPreview(known, url)
            : await fetchPreview(url);
          const card = document.createElement("div");
          card.innerHTML = renderCard(preview);
          const anchor = card.firstElementChild;
          if (anchor) el.replaceWith(anchor);
        } catch (_) {
          el.innerHTML = `<a class="ticket-preview-card ticket-preview-card--fallback" href="${escapeHtml(url)}" target="_blank" rel="noopener"><div class="ticket-preview-thumb ticket-preview-thumb--fallback">🎫</div><div class="ticket-preview-body"><span class="ticket-preview-site">INTERPARK TICKET</span><strong class="ticket-preview-title">チケットページを開く</strong><span class="ticket-preview-cta">リンクを開く →</span></div></a>`;
        }
      })
    );
  }

  global.LinkPreview = {
    TICKET_URL_RE,
    extractTicketUrls,
    buildEventIndex,
    eventToPreview,
    renderCard,
    renderSkeleton,
    fetchPreview,
    stripUrlsFromProse,
    hydrate,
    normalizeUrl,
    escapeHtml,
  };
})(window);
