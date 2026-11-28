"""
Workflow API (Phase 5).

POST /api/workflows                       -- plan a request and start a workflow
GET  /api/workflows                       -- recent workflows (with tasks, without the event trace)
GET  /api/workflows/{id}                  -- one workflow with tasks and its activity trace
GET  /api/workflows/{id}/tasks            -- its tasks
POST /api/workflows/{id}/approve|reject   -- answer the action a task is waiting on
POST /api/workflows/{id}/resume|cancel    -- continue an unfinished workflow / stop one

Runs happen in the background by default; `wait: true` runs to the next stopping point before replying.
Approval is server-side state: the client can only say yes or no to the exact call the server is holding
(optionally echoing its `call_id`), never supply a call of its own.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field

from app.api.deps import get_workflow_engine
from app.config.settings import ConfigurationError
from app.database.postgres import DatabaseUnavailable
from app.workflow.engine import WorkflowEngine, WorkflowError, WorkflowNotFound, WorkflowStateError
from app.workflow.models import Workflow, WorkflowStatus, WorkflowTask
from app.workflow.planner import PlanningError
from app.workflow.validation import PlanValidationError

logger = logging.getLogger("alfred.api.workflows")

router = APIRouter(prefix="/api/workflows", tags=["workflows"])

WorkflowId = Path(..., pattern=r"^[0-9a-f]{32}$", description="Workflow id.")
T = TypeVar("T")


class CreateWorkflowRequest(BaseModel):
    request: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, description="Conversation to associate the workflow with.")
    wait: bool = Field(default=False, description="Run to the next stopping point before responding.")


class ResumeWorkflowRequest(BaseModel):
    retry_failed: bool = Field(default=False, description="Also retry failed tasks (an explicit choice).")
    wait: bool = False


class ApprovalRequest(BaseModel):
    task_id: str | None = Field(default=None, max_length=40)
    call_id: str | None = Field(default=None, max_length=200, description="The call_id shown with the pending action.")
    wait: bool = False


async def _guard(action: Awaitable[T]) -> T:
    try:
        return await action
    except WorkflowNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WorkflowStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PlanningError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (PlanValidationError, WorkflowError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (HTTPException, DatabaseUnavailable):
        raise
    except Exception as exc:  # noqa: BLE001 - never leak internals to the client
        logger.exception("Unexpected error in workflow API")
        raise HTTPException(status_code=500, detail="ALFRED hit an unexpected internal error processing that request.") from exc


async def _launch(engine: WorkflowEngine, workflow_id: str, wait: bool) -> Workflow:
    if wait:
        return await engine.run(workflow_id)
    engine.spawn(workflow_id)
    await asyncio.sleep(0)
    return await engine.get(workflow_id)


@router.post("", response_model=Workflow, status_code=201)
async def create_workflow(
    payload: CreateWorkflowRequest, engine: WorkflowEngine = Depends(get_workflow_engine)
) -> Workflow:
    async def go() -> Workflow:
        wf = await engine.create(payload.request, conversation_id=payload.session_id)
        return await _launch(engine, wf.id, payload.wait)

    return await _guard(go())


@router.get("", response_model=list[Workflow], response_model_exclude={"__all__": {"events"}})
async def list_workflows(
    status: WorkflowStatus | None = Query(default=None),
    session_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    engine: WorkflowEngine = Depends(get_workflow_engine),
) -> list[Workflow]:
    return await _guard(
        engine.list(status=status.value if status else None, conversation_id=session_id, limit=limit)
    )


@router.get("/{workflow_id}", response_model=Workflow)
async def get_workflow(workflow_id: str = WorkflowId, engine: WorkflowEngine = Depends(get_workflow_engine)) -> Workflow:
    return await _guard(engine.get(workflow_id))


@router.get("/{workflow_id}/tasks", response_model=list[WorkflowTask])
async def get_workflow_tasks(
    workflow_id: str = WorkflowId, engine: WorkflowEngine = Depends(get_workflow_engine)
) -> list[WorkflowTask]:
    async def go() -> list[WorkflowTask]:
        return (await engine.get(workflow_id)).tasks

    return await _guard(go())


def _act(
    engine: WorkflowEngine, workflow_id: str, prepare: Callable[[], Awaitable[Workflow]], wait: bool
) -> Awaitable[Workflow]:
    async def go() -> Workflow:
        await prepare()
        return await _launch(engine, workflow_id, wait)

    return _guard(go())


@router.post("/{workflow_id}/resume", response_model=Workflow)
async def resume_workflow(
    workflow_id: str = WorkflowId,
    payload: ResumeWorkflowRequest = Body(default_factory=ResumeWorkflowRequest),
    engine: WorkflowEngine = Depends(get_workflow_engine),
) -> Workflow:
    return await _act(engine, workflow_id, lambda: engine.resume(workflow_id, retry_failed=payload.retry_failed), payload.wait)


@router.post("/{workflow_id}/approve", response_model=Workflow)
async def approve_workflow(
    workflow_id: str = WorkflowId,
    payload: ApprovalRequest = Body(default_factory=ApprovalRequest),
    engine: WorkflowEngine = Depends(get_workflow_engine),
) -> Workflow:
    return await _act(
        engine, workflow_id, lambda: engine.approve(workflow_id, task_id=payload.task_id, call_id=payload.call_id), payload.wait
    )


@router.post("/{workflow_id}/reject", response_model=Workflow)
async def reject_workflow(
    workflow_id: str = WorkflowId,
    payload: ApprovalRequest = Body(default_factory=ApprovalRequest),
    engine: WorkflowEngine = Depends(get_workflow_engine),
) -> Workflow:
    return await _act(
        engine, workflow_id, lambda: engine.reject(workflow_id, task_id=payload.task_id, call_id=payload.call_id), payload.wait
    )


@router.post("/{workflow_id}/cancel", response_model=Workflow)
async def cancel_workflow(workflow_id: str = WorkflowId, engine: WorkflowEngine = Depends(get_workflow_engine)) -> Workflow:
    return await _guard(engine.cancel(workflow_id))
