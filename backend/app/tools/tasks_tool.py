"""tasks: remember ongoing work, decisions and milestones (PostgreSQL)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.database.postgres import DatabaseUnavailable
from app.memory.coordinator import MemoryCoordinator
from app.memory.tasks import TaskValidationError
from app.tools.base import BaseTool, PermissionLevel, ToolResult


class TasksAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    ADD_NOTE = "add_note"
    GET = "get"
    LIST = "list"
    SEARCH = "search"
    DELETE = "delete"


class TasksInput(BaseModel):
    action: TasksAction = Field(
        ...,
        description=(
            "create a task, update its fields/status, add_note (a note, decision, milestone or step on a task), "
            "get (with history), list (optionally by status/project), search, or delete."
        ),
    )
    task_id: int | None = Field(default=None, ge=1, description="Required for update, add_note, get and delete.")
    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    project: str | None = Field(default=None, max_length=100)
    status: str | None = Field(default=None, description="pending, in_progress, blocked, completed or cancelled.")
    priority: int | None = Field(default=None, ge=1, le=5, description="1 is highest.")
    kind: str = Field(default="note", description="For add_note: note, decision, milestone or step.")
    content: str | None = Field(default=None, max_length=2000, description="Text of the note for add_note.")
    query: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _check(self) -> "TasksInput":
        a = self.action
        if a == TasksAction.CREATE and not (self.title and self.title.strip()):
            raise ValueError("'title' is required to create a task.")
        if a in (TasksAction.UPDATE, TasksAction.ADD_NOTE, TasksAction.GET, TasksAction.DELETE) and self.task_id is None:
            raise ValueError("'task_id' is required for update, add_note, get and delete.")
        if a == TasksAction.ADD_NOTE and not (self.content and self.content.strip()):
            raise ValueError("'content' is required for add_note.")
        return self


class TasksTool(BaseTool):
    name = "tasks"
    description = (
        "Task memory: track the user's ongoing projects and pending tasks, record decisions and milestones, "
        "and look up what was discussed before so earlier work can be continued."
    )
    permission_level = PermissionLevel.HIGH  # highest action; see permission_for
    input_model = TasksInput

    def __init__(self, memory: MemoryCoordinator):
        self._memory = memory

    def permission_for(self, arguments: TasksInput) -> PermissionLevel:
        return PermissionLevel.HIGH if arguments.action == TasksAction.DELETE else PermissionLevel.LOW

    def describe_call(self, arguments: TasksInput) -> str:
        return f"I can permanently delete task number {arguments.task_id}"

    async def execute(self, arguments: TasksInput) -> ToolResult:
        tasks, run, a = self._memory.tasks, self._memory.db.run, arguments
        try:
            if a.action == TasksAction.CREATE:
                task = await run(
                    tasks.create, a.title, description=a.description, project=a.project,
                    priority=a.priority or 3, status=a.status or "pending",
                )
                return ToolResult.ok({"task": task})
            if a.action == TasksAction.UPDATE:
                task = await run(
                    tasks.update, a.task_id, title=a.title, description=a.description, project=a.project,
                    status=a.status, priority=a.priority,
                )
                return ToolResult.ok({"task": task}) if task else self._missing(a.task_id)
            if a.action == TasksAction.ADD_NOTE:
                row = await run(tasks.add_update, a.task_id, a.content, kind=a.kind)
                return ToolResult.ok({"update": row}) if row else self._missing(a.task_id)
            if a.action == TasksAction.GET:
                task = await run(tasks.get, a.task_id)
                return ToolResult.ok({"task": task}) if task else self._missing(a.task_id)
            if a.action == TasksAction.LIST:
                rows = await run(tasks.list, status=a.status, project=a.project)
                return ToolResult.ok({"count": len(rows), "tasks": rows})
            if a.action == TasksAction.SEARCH:
                rows = await run(tasks.search, a.query or "", limit=10)
                return ToolResult.ok({"count": len(rows), "tasks": rows})
            if not await run(tasks.delete, a.task_id):
                return self._missing(a.task_id)
            return ToolResult.ok({"deleted_task_id": a.task_id})
        except TaskValidationError as exc:
            return ToolResult.fail(str(exc))
        except DatabaseUnavailable:
            return ToolResult.fail("Persistent memory is unavailable right now.")

    @staticmethod
    def _missing(task_id: int | None) -> ToolResult:
        return ToolResult.fail(f"There is no task with id {task_id}.")
