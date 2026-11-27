"""web_search: current information from the web (snippets, not full pages)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.services.search import SearchError, SearchProvider
from app.tools.base import BaseTool, PermissionLevel, ToolResult


class Recency(str, Enum):
    ANY = "any"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class WebSearchInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=300, description="What to search for.")
    max_results: int | None = Field(default=None, ge=1, le=10, description="How many results (default 5).")
    recency: Recency = Field(
        default=Recency.ANY,
        description="Restrict to results from the last day/week/month/year. Use for 'latest' or 'recent' questions.",
    )


class WebSearchTool(BaseTool):
    name = "web_search"
    description = (
        "Search the web for current information. Returns result titles, URLs and short "
        "snippets. Run several searches with different queries to compare sources."
    )
    permission_level = PermissionLevel.LOW
    input_model = WebSearchInput

    def __init__(self, provider: SearchProvider | None = None, default_max_results: int = 5):
        self._provider = provider
        self._default_max = default_max_results

    def _get_provider(self) -> SearchProvider:
        if self._provider is None:
            from app.services.ddg_search import DuckDuckGoSearchProvider

            self._provider = DuckDuckGoSearchProvider()
        return self._provider

    async def execute(self, arguments: WebSearchInput) -> ToolResult:
        limit = arguments.max_results or self._default_max
        recency = None if arguments.recency == Recency.ANY else arguments.recency.value
        try:
            results = await self._get_provider().search(arguments.query, max_results=limit, recency=recency)
        except SearchError:
            return ToolResult.fail("The web search service is unavailable right now.")

        return ToolResult.ok(
            {
                "query": arguments.query,
                "results": [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in results],
            },
            untrusted=True,
        )
