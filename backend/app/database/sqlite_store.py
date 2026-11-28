"""
SQLite persistence for Phase 3 (notes, reminders, uploaded files + search).

Deliberately free of Pydantic/FastAPI so it is easy to test and easy to
replace: Phase 4 swaps this for a PostgreSQL implementation with the same
method names. Every method is synchronous; callers use `await store.run(...)`
to keep the event loop free.

Use a real file path -- each call opens its own short-lived connection, so
`:memory:` databases are not supported.
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "find", "for", "from", "get",
    "give", "have", "how", "i", "in", "is", "it", "me", "my", "of", "on", "or", "please",
    "show", "that", "the", "this", "to", "was", "what", "which", "with", "file", "document",
}
_SNIPPET_CHARS = 500


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def tokenize(query: str | None, *, drop_stopwords: bool = True, limit: int = 12) -> list[str]:
    tokens = re.findall(r"\w+", (query or "").lower())
    if drop_stopwords:
        tokens = [t for t in tokens if t not in _STOPWORDS]
    seen: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.append(token)
    return seen[:limit]


def _like(token: str) -> str:
    escaped = token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class SQLiteStore:
    def __init__(self, path: str | Path):
        self._path = str(path)
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._fts = False
        self._init_schema()

    # ---- plumbing -----------------------------------------------------
    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    async def run(self, fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
        """Run a store method in a worker thread."""
        return await asyncio.to_thread(fn, *args, **kwargs)

    @property
    def has_full_text_search(self) -> bool:
        return self._fts

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    notes TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(due_at);
                CREATE TABLE IF NOT EXISTS files (
                    id TEXT PRIMARY KEY,
                    original_name TEXT NOT NULL,
                    stored_name TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    char_count INTEGER NOT NULL,
                    text_content TEXT NOT NULL,
                    uploaded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS file_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chunks_file ON file_chunks(file_id);
                """
            )
            try:
                conn.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5("
                    "text, file_id UNINDEXED, chunk_index UNINDEXED)"
                )
                self._fts = True
            except sqlite3.OperationalError:
                self._fts = False

    # ---- notes ----------------------------------------------------------
    def create_note(self, title: str, content: str) -> dict[str, Any]:
        now = utc_now_iso()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO notes(title, content, created_at, updated_at) VALUES (?,?,?,?)",
                (title, content, now, now),
            )
            note_id = cur.lastrowid
        return {"id": note_id, "title": title, "content": content, "created_at": now, "updated_at": now}

    def get_note(self, note_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
        return dict(row) if row else None

    def search_notes(self, query: str | None, limit: int = 10) -> list[dict[str, Any]]:
        tokens = tokenize(query, drop_stopwords=False)
        sql = "SELECT * FROM notes"
        params: list[Any] = []
        if tokens:
            clauses = ["(lower(title) LIKE ? ESCAPE '\\' OR lower(content) LIKE ? ESCAPE '\\')"] * len(tokens)
            sql += " WHERE " + " AND ".join(clauses)
            for token in tokens:
                params.extend([_like(token), _like(token)])
        sql += " ORDER BY updated_at DESC, id DESC LIMIT ?"
        params.append(limit)
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def delete_note(self, note_id: int) -> bool:
        with self._conn() as conn:
            return conn.execute("DELETE FROM notes WHERE id=?", (note_id,)).rowcount > 0

    # ---- reminders --------------------------------------------------
    def create_reminder(self, title: str, due_at_utc: str, notes: str | None) -> dict[str, Any]:
        now = utc_now_iso()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO reminders(title, due_at, notes, created_at) VALUES (?,?,?,?)",
                (title, due_at_utc, notes, now),
            )
            reminder_id = cur.lastrowid
        return {"id": reminder_id, "title": title, "due_at": due_at_utc, "notes": notes, "created_at": now}

    def list_reminders(self, scope: str, now_utc: str, limit: int = 50) -> list[dict[str, Any]]:
        if scope == "upcoming":
            where, order, params = "WHERE due_at >= ?", "ASC", [now_utc]
        elif scope == "past":
            where, order, params = "WHERE due_at < ?", "DESC", [now_utc]
        else:
            where, order, params = "", "ASC", []
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM reminders {where} ORDER BY due_at {order}, id {order} LIMIT ?",
                [*params, limit],
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_reminder(self, reminder_id: int) -> bool:
        with self._conn() as conn:
            return conn.execute("DELETE FROM reminders WHERE id=?", (reminder_id,)).rowcount > 0

    # ---- files ----------------------------------------------------------
    def add_file(
        self,
        file_id: str,
        original_name: str,
        stored_name: str,
        media_type: str,
        size_bytes: int,
        text: str,
        chunks: list[str],
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO files(id, original_name, stored_name, media_type, size_bytes,"
                " char_count, text_content, uploaded_at) VALUES (?,?,?,?,?,?,?,?)",
                (file_id, original_name, stored_name, media_type, size_bytes, len(text), text, now),
            )
            for index, chunk in enumerate(chunks):
                conn.execute(
                    "INSERT INTO file_chunks(file_id, chunk_index, text) VALUES (?,?,?)",
                    (file_id, index, chunk),
                )
                if self._fts:
                    conn.execute(
                        "INSERT INTO chunk_fts(text, file_id, chunk_index) VALUES (?,?,?)",
                        (chunk, file_id, index),
                    )
        return self._public_file(
            {"id": file_id, "original_name": original_name, "media_type": media_type,
             "size_bytes": size_bytes, "char_count": len(text), "uploaded_at": now}
        )

    @staticmethod
    def _public_file(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["original_name"],
            "media_type": row["media_type"],
            "size_bytes": row["size_bytes"],
            "char_count": row["char_count"],
            "uploaded_at": row["uploaded_at"],
        }

    def list_files(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, original_name, media_type, size_bytes, char_count, uploaded_at"
                " FROM files ORDER BY uploaded_at DESC, rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._public_file(dict(r)) for r in rows]

    def get_file(self, file_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, original_name, media_type, size_bytes, char_count, uploaded_at"
                " FROM files WHERE id=?",
                (file_id,),
            ).fetchone()
        return self._public_file(dict(row)) if row else None

    def get_stored_name(self, file_id: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute("SELECT stored_name FROM files WHERE id=?", (file_id,)).fetchone()
        return row["stored_name"] if row else None

    def delete_file(self, file_id: str) -> bool:
        """Remove a document, its chunks and its search-index rows. False if it does not exist."""
        with self._conn() as conn:
            if conn.execute("SELECT 1 FROM files WHERE id=?", (file_id,)).fetchone() is None:
                return False
            if self._fts:
                conn.execute("DELETE FROM chunk_fts WHERE file_id=?", (file_id,))
            conn.execute("DELETE FROM file_chunks WHERE file_id=?", (file_id,))
            conn.execute("DELETE FROM files WHERE id=?", (file_id,))
        return True

    def read_file_text(self, file_id: str, offset: int, length: int) -> str | None:
        """Return `length` characters starting at `offset` (None if the file is unknown)."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT substr(text_content, ?, ?) AS piece FROM files WHERE id=?",
                (offset + 1, length, file_id),
            ).fetchone()
        return None if row is None else row["piece"]

    def _matching_chunks(
        self, conn: sqlite3.Connection, tokens: list[str], file_id: str | None, limit: int
    ) -> list[tuple[str, int, str, float]]:
        """Return (file_id, chunk_index, text, rank) best-first; lower rank is better."""
        if not tokens:
            return []
        if self._fts:
            match = " OR ".join(f'"{t}"' for t in tokens)
            sql = "SELECT file_id, chunk_index, text, bm25(chunk_fts) AS score FROM chunk_fts WHERE chunk_fts MATCH ?"
            params: list[Any] = [match]
            if file_id:
                sql += " AND file_id = ?"
                params.append(file_id)
            sql += " ORDER BY score LIMIT ?"
            params.append(limit)
            return [(r["file_id"], int(r["chunk_index"]), r["text"], float(r["score"]))
                    for r in conn.execute(sql, params).fetchall()]

        # Fallback without FTS5: score by how many tokens a chunk contains.
        sql = "SELECT file_id, chunk_index, text FROM file_chunks"
        params = []
        clauses = ["lower(text) LIKE ? ESCAPE '\\'" for _ in tokens]
        sql += " WHERE (" + " OR ".join(clauses) + ")"
        params.extend(_like(t) for t in tokens)
        if file_id:
            sql += " AND file_id = ?"
            params.append(file_id)
        scored = []
        for r in conn.execute(sql, params).fetchall():
            lowered = r["text"].lower()
            hits = sum(1 for t in tokens if t in lowered)
            scored.append((r["file_id"], int(r["chunk_index"]), r["text"], -float(hits)))
        scored.sort(key=lambda item: item[3])
        return scored[:limit]

    def search_chunks_in_file(self, file_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        tokens = tokenize(query)
        with self._conn() as conn:
            found = self._matching_chunks(conn, tokens, file_id, limit)
        return [{"chunk_index": idx, "text": text} for _, idx, text, _ in found]

    def search_files(self, query: str | None, limit: int = 5) -> list[dict[str, Any]]:
        """Find files by name and content. Blank queries list the newest files."""
        tokens = tokenize(query)
        if not tokens:
            return [{**f, "name_match": False, "snippets": []} for f in self.list_files(limit)]

        with self._conn() as conn:
            name_hits: dict[str, int] = {}
            clauses = " OR ".join("lower(original_name) LIKE ? ESCAPE '\\'" for _ in tokens)
            for r in conn.execute(
                f"SELECT id, lower(original_name) AS n FROM files WHERE {clauses}",
                [_like(t) for t in tokens],
            ).fetchall():
                name_hits[r["id"]] = sum(1 for t in tokens if t in r["n"])

            content: dict[str, dict[str, Any]] = {}
            for fid, _idx, text, rank in self._matching_chunks(conn, tokens, None, 60):
                entry = content.setdefault(fid, {"best": rank, "snippets": []})
                entry["best"] = min(entry["best"], rank)
                if len(entry["snippets"]) < 2:
                    entry["snippets"].append(text[:_SNIPPET_CHARS])

            ids = list({*name_hits, *content})
            if not ids:
                return []
            placeholders = ",".join("?" for _ in ids)
            metas = {
                r["id"]: dict(r)
                for r in conn.execute(
                    "SELECT id, original_name, media_type, size_bytes, char_count, uploaded_at"
                    f" FROM files WHERE id IN ({placeholders})",
                    ids,
                ).fetchall()
            }

        def sort_key(fid: str) -> tuple[int, float]:
            return (-name_hits.get(fid, 0), content[fid]["best"] if fid in content else float("inf"))

        results = []
        for fid in sorted(ids, key=sort_key)[:limit]:
            results.append(
                {
                    **self._public_file(metas[fid]),
                    "name_match": fid in name_hits,
                    "snippets": content.get(fid, {}).get("snippets", []),
                }
            )
        return results
