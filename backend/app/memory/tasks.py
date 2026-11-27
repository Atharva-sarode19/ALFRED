"""Task memory: ongoing/pending work, decisions and milestones, stored in PostgreSQL."""

from __future__ import annotations

from typing import Any

from app.database.postgres import PostgresManager
from app.memory.text import TOKENS_CTE, coverage, to_tsquery, tokenize

STATUSES = ("pending", "in_progress", "blocked", "completed", "cancelled")
ACTIVE_STATUSES = ("pending", "in_progress", "blocked")
UPDATE_KINDS = ("note", "decision", "milestone", "step")
_TASK_COLUMNS = "id, title, description, project, status, priority, created_at, updated_at, completed_at"


class TaskValidationError(ValueError):
    """Invalid task input."""


class TaskMemoryManager:
    def __init__(self, db: PostgresManager):
        self._db = db

    # ---- create / read ----------------------------------------------------
    def create(
        self, title: str, *, description: str | None = None, project: str | None = None, priority: int = 3,
        status: str = "pending",
    ) -> dict[str, Any]:
        title = " ".join((title or "").split())
        if not title:
            raise TaskValidationError("A task needs a title.")
        self._check(status=status, priority=priority)
        with self._db.transaction() as conn:
            return conn.execute(
                f"INSERT INTO tasks (title, description, project, status, priority, completed_at) "
                f"VALUES (%s, %s, %s, %s, %s, CASE WHEN %s = 'completed' THEN now() END) RETURNING {_TASK_COLUMNS}",
                (title[:300], (description or None), (project or None), status, priority, status),
            ).fetchone()

    def get(self, task_id: int, *, with_updates: bool = True) -> dict[str, Any] | None:
        with self._db.connection() as conn:
            task = conn.execute(f"SELECT {_TASK_COLUMNS} FROM tasks WHERE id = %s", (task_id,)).fetchone()
            if task and with_updates:
                task["updates"] = conn.execute(
                    "SELECT id, kind, content, created_at FROM task_updates WHERE task_id = %s ORDER BY id", (task_id,)
                ).fetchall()
            return task

    def list(
        self, *, status: str | None = None, project: str | None = None, active_only: bool = False, limit: int = 50
    ) -> list[dict[str, Any]]:
        if status:
            self._check(status=status)
        with self._db.connection() as conn:
            return conn.execute(
                f"""
                SELECT {_TASK_COLUMNS} FROM tasks
                WHERE (%(status)s::text IS NULL OR status = %(status)s)
                  AND (%(project)s::text IS NULL OR lower(project) = lower(%(project)s))
                  AND (NOT %(active)s OR status = ANY(%(active_statuses)s))
                ORDER BY priority ASC, updated_at DESC LIMIT %(limit)s
                """,
                {"status": status, "project": project, "active": active_only,
                 "active_statuses": list(ACTIVE_STATUSES), "limit": limit},
            ).fetchall()

    # ---- update / delete ------------------------------------------------------
    def update(self, task_id: int, **changes: Any) -> dict[str, Any] | None:
        allowed = {"title", "description", "project", "status", "priority"}
        fields = {k: v for k, v in changes.items() if k in allowed and v is not None}
        self._check(status=fields.get("status"), priority=fields.get("priority"))
        if "title" in fields and not fields["title"].strip():
            raise TaskValidationError("A task needs a title.")
        with self._db.transaction() as conn:
            if not fields:
                return conn.execute(f"SELECT {_TASK_COLUMNS} FROM tasks WHERE id = %s", (task_id,)).fetchone()
            assignments = ", ".join(f"{name} = %({name})s" for name in fields)
            completed = ""
            if "status" in fields:
                completed = ", completed_at = CASE WHEN %(status)s = 'completed' THEN now() ELSE NULL END"
            return conn.execute(
                f"UPDATE tasks SET {assignments}{completed}, updated_at = now() WHERE id = %(id)s "
                f"RETURNING {_TASK_COLUMNS}",
                {**fields, "id": task_id},
            ).fetchone()

    def add_update(self, task_id: int, content: str, *, kind: str = "note") -> dict[str, Any] | None:
        """Record a note, decision, milestone or step on a task. None if the task does not exist."""
        content = " ".join((content or "").split())
        if not content:
            raise TaskValidationError("An update cannot be empty.")
        if kind not in UPDATE_KINDS:
            raise TaskValidationError(f"Unknown update kind '{kind}'. Use one of {list(UPDATE_KINDS)}.")
        with self._db.transaction() as conn:
            if conn.execute("SELECT 1 FROM tasks WHERE id = %s", (task_id,)).fetchone() is None:
                return None
            row = conn.execute(
                "INSERT INTO task_updates (task_id, kind, content) VALUES (%s, %s, %s) "
                "RETURNING id, task_id, kind, content, created_at",
                (task_id, kind, content),
            ).fetchone()
            conn.execute("UPDATE tasks SET updated_at = now() WHERE id = %s", (task_id,))
            return row

    def delete(self, task_id: int) -> bool:
        with self._db.transaction() as conn:
            return conn.execute("DELETE FROM tasks WHERE id = %s", (task_id,)).rowcount > 0

    # ---- retrieval ----------------------------------------------------------------
    def search(self, query: str | list[str], *, limit: int = 5) -> list[dict[str, Any]]:
        """Tasks whose own text, or any of whose updates, match the query (best first)."""
        tokens = tokenize(query) if isinstance(query, str) else query
        tsquery = to_tsquery(tokens)
        if tsquery is None:
            return []
        with self._db.connection() as conn:
            tasks = conn.execute(
                f"""
                WITH {TOKENS_CTE},
                hits AS (
                    SELECT id AS task_id, {coverage("search_vector")} AS relevance
                    FROM tasks WHERE search_vector @@ to_tsquery('english', %(q)s)
                    UNION ALL
                    SELECT task_id, {coverage("search_vector")}
                    FROM task_updates WHERE search_vector @@ to_tsquery('english', %(q)s)
                )
                SELECT t.id, t.title, t.description, t.project, t.status, t.priority, t.created_at,
                       t.updated_at, t.completed_at, max(h.relevance) AS relevance
                FROM hits h JOIN tasks t ON t.id = h.task_id
                GROUP BY t.id
                ORDER BY max(h.relevance) DESC, (t.status = ANY(%(active)s)) DESC, t.updated_at DESC
                LIMIT %(limit)s
                """,
                {"q": tsquery, "tokens": tokens, "active": list(ACTIVE_STATUSES), "limit": limit},
            ).fetchall()
            self._attach_recent_updates(conn, tasks)
            return tasks

    def recent_active(self, limit: int = 3) -> list[dict[str, Any]]:
        """The most recently touched unfinished tasks, for 'continue where we left off'."""
        with self._db.connection() as conn:
            tasks = conn.execute(
                f"SELECT {_TASK_COLUMNS} FROM tasks WHERE status = ANY(%s) ORDER BY updated_at DESC LIMIT %s",
                (list(ACTIVE_STATUSES), limit),
            ).fetchall()
            self._attach_recent_updates(conn, tasks)
            return tasks

    @staticmethod
    def _attach_recent_updates(conn, tasks: list[dict[str, Any]], per_task: int = 3) -> None:
        for task in tasks:
            rows = conn.execute(
                "SELECT kind, content, created_at FROM task_updates WHERE task_id = %s ORDER BY id DESC LIMIT %s",
                (task["id"], per_task),
            ).fetchall()
            task["recent_updates"] = list(reversed(rows))

    @staticmethod
    def _check(*, status: str | None = None, priority: int | None = None) -> None:
        if status is not None and status not in STATUSES:
            raise TaskValidationError(f"Unknown status '{status}'. Use one of {list(STATUSES)}.")
        if priority is not None and not 1 <= priority <= 5:
            raise TaskValidationError("Priority must be between 1 (highest) and 5.")
