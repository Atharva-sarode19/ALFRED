"""Web-search abstraction: the tool depends on this, never on a specific engine."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class SearchError(RuntimeError):
    """The search backend failed or is unavailable."""


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class SearchProvider(ABC):
    @abstractmethod
    async def search(self, query: str, *, max_results: int, recency: str | None = None) -> list[SearchResult]:
        """`recency` is one of 'day' | 'week' | 'month' | 'year' | None."""
        raise NotImplementedError
