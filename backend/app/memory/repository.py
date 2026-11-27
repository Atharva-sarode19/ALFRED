"""
SQL for memories. Every method takes an open connection first, so a service can
group several calls into one transaction (`with db.transaction() as conn:`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import psycopg

from app.memory.text import TOKENS_CTE, coverage, to_tsquery

CATEGORIES = ("preference", "fact", "instruction", "project", "other")
_COLUMNS = (
    "id, category, key, content, importance, status, source, source_conversation_id, superseded_by, "
    "created_at, updated_at, last_accessed_at, access_count, expires_at"
)
_UPDATABLE = {"content", "category", "key", "importance", "status", "expires_at", "content_hash"}


class MemoryRepository:
    def create(
        self,
        conn: psycopg.Connection,
        *,
        content: str,
        content_hash: str,
        category: str = "fact",
        key: str | None = None,
        importance: int = 3,
        source: str = "extracted",
        conversation_id: str | None = None,
        expires_at: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Insert a memory. Returns None if an identical active memory already exists."""
        return conn.execute(
            f"""
            INSERT INTO memories (category, key, content, content_hash, importance, source,
                                  source_conversation_id, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (content_hash) WHERE status = 'active' DO NOTHING
            RETURNING {_COLUMNS}
            """,
            (category, key, content, content_hash, importance, source, conversation_id, expires_at),
        ).fetchone()

    def get(self, conn: psycopg.Connection, memory_id: int) -> dict[str, Any] | None:
        return conn.execute(f"SELECT {_COLUMNS} FROM memories WHERE id = %s", (memory_id,)).fetchone()

    def find_active_by_hash(self, conn: psycopg.Connection, content_hash: str) -> dict[str, Any] | None:
        return conn.execute(
            f"SELECT {_COLUMNS} FROM memories WHERE content_hash = %s AND status = 'active'", (content_hash,)
        ).fetchone()

    def find_active_by_key(self, conn: psycopg.Connection, key: str) -> list[dict[str, Any]]:
        return conn.execute(
            f"SELECT {_COLUMNS} FROM memories WHERE key = %s AND status = 'active' ORDER BY id", (key,)
        ).fetchall()

    def active_in_category(self, conn: psycopg.Connection, category: str, limit: int = 200) -> list[dict[str, Any]]:
        return conn.execute(
            f"SELECT {_COLUMNS} FROM memories WHERE category = %s AND status = 'active' "
            "AND key IS NULL ORDER BY updated_at DESC LIMIT %s",
            (category, limit),
        ).fetchall()

    def list(
        self,
        conn: psycopg.Connection,
        *,
        category: str | None = None,
        status: str | None = "active",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return conn.execute(
            f"""
            SELECT {_COLUMNS} FROM memories
            WHERE (%(category)s::text IS NULL OR category = %(category)s)
              AND (%(status)s::text IS NULL OR status = %(status)s)
            ORDER BY importance DESC, updated_at DESC
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            {"category": category, "status": status, "limit": limit, "offset": offset},
        ).fetchall()

    def search(
        self,
        conn: psycopg.Connection,
        tokens: list[str],
        *,
        categories: list[str] | None = None,
        status: str | None = "active",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Full-text search, best match first. `relevance` is the share of query words found (0..1)."""
        tsquery = to_tsquery(tokens)
        if tsquery is None:
            return []
        return conn.execute(
            f"""
            WITH {TOKENS_CTE}
            SELECT {_COLUMNS}, {coverage("search_vector")} AS relevance
            FROM memories
            WHERE search_vector @@ to_tsquery('english', %(q)s)
              AND (%(status)s::text IS NULL OR status = %(status)s)
              AND (%(categories)s::text[] IS NULL OR category = ANY(%(categories)s))
              AND (expires_at IS NULL OR expires_at > now())
            ORDER BY relevance DESC, importance DESC, ts_rank(search_vector, to_tsquery('english', %(q)s)) DESC,
                     updated_at DESC
            LIMIT %(limit)s
            """,
            {"q": tsquery, "tokens": tokens, "status": status, "categories": categories, "limit": limit},
        ).fetchall()

    def standing_instructions(self, conn: psycopg.Connection, min_importance: int, limit: int) -> list[dict[str, Any]]:
        return conn.execute(
            f"""
            SELECT {_COLUMNS} FROM memories
            WHERE category = 'instruction' AND status = 'active' AND importance >= %s
              AND (expires_at IS NULL OR expires_at > now())
            ORDER BY importance DESC, updated_at DESC LIMIT %s
            """,
            (min_importance, limit),
        ).fetchall()

    def update(self, conn: psycopg.Connection, memory_id: int, **fields: Any) -> dict[str, Any] | None:
        bad = set(fields) - _UPDATABLE
        if bad:
            raise ValueError(f"Cannot update fields: {sorted(bad)}")
        if not fields:
            return self.get(conn, memory_id)
        assignments = ", ".join(f"{name} = %({name})s" for name in fields)
        return conn.execute(
            f"UPDATE memories SET {assignments}, updated_at = now() WHERE id = %(id)s RETURNING {_COLUMNS}",
            {**fields, "id": memory_id},
        ).fetchone()

    def archive_by_key(self, conn: psycopg.Connection, key: str) -> int:
        return conn.execute(
            "UPDATE memories SET status = 'archived', updated_at = now() WHERE key = %s AND status = 'active'", (key,)
        ).rowcount

    def archive(self, conn: psycopg.Connection, memory_id: int, superseded_by: int | None = None) -> None:
        conn.execute(
            "UPDATE memories SET status = 'archived', superseded_by = %s, updated_at = now() WHERE id = %s",
            (superseded_by, memory_id),
        )

    def delete(self, conn: psycopg.Connection, memory_id: int) -> bool:
        return conn.execute("DELETE FROM memories WHERE id = %s", (memory_id,)).rowcount > 0

    def touch(self, conn: psycopg.Connection, memory_ids: list[int]) -> None:
        if memory_ids:
            conn.execute(
                "UPDATE memories SET last_accessed_at = now(), access_count = access_count + 1 WHERE id = ANY(%s)",
                (memory_ids,),
            )

    def archive_expired(self, conn: psycopg.Connection) -> int:
        return conn.execute(
            "UPDATE memories SET status = 'archived', updated_at = now() "
            "WHERE status = 'active' AND expires_at IS NOT NULL AND expires_at <= now()"
        ).rowcount

    def archive_stale(self, conn: psycopg.Connection, older_than_days: int, max_importance: int = 2) -> int:
        return conn.execute(
            """
            UPDATE memories SET status = 'archived', updated_at = now()
            WHERE status = 'active' AND importance <= %s
              AND coalesce(last_accessed_at, updated_at) < now() - make_interval(days => %s)
            """,
            (max_importance, older_than_days),
        ).rowcount

    def counts(self, conn: psycopg.Connection) -> dict[str, int]:
        rows = conn.execute("SELECT status, count(*) AS n FROM memories GROUP BY status").fetchall()
        return {row["status"]: row["n"] for row in rows}
