"""Process-wide singletons shared by the API routers (override them in tests)."""

from __future__ import annotations

from app.agent.state import SessionStore
from app.memory.coordinator import MemoryCoordinator, build_memory_coordinator
from app.config.settings import get_settings
from app.database.sqlite_store import SQLiteStore
from app.services.gemini import GeminiProvider
from app.services.llm import LLMProvider
from app.tools.registry import ToolRegistry, build_default_registry
from app.workflow.engine import EngineConfig, WorkflowEngine
from app.workflow.store import InMemoryWorkflowStore, PostgresWorkflowStore

_store: SQLiteStore | None = None
_registry: ToolRegistry | None = None
_llm: LLMProvider | None = None
_sessions: SessionStore | None = None
_memory: MemoryCoordinator | None = None
_memory_built = False
_engine: WorkflowEngine | None = None


def get_store() -> SQLiteStore:
    global _store
    if _store is None:
        _store = SQLiteStore(get_settings().sqlite_path)
    return _store


def get_memory() -> MemoryCoordinator | None:
    """The PostgreSQL memory system, or None when memory is disabled/unconfigured."""
    global _memory, _memory_built
    if not _memory_built:
        _memory = build_memory_coordinator(get_settings(), get_llm_provider())
        _memory_built = True
    return _memory


def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = build_default_registry(get_settings(), get_store(), get_memory())
        get_workflow_engine()  # registers the `workflow` tool on this registry
    return _registry


def get_workflow_engine() -> WorkflowEngine:
    """The Phase 5 workflow engine; stores workflows in PostgreSQL when memory is configured, else in memory."""
    global _engine
    registry = get_tool_registry()
    if _engine is None:
        from app.tools.workflow_tool import WorkflowTool

        settings = get_settings()
        memory = get_memory()
        store = PostgresWorkflowStore(memory.db, memory.ready) if memory is not None else InMemoryWorkflowStore()
        _engine = WorkflowEngine(
            get_llm_provider(),
            registry,
            store,
            EngineConfig(
                max_tasks=settings.max_workflow_tasks,
                max_task_retries=settings.max_task_retries,
                max_iterations=settings.max_agent_iterations,
                confirm_medium=settings.require_medium_confirmation,
                timezone=settings.default_timezone,
                timeout_seconds=settings.workflow_execution_timeout,
                concurrency=settings.workflow_concurrency,
                retry_delay=settings.workflow_retry_delay,
            ),
        )
        if not registry.is_allowed("workflow"):
            registry.register(WorkflowTool(_engine, wait_seconds=settings.workflow_tool_wait))
    return _engine


def get_llm_provider() -> LLMProvider:
    global _llm
    if _llm is None:
        _llm = GeminiProvider()
    return _llm


def get_session_store() -> SessionStore:
    global _sessions
    if _sessions is None:
        settings = get_settings()
        _sessions = SessionStore(
            max_context_messages=settings.max_context_messages, max_context_chars=settings.max_context_chars
        )
    return _sessions
