"""Shared data structures for the chat routing pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RagSearchBundle:
    results: list[dict]
    backend: str
    area_filter: str = ""


@dataclass
class RouteResult:
    reply: str
    category: str
    keyword: str
    sources_used: list[str] = field(default_factory=list)
    rag_count: int = 0
    places_count: int = 0
    is_fallback: bool = False
    rag_result_ids: list[str] = field(default_factory=list)
    rag_area: str = ""
    retrieval_backend: str = ""
    places: list = field(default_factory=list)
    itinerary_places: list = field(default_factory=list)
    places_error: str = ""
    sports_events: list = field(default_factory=list)
    flights: list = field(default_factory=list)
    flights_error: str = ""
    airport: Any | None = None
    flight_subtype: str = ""
    visitkorea_stays: list = field(default_factory=list)
    visitkorea_festivals: list = field(default_factory=list)
    visitkorea_attractions: list = field(default_factory=list)
    visitkorea_error: str = ""
    gyeonggi_events: list = field(default_factory=list)
    web_search_results: list = field(default_factory=list)
    ticket_platform_events: list = field(default_factory=list)
    token_stream: Any | None = field(default=None, repr=False)
