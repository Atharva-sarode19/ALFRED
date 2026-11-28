"""
Workflow persistence.

`PostgresWorkflowStore` keeps workflows in the Phase 4 PostgreSQL database (tables added by migration
002). `InMemoryWorkflowStore` is the fallback when PostgreSQL is not configured: workflows then last
for the life of the process. Both have the same async interface and both return independent copies.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from psycopg.types.json import Jsonb

from app.database.postgres import PostgresManager
from app.workflow.models import PendingApproval, Workflow, WorkflowEvent, WorkflowStatus, WorkflowTask


class WorkflowStore(Protocol):
    persistent: bool

    async def save(self, workflow: Workflow) -> None: ...
    async def get(self, workflow_id: str) -> Workflow | None: ...
    async def list(
        self, *, status: str | None = None, conversation_id: str | None = None, limit: int = 20
    ) -> list[Workflow]: ...


class InMemoryWorkflowStore:
    persistent = False

    def __init__(self) -> None:
        self._items: dict[str, Workflow] = {}

    async def save(self, workflow: Workflow) -> None:
        self._items[workflow.id] = workflow.model_copy(deep=True)

    async def get(self, workflow_id: str) -> Workflow | None:
        found = self._items.get(workflow_id)
        return found.model_copy(deep=True) if found else None

    async def list(
        self, *, status: str | None = None, conversation_id: str | None = None, limit: int = 20
    ) -> list[Workflow]:
        items = [
            w
            for w in self._items.values()
            if (status is None or w.status.value == status)
            and (conversation_id is None or w.conversation_id == conversation_id)
        ]
        items.sort(key=lambda w: w.updated_at, reverse=True)
        return [w.model_copy(deep=True) for w in items[:limit]]


_WORKFLOW_COLUMNS = (
    "id, conversation_id, title, request, status, failure, summary, result, created_at, updated_at, completed_at"
)


class PostgresWorkflowStore:
    persistent = True

    def __init__(self, db: PostgresManager, ready: Callable[[], Awaitable[None]] | None = None):
        self._db = db
        self._ready = ready

    async def _prepare(self) -> None:
        if self._ready is not None:
            await self._ready()

    # ---- writes ---------------------------------------------------------------------
    async def save(self, workflow: Workflow) -> None:
        await self._prepare()
        await self._db.run(self._save, workflow.model_copy(deep=True))

    def _save(self, wf: Workflow) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO workflows (id, conversation_id, title, request, status, failure, summary, result,
                                       created_at, updated_at, completed_at)
                VALUES (%(id)s, %(conversation_id)s, %(title)s, %(request)s, %(status)s, %(failure)s,
                        %(summary)s, %(result)s, %(created_at)s, %(updated_at)s, %(completed_at)s)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title, status = EXCLUDED.status, failure = EXCLUDED.failure,
                    summary = EXCLUDED.summary, result = EXCLUDED.result,
                    updated_at = EXCLUDED.updated_at, completed_at = EXCLUDED.completed_at
                """,
                {
                    "id": wf.id, "conversation_id": wf.conversation_id, "title": wf.title, "request": wf.request,
                    "status": wf.status.value, "failure": wf.failure, "summary": wf.summary, "result": wf.result,
                    "created_at": wf.created_at, "updated_at": wf.updated_at, "completed_at": wf.completed_at,
                },
            )
            for position, task in enumerate(wf.tasks):
                conn.execute(
                    """
                    INSERT INTO workflow_tasks (workflow_id, task_id, position, description, status, dependencies,
                        expected_outcome, tools, attempts, result_summary, error, pending_approval,
                        created_at, updated_at)
                    VALUES (%(wid)s, %(tid)s, %(pos)s, %(description)s, %(status)s, %(deps)s, %(expected)s,
                        %(tools)s, %(attempts)s, %(result)s, %(error)s, %(approval)s, %(created_at)s, %(updated_at)s)
                    ON CONFLICT (workflow_id, task_id) DO UPDATE SET
                        status = EXCLUDED.status, attempts = EXCLUDED.attempts,
                        result_summary = EXCLUDED.result_summary, error = EXCLUDED.error,
                        pending_approval = EXCLUDED.pending_approval, updated_at = EXCLUDED.updated_at
                    """,
                    {
                        "wid": wf.id, "tid": task.id, "pos": position, "description": task.description,
                        "status": task.status.value, "deps": Jsonb(task.dependencies),
                        "expected": task.expected_outcome, "tools": Jsonb(task.tools), "attempts": task.attempts,
                        "result": task.result_summary, "error": task.error,
                        "approval": Jsonb(task.pending_approval.model_dump(mode="json")) if task.pending_approval else None,
                        "created_at": task.created_at, "updated_at": task.updated_at,
                    },
                )
            if wf.events:
                conn.cursor().executemany(
                    "INSERT INTO workflow_events (workflow_id, seq, at, kind, task_id, message) "
                    "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (workflow_id, seq) DO NOTHING",
                    [(wf.id, e.seq, e.at, e.kind, e.task_id, e.message) for e in wf.events],
                )

    # ---- reads ----------------------------------------------------------------------
    async def get(self, workflow_id: str) -> Workflow | None:
        await self._prepare()
        return await self._db.run(self._get, workflow_id)

    def _get(self, workflow_id: str) -> Workflow | None:
        with self._db.connection() as conn:
            row = conn.execute(f"SELECT {_WORKFLOW_COLUMNS} FROM workflows WHERE id = %s", (workflow_id,)).fetchone()
            if row is None:
                return None
            return self._assemble(conn, [row], with_events=True)[0]

    async def list(
        self, *, status: str | None = None, conversation_id: str | None = None, limit: int = 20
    ) -> list[Workflow]:
        await self._prepare()
        return await self._db.run(self._list, status, conversation_id, limit)

    def _list(self, status: str | None, conversation_id: str | None, limit: int) -> list[Workflow]:
        with self._db.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT {_WORKFLOW_COLUMNS} FROM workflows
                WHERE (%(status)s::text IS NULL OR status = %(status)s)
                  AND (%(conv)s::text IS NULL OR conversation_id = %(conv)s)
                ORDER BY updated_at DESC LIMIT %(limit)s
                """,
                {"status": status, "conv": conversation_id, "limit": limit},
            ).fetchall()
            return self._assemble(conn, rows, with_events=False)

    @staticmethod
    def _assemble(conn: Any, rows: list[dict[str, Any]], *, with_events: bool) -> list[Workflow]:
        ids = [r["id"] for r in rows]
        tasks_by: dict[str, list[WorkflowTask]] = {i: [] for i in ids}
        events_by: dict[str, list[WorkflowEvent]] = {i: [] for i in ids}
        if ids:
            for t in conn.execute(
                "SELECT * FROM workflow_tasks WHERE workflow_id = ANY(%s) ORDER BY workflow_id, position", (ids,)
            ).fetchall():
                tasks_by[t["workflow_id"]].append(
                    WorkflowTask(
                        id=t["task_id"], description=t["description"], status=t["status"],
                        dependencies=t["dependencies"], expected_outcome=t["expected_outcome"], tools=t["tools"],
                        attempts=t["attempts"], result_summary=t["result_summary"], error=t["error"],
                        pending_approval=PendingApproval.model_validate(t["pending_approval"]) if t["pending_approval"] else None,
                        created_at=t["created_at"], updated_at=t["updated_at"],
                    )
                )
            if with_events:
                for e in conn.execute(
                    "SELECT workflow_id, seq, at, kind, task_id, message FROM workflow_events "
                    "WHERE workflow_id = ANY(%s) ORDER BY workflow_id, seq", (ids,)
                ).fetchall():
                    events_by[e["workflow_id"]].append(
                        WorkflowEvent(seq=e["seq"], at=e["at"], kind=e["kind"], message=e["message"], task_id=e["task_id"])
                    )
        return [
            Workflow(
                id=r["id"], conversation_id=r["conversation_id"], title=r["title"], request=r["request"],
                status=WorkflowStatus(r["status"]), failure=r["failure"], summary=r["summary"], result=r["result"],
                created_at=r["created_at"], updated_at=r["updated_at"], completed_at=r["completed_at"],
                tasks=tasks_by[r["id"]], events=events_by[r["id"]],
            )
            for r in rows
        ]
