"""
POST /api/chat -- the Phase 1 entrypoint into the agent.

Request/response schemas plus the FastAPI route. Dependency wiring
(`get_orchestrator`) constructs a single shared AgentOrchestrator using the
process-wide ToolRegistry and GeminiProvider, and a per-process in-memory
SessionStore for conversation state.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agent.orchestrator import AgentOrchestrator, TraceStep, new_session_id
from app.agent.state import SessionStore
from app.config.settings import ConfigurationError, get_settings
from app.services.gemini import GeminiProvider
from app.services.llm import LLMProvider
from app.tools.registry import ToolRegistry, build_default_registry

logger = logging.getLogger("alfred.api.chat")

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = Field(
        default=None, description="Omit to start a new conversation session."
    )
    auto_approve_confirmations: bool = Field(
        default=False,
        description="If true, MEDIUM-permission tools run without a confirmation round-trip.",
    )


class TraceStepResponse(BaseModel):
    stage: str
    detail: str


class ChatResponse(BaseModel):
    session_id: str
    response: str
    trace: list[TraceStepResponse]
    pending_confirmation: dict | None = None
    iterations_used: int


# ---- process-wide singletons (Phase 1: simple module-level state) --------
_tool_registry: ToolRegistry | None = None
_llm_provider: LLMProvider | None = None
_session_store: SessionStore | None = None


def get_tool_registry() -> ToolRegistry:
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = build_default_registry()
    return _tool_registry


def get_llm_provider() -> LLMProvider:
    global _llm_provider
    if _llm_provider is None:
        _llm_provider = GeminiProvider()
    return _llm_provider


def get_session_store() -> SessionStore:
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store


def get_orchestrator(
    llm: LLMProvider = Depends(get_llm_provider),
    tools: ToolRegistry = Depends(get_tool_registry),
) -> AgentOrchestrator:
    settings = get_settings()
    return AgentOrchestrator(llm, tools, max_iterations=settings.max_agent_iterations)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    sessions: SessionStore = Depends(get_session_store),
) -> ChatResponse:
    session_id = request.session_id or new_session_id()
    state = sessions.get_or_create(session_id)

    try:
        result = await orchestrator.process(
            state,
            request.message,
            auto_approve_confirmations=request.auto_approve_confirmations,
        )
    except ConfigurationError as exc:
        # e.g. GEMINI_API_KEY / GEMINI_MODEL not set -- a setup problem, not a
        # user error. Surface it clearly rather than a generic 500.
        logger.error("Configuration error while handling chat request: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - never leak internals to the client
        logger.exception("Unexpected error while processing chat request")
        raise HTTPException(
            status_code=500,
            detail="ALFRED hit an unexpected internal error processing that request.",
        ) from exc

    return ChatResponse(
        session_id=session_id,
        response=result.response_text,
        trace=[TraceStepResponse(stage=s.stage, detail=s.detail) for s in result.trace],
        pending_confirmation=result.pending_confirmation,
        iterations_used=result.iterations_used,
    )
