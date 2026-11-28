"""
POST /api/chat          -- one user turn through the agent.
POST /api/chat/confirm  -- approve or decline the action the agent is waiting on.
POST /api/chat/cancel   -- drop that action without running it or calling the model.

Confirmation is server-side state: the client can only say yes or no to the
exact call the server is holding. It cannot pre-approve anything.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agent.orchestrator import AgentOrchestrator, AgentRunResult, NoPendingActionError, new_session_id
from app.agent.state import SessionStore
from app.api.deps import get_llm_provider, get_memory, get_session_store, get_tool_registry, get_workflow_engine
from app.config.settings import ConfigurationError, get_settings
from app.memory.coordinator import MemoryCoordinator
from app.services.llm import LLMProvider
from app.tools.registry import ToolRegistry
from app.workflow.engine import WorkflowEngine

logger = logging.getLogger("alfred.api.chat")

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, description="Omit to start a new conversation session.")


class ConfirmRequest(BaseModel):
    session_id: str
    approve: bool


class CancelRequest(BaseModel):
    session_id: str


class CancelResponse(BaseModel):
    cancelled: bool


class TraceStepResponse(BaseModel):
    stage: str
    detail: str
    duration_ms: int | None = None


class ChatResponse(BaseModel):
    session_id: str
    response: str
    trace: list[TraceStepResponse]
    pending_confirmation: dict | None = None
    iterations_used: int


def get_orchestrator(
    llm: LLMProvider = Depends(get_llm_provider),
    tools: ToolRegistry = Depends(get_tool_registry),
    memory: MemoryCoordinator | None = Depends(get_memory),
    workflows: WorkflowEngine = Depends(get_workflow_engine),
) -> AgentOrchestrator:
    settings = get_settings()

    async def workflow_context(session_id: str) -> str | None:
        try:
            return await workflows.context_block(session_id)
        except Exception:  # noqa: BLE001 - workflow context is optional; chat must never fail because of it
            logger.warning("Could not load workflow context", exc_info=True)
            return None

    return AgentOrchestrator(
        llm,
        tools,
        max_iterations=settings.max_agent_iterations,
        confirm_medium=settings.require_medium_confirmation,
        default_timezone=settings.default_timezone,
        memory=memory,
        workflow_context=workflow_context,
    )


def _to_response(session_id: str, result: AgentRunResult) -> ChatResponse:
    return ChatResponse(
        session_id=session_id,
        response=result.response_text,
        trace=[TraceStepResponse(stage=s.stage, detail=s.detail, duration_ms=s.duration_ms) for s in result.trace],
        pending_confirmation=result.pending_confirmation,
        iterations_used=result.iterations_used,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    sessions: SessionStore = Depends(get_session_store),
) -> ChatResponse:
    session_id = request.session_id or new_session_id()
    state = sessions.get_or_create(session_id)
    try:
        result = await orchestrator.process(state, request.message)
    except ConfigurationError as exc:
        logger.error("Configuration error while handling chat request: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - never leak internals to the client
        logger.exception("Unexpected error while processing chat request")
        raise HTTPException(
            status_code=500, detail="ALFRED hit an unexpected internal error processing that request."
        ) from exc
    return _to_response(session_id, result)


@router.post("/chat/confirm", response_model=ChatResponse)
async def confirm(
    request: ConfirmRequest,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    sessions: SessionStore = Depends(get_session_store),
) -> ChatResponse:
    state = sessions.get(request.session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Unknown session.")
    try:
        result = await orchestrator.resume(state, request.approve)
    except NoPendingActionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error while resuming after confirmation")
        raise HTTPException(
            status_code=500, detail="ALFRED hit an unexpected internal error processing that request."
        ) from exc
    return _to_response(request.session_id, result)


@router.post("/chat/cancel", response_model=CancelResponse)
async def cancel(
    request: CancelRequest,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    sessions: SessionStore = Depends(get_session_store),
) -> CancelResponse:
    """Drop the action waiting for confirmation (silently: nothing runs, no model call)."""
    state = sessions.get(request.session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Unknown session.")
    return CancelResponse(cancelled=orchestrator.cancel_pending(state))
