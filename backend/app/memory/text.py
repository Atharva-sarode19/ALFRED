"""Small text helpers shared by the memory modules."""

from __future__ import annotations

import hashlib
import re

from app.database.sqlite_store import tokenize

__all__ = ["tokenize", "normalize", "content_hash", "similarity", "to_tsquery", "group", "TOKENS_CTE", "coverage"]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", text.lower())).strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def similarity(a: str, b: str) -> float:
    """Jaccard similarity of the two texts' word sets (0..1)."""
    left, right = set(normalize(a).split()), set(normalize(b).split())
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


_GROUP = re.compile(r"\w+(?: \| \w+)*")


def to_tsquery(tokens: list[str]) -> str | None:
    """
    OR-joined, injection-safe tsquery string (None if empty). Each token is a word or a
    group of alternatives written 'word | other' (see `group`); anything else is dropped.
    """
    parts = [t for t in tokens if _GROUP.fullmatch(t)]
    return " | ".join(parts) if parts else None


def group(*words: str) -> str:
    """One query 'word' that matches any of the given alternatives (counts once for coverage)."""
    return " | ".join(dict.fromkeys(words))


# SQL fragment: the query words that survive Postgres' own stop-word removal (needs `%(tokens)s::text[]`).
TOKENS_CTE = (
    "toks AS (SELECT to_tsquery('english', t) AS q FROM unnest(%(tokens)s::text[]) AS t "
    "WHERE numnode(to_tsquery('english', t)) > 0)"
)


def coverage(vector_column: str) -> str:
    """SQL expression (0..1): the share of query words found in `vector_column`."""
    return (
        f"((SELECT count(*) FROM toks WHERE {vector_column} @@ toks.q)::float8 / "
        "GREATEST((SELECT count(*) FROM toks), 1))"
    )
