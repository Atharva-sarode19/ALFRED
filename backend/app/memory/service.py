"""
MemoryService: controlled create/read/update/delete/search of long-term memories.

Rules it enforces:
  * identical memories are never stored twice (hash + near-duplicate check);
  * a new memory with the same `key` as an active one replaces it -- the old row
    is archived and points at its replacement, so contradictions update instead of piling up;
  * every write is one transaction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.database.postgres import PostgresManager
from app.memory.repository import CATEGORIES, MemoryRepository
from app.memory.text import content_hash, similarity, tokenize

logger = logging.getLogger("alfred.memory")

NEAR_DUPLICATE_THRESHOLD = 0.8
_MAX_CONTENT_CHARS = 1000


class MemoryValidationError(ValueError):
    """Invalid memory input."""


@dataclass
class SaveResult:
    action: str  # created | updated | duplicate
    memory: dict[str, Any]
    replaced: dict[str, Any] | None = None


def _clean(content: str, category: str, importance: int) -> tuple[str, str, int]:
    content = " ".join((content or "").split())
    if not content:
        raise MemoryValidationError("Memory content cannot be empty.")
    if len(content) > _MAX_CONTENT_CHARS:
        raise MemoryValidationError(f"Memory content is too long (max {_MAX_CONTENT_CHARS} characters).")
    if category not in CATEGORIES:
        raise MemoryValidationError(f"Unknown category '{category}'. Use one of {list(CATEGORIES)}.")
    if not 1 <= importance <= 5:
        raise MemoryValidationError("Importance must be between 1 and 5.")
    return content, category, importance


class MemoryService:
    def __init__(self, db: PostgresManager, repository: MemoryRepository | None = None):
        self._db = db
        self._repo = repository or MemoryRepository()

    # ---- create / update-on-contradiction ---------------------------------
    def remember(
        self,
        content: str,
        *,
        category: str = "fact",
        key: str | None = None,
        importance: int = 3,
        source: str = "extracted",
        conversation_id: str | None = None,
        expires_at: datetime | None = None,
    ) -> SaveResult:
        content, category, importance = _clean(content, category, importance)
        key = (key or "").strip().lower() or None
        digest = content_hash(content)
        repo = self._repo

        with self._db.transaction() as conn:
            same = repo.find_active_by_hash(conn, digest)
            if same:
                return self._duplicate(conn, same, importance)

            replaced: list[dict[str, Any]] = []
            if key:
                replaced = repo.find_active_by_key(conn, key)
            else:
                for existing in repo.active_in_category(conn, category):
                    if similarity(existing["content"], content) >= NEAR_DUPLICATE_THRESHOLD:
                        return self._duplicate(conn, existing, importance)

            created = repo.create(
                conn,
                content=content,
                content_hash=digest,
                category=category,
                key=key,
                importance=importance,
                source=source,
                conversation_id=conversation_id,
                expires_at=expires_at,
            )
            if created is None:  # lost a race with an identical concurrent insert
                same = repo.find_active_by_hash(conn, digest)
                return self._duplicate(conn, same, importance)  # type: ignore[arg-type]
            for old in replaced:
                repo.archive(conn, old["id"], superseded_by=created["id"])
            return SaveResult("updated" if replaced else "created", created, replaced[0] if replaced else None)

    def _duplicate(self, conn, existing: dict[str, Any], importance: int) -> SaveResult:
        bumped = self._repo.update(conn, existing["id"], importance=max(existing["importance"], importance))
        return SaveResult("duplicate", bumped or existing)

    # ---- read / update / delete ---------------------------------------------
    def get(self, memory_id: int) -> dict[str, Any] | None:
        with self._db.connection() as conn:
            return self._repo.get(conn, memory_id)

    def list(self, *, category: str | None = None, status: str | None = "active", limit: int = 50, offset: int = 0):
        with self._db.connection() as conn:
            return self._repo.list(conn, category=category, status=status, limit=limit, offset=offset)

    def update(self, memory_id: int, **changes: Any) -> dict[str, Any] | None:
        """Edit content/category/importance/key/status/expires_at. None if the id is unknown."""
        fields = {k: v for k, v in changes.items() if v is not None or k in ("key", "expires_at")}
        with self._db.transaction() as conn:
            current = self._repo.get(conn, memory_id)
            if current is None:
                return None
            if "status" in fields and fields["status"] not in ("active", "archived"):
                raise MemoryValidationError("Status must be 'active' or 'archived'.")
            content = fields.get("content", current["content"])
            content, category, importance = _clean(
                content, fields.get("category", current["category"]), fields.get("importance", current["importance"])
            )
            fields.update(content=content, category=category, importance=importance, content_hash=content_hash(content))
            if "key" in fields and fields["key"]:
                fields["key"] = fields["key"].strip().lower()
            if fields["content_hash"] != content_hash(current["content"]) or fields.get("status") == "active":
                clash = self._repo.find_active_by_hash(conn, fields["content_hash"])
                if clash and clash["id"] != memory_id:
                    raise MemoryValidationError("An identical active memory already exists.")
            return self._repo.update(conn, memory_id, **fields)

    def delete(self, memory_id: int) -> bool:
        with self._db.transaction() as conn:
            return self._repo.delete(conn, memory_id)

    # ---- search ---------------------------------------------------------------
    def search(self, query: str | list[str], *, categories: list[str] | None = None, limit: int = 10, touch: bool = False):
        """`query` is free text, or a ready list of query words/groups (see `text.group`)."""
        tokens = tokenize(query) if isinstance(query, str) else query
        with self._db.transaction() as conn:
            rows = self._repo.search(conn, tokens, categories=categories, limit=limit)
            if touch:
                self._repo.touch(conn, [row["id"] for row in rows])
            return rows

    def retract(self, key: str) -> int:
        """Archive the active memories filed under a slot the user said no longer applies."""
        with self._db.transaction() as conn:
            return self._repo.archive_by_key(conn, key)

    def standing_instructions(self, min_importance: int = 4, limit: int = 3):
        with self._db.connection() as conn:
            return self._repo.standing_instructions(conn, min_importance, limit)

    def touch(self, memory_ids: list[int]) -> None:
        with self._db.transaction() as conn:
            self._repo.touch(conn, memory_ids)

    # ---- maintenance ------------------------------------------------------------
    def run_maintenance(self, archive_after_days: int) -> dict[str, int]:
        """Archive expired memories and long-unused, low-importance ones."""
        with self._db.transaction() as conn:
            expired = self._repo.archive_expired(conn)
            stale = self._repo.archive_stale(conn, archive_after_days)
        return {"expired": expired, "stale": stale}

    def counts(self) -> dict[str, int]:
        with self._db.connection() as conn:
            return self._repo.counts(conn)
