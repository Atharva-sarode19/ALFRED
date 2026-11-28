"""
Structured workflow data models (Phase 5).

A `Workflow` is the persisted record of one complex request: its plan (a set of
`WorkflowTask`s linked by explicit dependencies), its status, a safe activity trace
(`WorkflowEvent`s) and the final outcome. The models also own the legal state
transitions so no component can move a task or workflow into an impossible state.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, computed_field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_workflow_id() -> str:
    return uuid.uuid4().hex


class TaskStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class WorkflowStatus(str, Enum):
    CREATED = "created"
    PLANNING = "planning"
    READY = "ready"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


T, W = TaskStatus, WorkflowStatus

TASK_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    T.PENDING: frozenset({T.READY, T.RUNNING, T.BLOCKED, T.CANCELLED}),
    T.READY: frozenset({T.RUNNING, T.PENDING, T.BLOCKED, T.CANCELLED}),
    T.RUNNING: frozenset({T.COMPLETED, T.FAILED, T.RETRYING, T.WAITING_FOR_APPROVAL, T.CANCELLED}),
    T.RETRYING: frozenset({T.RUNNING, T.FAILED, T.CANCELLED}),
    T.WAITING_FOR_APPROVAL: frozenset({T.RUNNING, T.FAILED, T.CANCELLED}),
    T.BLOCKED: frozenset({T.PENDING, T.CANCELLED}),
    # An explicit user-requested retry resets a failed task.
    T.FAILED: frozenset({T.PENDING}),
    T.COMPLETED: frozenset(),
    T.CANCELLED: frozenset(),
}

WORKFLOW_TRANSITIONS: dict[WorkflowStatus, frozenset[WorkflowStatus]] = {
    W.CREATED: frozenset({W.PLANNING, W.READY, W.FAILED, W.CANCELLED}),
    W.PLANNING: frozenset({W.READY, W.FAILED, W.CANCELLED}),
    W.READY: frozenset({W.RUNNING, W.FAILED, W.CANCELLED}),
    W.RUNNING: frozenset({W.WAITING_FOR_APPROVAL, W.COMPLETED, W.FAILED, W.CANCELLED, W.READY}),
    W.WAITING_FOR_APPROVAL: frozenset({W.RUNNING, W.FAILED, W.CANCELLED}),
    # A failed workflow can be resumed on explicit request.
    W.FAILED: frozenset({W.RUNNING}),
    W.COMPLETED: frozenset(),
    W.CANCELLED: frozenset(),
}

TASK_TERMINAL = frozenset({T.COMPLETED, T.FAILED, T.CANCELLED, T.BLOCKED})
TASK_DONE_STATES = frozenset({T.COMPLETED, T.FAILED, T.CANCELLED})
WORKFLOW_TERMINAL = frozenset({W.COMPLETED, W.FAILED, W.CANCELLED})
WORKFLOW_ACTIVE = frozenset({W.CREATED, W.PLANNING, W.READY, W.RUNNING, W.WAITING_FOR_APPROVAL})


class InvalidTransition(ValueError):
    """A task or workflow was asked to move to a state it cannot reach from where it is."""


class PendingApproval(BaseModel):
    """The exact tool call a task is waiting on. Approval applies to this call and nothing else."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    call_id: str
    description: str = ""
    requested_at: datetime = Field(default_factory=utcnow)
    #: None while waiting, then "approved" or "rejected".
    decision: str | None = None


class WorkflowTask(BaseModel):
    id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    dependencies: list[str] = Field(default_factory=list)
    expected_outcome: str = ""
    tools: list[str] = Field(default_factory=list)
    attempts: int = 0
    result_summary: str | None = None
    error: str | None = None
    pending_approval: PendingApproval | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    def transition(self, new: TaskStatus) -> None:
        if new == self.status:
            return
        if new not in TASK_TRANSITIONS[self.status]:
            raise InvalidTransition(f"Task '{self.id}' cannot go from {self.status.value} to {new.value}.")
        self.status = new
        self.updated_at = utcnow()


class WorkflowEvent(BaseModel):
    """One safe, user-visible line of the workflow activity trace (never model reasoning)."""

    seq: int
    at: datetime = Field(default_factory=utcnow)
    kind: str
    message: str
    task_id: str | None = None


class Workflow(BaseModel):
    id: str = Field(default_factory=new_workflow_id)
    request: str
    title: str = ""
    status: WorkflowStatus = WorkflowStatus.CREATED
    conversation_id: str | None = None
    tasks: list[WorkflowTask] = Field(default_factory=list)
    events: list[WorkflowEvent] = Field(default_factory=list)
    failure: str | None = None
    summary: str | None = None
    result: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_tasks(self) -> int:
        return len(self.tasks)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def completed_tasks(self) -> int:
        return sum(t.status == TaskStatus.COMPLETED for t in self.tasks)

    def task(self, task_id: str) -> WorkflowTask | None:
        return next((t for t in self.tasks if t.id == task_id), None)

    def transition(self, new: WorkflowStatus) -> None:
        if new == self.status:
            return
        if new not in WORKFLOW_TRANSITIONS[self.status]:
            raise InvalidTransition(f"Workflow cannot go from {self.status.value} to {new.value}.")
        self.status = new
        self.updated_at = utcnow()
        self.completed_at = self.updated_at if new in WORKFLOW_TERMINAL else None

    def record(self, kind: str, message: str, task_id: str | None = None) -> WorkflowEvent:
        event = WorkflowEvent(seq=len(self.events) + 1, kind=kind, message=message[:300], task_id=task_id)
        self.events.append(event)
        self.updated_at = event.at
        return event

    @property
    def is_terminal(self) -> bool:
        return self.status in WORKFLOW_TERMINAL

    def waiting_tasks(self) -> list[WorkflowTask]:
        return [t for t in self.tasks if t.status == TaskStatus.WAITING_FOR_APPROVAL]


class PlannedTask(BaseModel):
    """One task as proposed by the planner, before it becomes a `WorkflowTask`."""

    id: str
    description: str
    depends_on: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    expected_outcome: str = ""


class Plan(BaseModel):
    title: str = ""
    tasks: list[PlannedTask]
