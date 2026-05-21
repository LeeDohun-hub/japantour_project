"""Fetch Open Graph metadata for allowed ticket URLs (Interpark NOL)."""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import urlparse

import requests

_ALLOWED_HOSTS = frozenset(
    {
        "tickets.interpark.com",
        "ticket.interpark.com",
        "www.ticket.interpark.com",
    }
)

_OG_TAG_RE = re.compile(
    r'<meta\s+(?:[^>]*?\s)?(?:property|name)=["\'](og:[^"\']+)["\']\s+'
    r'(?:[^>]*?\s)?content=["\']([^"\']*)["\']'
    r'|'
    r'<meta\s+(?:[^>]*?\s)?content=["\']([^"\']*)["\']\s+'
    r'(?:[^>]*?\s)?(?:property|name)=["\'](og:[^"\']+)["\']',
    re.IGNORECASE,
)

_TITLE_RE = re.compile(r"<title[^>]*>([^<]+)</title>", re.IGNORECASE)


def _is_allowed_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host in _ALLOWED_HOSTS


def _parse_og_tags(html: str) -> dict[str, str]:
    tags: dict[str, str] = {}
    for m in _OG_TAG_RE.finditer(html):
        if m.group(1) and m.group(2):
            key, val = m.group(1).lower(), unescape(m.group(2).strip())
        else:
            val, key = unescape(m.group(3).strip()), (m.group(4) or "").lower()
        if key and val and key not in tags:
            tags[key] = val
    return tags


def fetch_link_preview(url: str, *, timeout: int = 12) -> dict[str, str | None]:
    """Return preview dict: url, title, description, image, site_name."""
    if not _is_allowed_url(url):
        raise ValueError("URL host not allowed for preview")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; JapanTourBot/1.0; +https://localhost) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,ko;q=0.9,en;q=0.8",
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    if resp.encoding is None or resp.encoding.lower() in ("iso-8859-1", "ascii"):
        resp.encoding = resp.apparent_encoding or "utf-8"
    html = resp.text[:500_000]
    og = _parse_og_tags(html)

    title = og.get("og:title") or ""
    goods_name = re.search(
        r'"goodsName"\s*:\s*"((?:\\.|[^"\\])*)"',
        html,
    )
    if goods_name:
        title = unescape(goods_name.group(1).replace("\\u0026", "&"))
    if not title or title.lower() in ("nol ticket", "nol 티켓", "nol チケット"):
        tm = _TITLE_RE.search(html)
        if tm:
            title = unescape(tm.group(1).strip())
    if not title:
        play_name = re.search(r'"playName"\s*:\s*"((?:\\.|[^"\\])*)"', html)
        if play_name:
            title = unescape(play_name.group(1).replace("\\u0026", "&"))

    description = og.get("og:description") or og.get("description") or ""
    image = og.get("og:image") or ""
    site_name = og.get("og:site_name") or "INTERPARK TICKET"

    return {
        "url": url,
        "title": title or None,
        "description": (description[:280] if description else None),
        "image": image or None,
        "site_name": site_name,
    }
