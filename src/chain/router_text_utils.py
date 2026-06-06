"""Small text helpers shared by the router pipeline."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator

HISTORY_CONTENT_LIMIT = 2000

_INTERNAL_DATA_DISCLOSURE_RE = re.compile(
    r"(Reference Data|데이터셋|dataset|미게재|未掲載|未記載|取得不可|取得でき|"
    r"検証済み.*(?:ありません|ない)|API.*(?:없|無|未|取得|unavailable|available)|"
    r"(?:생략|省略).*(?:데이터|Data|情報|미게재|未掲載)|"
    r"時間外の可能性|営業時間外かもしれ|"
    r"候補(?:が|は|も)?.*(?:足り|少な|終わ|尽き|ない|不足)|候補不足|"
    r"食事候補.*(?:ない|不足|終わ|尽き)|"
    r"후보.*(?:부족|없|다했|끝났)|식사\s*후보.*(?:부족|없|다했|끝났))",
    re.IGNORECASE,
)


def strip_internal_data_disclosure(text: str) -> str:
    """Remove internal source-availability explanations from user-visible text."""
    if not text:
        return text
    lines = []
    for line in text.splitlines():
        if _INTERNAL_DATA_DISCLOSURE_RE.search(line):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def trim_history_content(content: str, *, limit: int = HISTORY_CONTENT_LIMIT) -> str:
    text = str(content or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...[history truncated]"


def sanitize_stream_chunks(chunks: Iterable[str]) -> Iterator[str]:
    """Keep streaming output from exposing internal source-availability details."""
    buffer = ""
    flush_chars = 360
    guard_chars = 120
    for chunk in chunks:
        if not chunk:
            continue
        buffer += chunk
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            if not _INTERNAL_DATA_DISCLOSURE_RE.search(line):
                yield line + "\n"
        if len(buffer) > flush_chars + guard_chars:
            safe, buffer = buffer[:-guard_chars], buffer[-guard_chars:]
            if safe and not _INTERNAL_DATA_DISCLOSURE_RE.search(safe):
                yield safe
    if buffer and not _INTERNAL_DATA_DISCLOSURE_RE.search(buffer):
        yield buffer
