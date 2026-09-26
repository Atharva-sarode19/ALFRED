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

    def requires_confirmation(self, name: str) -> bool:
        """MEDIUM and HIGH permission tools require confirmation; LOW does not."""
        tool = self.get(name)
        return tool.permission_level in (PermissionLevel.MEDIUM, PermissionLevel.HIGH)


def build_default_registry() -> ToolRegistry:
    """
    Construct the registry with Phase 1's tools pre-registered.

    Later phases add more `register(...)` calls here (web_search, weather,
    notes, reminders, file_search, document_analyzer) without touching the
    orchestrator or the registry class itself.
    """
    from app.tools.calculator import CalculatorTool
    from app.tools.datetime_tool import DateTimeTool

    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(DateTimeTool())
    return registry
