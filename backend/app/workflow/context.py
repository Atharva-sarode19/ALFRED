"""The conversation session a tool call is running for (set by the orchestrator, read by the workflow tool)."""

from __future__ import annotations

from contextvars import ContextVar

current_session_id: ContextVar[str | None] = ContextVar("alfred_current_session_id", default=None)
