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
