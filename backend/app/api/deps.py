"""Process-wide singletons shared by the API routers (override them in tests)."""

from __future__ import annotations

from app.agent.state import SessionStore
from app.config.settings import get_settings
from app.database.sqlite_store import SQLiteStore
from app.services.gemini import GeminiProvider
from app.services.llm import LLMProvider
from app.tools.registry import ToolRegistry, build_default_registry

_store: SQLiteStore | None = None
_registry: ToolRegistry | None = None
_llm: LLMProvider | None = None
_sessions: SessionStore | None = None


def get_store() -> SQLiteStore:
    global _store
    if _store is None:
        _store = SQLiteStore(get_settings().sqlite_path)
    return _store


def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = build_default_registry(get_settings(), get_store())
    return _registry


def get_llm_provider() -> LLMProvider:
    global _llm
    if _llm is None:
        _llm = GeminiProvider()
    return _llm


def get_session_store() -> SessionStore:
    global _sessions
    if _sessions is None:
        _sessions = SessionStore()
    return _sessions
