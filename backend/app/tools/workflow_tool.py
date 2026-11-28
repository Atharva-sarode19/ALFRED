"""workflow: start, inspect, continue or cancel a multi-step workflow (Phase 5)."""

from __future__ import annotations

import asyncio
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.database.postgres import DatabaseUnavailable
from app.tools.base import BaseTool, PermissionLevel, ToolResult
from app.workflow.context import current_session_id
from app.workflow.engine import WorkflowEngine, WorkflowError
from app.workflow.models import TaskStatus, Workflow
from app.workflow.planner import PlanningError
from app.workflow.validation import PlanValidationError


class WorkflowAction(str, Enum):
    START = "start"
    STATUS = "status"
    RESULT = "result"
    RESUME = "resume"
    CANCEL = "cancel"


class WorkflowInput(BaseModel):
    action: WorkflowAction = Field(
        ...,
        description=(
            "start a new workflow for a complex multi-step request, or check its status, fetch its result, "
            "resume an unfinished one, or cancel it."
        ),
    )
    request: str | None = Field(
        default=None, max_length=4000, description="For start: the user's full request, in their own words."
    )
    workflow_id: str | None = Field(
        default=None, max_length=64, description="Which workflow. Omit to use the most recent one in this conversation."
    )
    retry_failed: bool = Field(default=False, description="For resume: also retry tasks that failed. Only when the user asks.")

    @model_validator(mode="after")
    def _check(self) -> "WorkflowInput":
        if self.action == WorkflowAction.START and not (self.request and self.request.strip()):
            raise ValueError("'request' is required to start a workflow.")
        return self


def workflow_view(wf: Workflow, *, with_result: bool = False) -> dict:
    view: dict = {
        "workflow_id": wf.id,
        "title": wf.title,
        "status": wf.status.value,
        "progress": f"{wf.completed_tasks}/{wf.total_tasks} tasks completed",
        "tasks": [
            {"id": t.id, "description": t.description, "status": t.status.value, **({"error": t.error} if t.error else {})}
            for t in wf.tasks
        ],
    }
    waiting = [t.pending_approval.description for t in wf.tasks if t.status == TaskStatus.WAITING_FOR_APPROVAL and t.pending_approval]
    if waiting:
        view["waiting_for_user_approval"] = waiting
        view["note"] = "The user must approve or decline this in the workflow panel; you cannot approve it."
    if wf.failure:
        view["failure"] = wf.failure
    if wf.summary:
        view["summary"] = wf.summary
    if with_result and wf.result:
        view["result"] = wf.result
    return view


class WorkflowTool(BaseTool):
    name = "workflow"
    description = (
        "Plan and run a multi-step workflow: break a complex request into dependent tasks and carry them out "
        "in order with the other tools, tracking progress, retrying transient failures and pausing for the user's "
        "approval when an action needs it. Use 'start' only for requests that genuinely need several dependent steps "
        "(for example research, compare and summarise). Use status, result, resume and cancel for workflows already started."
    )
    permission_level = PermissionLevel.LOW
    input_model = WorkflowInput

    def __init__(self, engine: WorkflowEngine, *, wait_seconds: float = 45):
        self._engine = engine
        self._wait = wait_seconds

    def describe_call(self, arguments: BaseModel) -> str:
        return "I can run a multi-step workflow"

    async def execute(self, arguments: BaseModel) -> ToolResult:
        args = WorkflowInput.model_validate(arguments)
        try:
            return await self._dispatch(args)
        except PlanningError as exc:
            return ToolResult.fail(str(exc))
        except (WorkflowError, PlanValidationError) as exc:
            return ToolResult.fail(str(exc))
        except DatabaseUnavailable:
            return ToolResult.fail("Workflow storage is unavailable right now.")

    async def _dispatch(self, args: WorkflowInput) -> ToolResult:
        session = current_session_id.get()
        if args.action == WorkflowAction.START:
            assert args.request is not None
            wf = await self._engine.create(args.request, conversation_id=session)
            return await self._launch(wf.id)

        wf = await (self._engine.get(args.workflow_id) if args.workflow_id else self._engine.latest_for(session))
        if wf is None:
            return ToolResult.fail("There is no workflow to refer to yet.")
        if args.action == WorkflowAction.STATUS:
            return ToolResult.ok(workflow_view(wf))
        if args.action == WorkflowAction.RESULT:
            return ToolResult.ok(workflow_view(wf, with_result=True), untrusted=bool(wf.result))
        if args.action == WorkflowAction.CANCEL:
            return ToolResult.ok(workflow_view(await self._engine.cancel(wf.id)))
        await self._engine.resume(wf.id, retry_failed=args.retry_failed)
        return await self._launch(wf.id)

    async def _launch(self, workflow_id: str) -> ToolResult:
        """Start the run in the background and wait a bounded time so a quick workflow answers in the same turn."""
        run = self._engine.spawn(workflow_id)
        if self._wait > 0:
            await asyncio.wait([run], timeout=self._wait)
        wf = await self._engine.get(workflow_id)
        data = workflow_view(wf, with_result=True)
        if not run.done() and not wf.is_terminal:
            data["note"] = "Still running in the background; the user can follow progress in the workflow panel."
        return ToolResult.ok(data, untrusted=bool(wf.result))
