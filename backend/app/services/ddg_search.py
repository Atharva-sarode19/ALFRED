"""
DuckDuckGo implementation of `SearchProvider` via the `ddgs` package
(no API key). It scrapes a public endpoint, so expect occasional rate limits;
swap in Brave/Tavily/etc. by adding another SearchProvider.
"""

from __future__ import annotations

import asyncio
import logging

from app.services.search import SearchError, SearchProvider, SearchResult

logger = logging.getLogger("alfred.search.ddg")

_TIMELIMITS = {"day": "d", "week": "w", "month": "m", "year": "y"}


class DuckDuckGoSearchProvider(SearchProvider):
    async def search(self, query: str, *, max_results: int, recency: str | None = None) -> list[SearchResult]:
        return await asyncio.to_thread(self._search_sync, query, max_results, recency)

    def _search_sync(self, query: str, max_results: int, recency: str | None) -> list[SearchResult]:
        try:
            from ddgs import DDGS
        except ImportError as exc:  # pragma: no cover
            raise SearchError("ddgs is not installed. Run `pip install ddgs`.") from exc

        kwargs: dict = {"max_results": max_results}
        if recency in _TIMELIMITS:
            kwargs["timelimit"] = _TIMELIMITS[recency]
        try:
            raw = DDGS().text(query, **kwargs)
        except Exception as exc:  # noqa: BLE001 - ddgs raises several exception types
            logger.warning("DuckDuckGo search failed: %s", exc)
            raise SearchError(f"Search failed: {exc}") from exc

        return [
            SearchResult(
                title=str(item.get("title", "")).strip(),
                url=str(item.get("href") or item.get("url") or ""),
                snippet=str(item.get("body", "")).strip(),
            )
            for item in raw or []
        ]
