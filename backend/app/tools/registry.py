"""
Tool registry.

Central place where every tool ALFRED knows about is registered. The
orchestrator asks this registry for (a) Gemini-ready tool declarations and
(b) a validated, permission-checked way to execute a specific tool by name.
Adding a new tool means writing a `BaseTool` subclass and registering an
instance here -- the orchestrator never needs to change.
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from app.services.llm import ToolDefinition
from app.tools.base import BaseTool, PermissionLevel, ToolResult

logger = logging.getLogger("alfred.tools.registry")


class ToolNotFoundError(KeyError):
    """Raised when the agent (or Gemini) asks for a tool that isn't registered."""


class ToolRegistry:
    """Registers, exposes, validates, and executes tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool
        logger.info("Registered tool '%s' (permission=%s)", tool.name, tool.permission_level)

    def get(self, name: str) -> BaseTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotFoundError(
                f"Tool '{name}' is not registered. Allowed tools: "
                f"{sorted(self._tools)}"
            ) from exc

    def is_allowed(self, name: str) -> bool:
        """Allowlist check -- only registered tools may ever execute."""
        return name in self._tools

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def get_tool_definitions(self) -> list[ToolDefinition]:
        """Build the provider-agnostic tool declarations to hand to the LLM."""
        return [
            ToolDefinition(
                name=tool.name,
                description=tool.description,
                parameters=tool.get_parameters_schema(),
            )
            for tool in self._tools.values()
        ]

    async def execute(self, name: str, raw_arguments: dict) -> ToolResult:
        """
        Validate arguments and execute a tool by name.

        This is the single choke point every tool call passes through:
        unknown tools are rejected (allowlisting), malformed arguments
        never reach `execute`, and unexpected exceptions are converted
        into a safe `ToolResult.fail(...)` instead of propagating.
        """
        if not self.is_allowed(name):
            return ToolResult.fail(f"Tool '{name}' is not allowed or does not exist.")

        tool = self._tools[name]

        try:
            validated_args = tool.validate_arguments(raw_arguments)
        except ValidationError as exc:
            logger.warning("Invalid arguments for tool '%s': %s", name, exc)
            return ToolResult.fail(f"Invalid arguments for '{name}': {exc}")

        try:
            return await tool.execute(validated_args)
        except Exception as exc:  # noqa: BLE001 - never let a tool crash the agent
            logger.exception("Tool '%s' raised an unexpected error", name)
            return ToolResult.fail(f"Tool '{name}' failed unexpectedly: {exc}")

    def permission_for_call(self, name: str, raw_arguments: dict) -> PermissionLevel | None:
        """Permission level for this specific call, or None if the arguments are invalid."""
        tool = self.get(name)
        try:
            validated = tool.validate_arguments(raw_arguments)
        except ValidationError:
            return None
        return tool.permission_for(validated)

    def describe_call(self, name: str, raw_arguments: dict) -> str:
        """Speakable description of a pending call; never raises."""
        tool = self.get(name)
        try:
            return tool.describe_call(tool.validate_arguments(raw_arguments)).rstrip(".")
        except Exception:  # noqa: BLE001 - description is cosmetic, fall back to the generic form
            return f"I can run {name}"

    def requires_confirmation(self, name: str, raw_arguments: dict, *, confirm_medium: bool = True) -> bool:
        """
        HIGH always needs confirmation; MEDIUM does when `confirm_medium` is set.
        Invalid arguments need none -- they fail validation before anything runs.
        """
        level = self.permission_for_call(name, raw_arguments)
        if level == PermissionLevel.HIGH:
            return True
        if level == PermissionLevel.MEDIUM:
            return confirm_medium
        return False


def build_default_registry(settings=None, store=None, memory=None) -> ToolRegistry:
    """
    Construct the registry with every built-in tool registered.

    `store` is the SQLite backend for notes, reminders and documents; `memory` is the Phase 4
    MemoryCoordinator (PostgreSQL). Without it the memory and tasks tools are not registered. New tools are
    added with one more `register(...)` call here -- the orchestrator never changes.
    """
    from app.config.settings import get_settings
    from app.database.sqlite_store import SQLiteStore
    from app.tools.calculator import CalculatorTool
    from app.tools.datetime_tool import DateTimeTool
    from app.tools.document_analyzer import DocumentAnalyzerTool
    from app.tools.file_search import FileSearchTool
    from app.tools.notes import NotesTool
    from app.tools.reminders import RemindersTool
    from app.tools.weather import WeatherTool
    from app.tools.web_search import WebSearchTool

    settings = settings or get_settings()
    store = store or SQLiteStore(settings.sqlite_path)

    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(DateTimeTool())
    registry.register(WebSearchTool(default_max_results=settings.search_max_results))
    registry.register(WeatherTool())
    registry.register(NotesTool(store))
    registry.register(RemindersTool(store, default_timezone=settings.default_timezone))
    registry.register(FileSearchTool(store))
    registry.register(DocumentAnalyzerTool(store))
    if memory is not None:
        from app.tools.memory_tool import MemoryTool
        from app.tools.tasks_tool import TasksTool

        registry.register(MemoryTool(memory))
        registry.register(TasksTool(memory))
    return registry
