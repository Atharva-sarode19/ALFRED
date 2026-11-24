"""
Base tool interface and permission model.

Every tool ALFRED can call implements `BaseTool`. Tools declare their own
Pydantic input schema, a permission level, and an async `execute` method.
The ToolRegistry (see `registry.py`) uses this schema to build the
structured tool declarations handed to Gemini, and to validate arguments
the model returns before anything executes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel


class PermissionLevel(str, Enum):
    """
    How much trust a tool call requires before it can run.

    LOW    - executes automatically (e.g. calculator, datetime, weather).
    MEDIUM - may require user confirmation (e.g. create reminder/note).
    HIGH   - always requires explicit confirmation (e.g. send message,
             delete file, system commands). ALFRED never auto-approves
             HIGH-permission tools.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ToolExecutionError(RuntimeError):
    """Raised by a tool when it fails to execute (never crashes the agent)."""


class ToolResult(BaseModel):
    """Normalized result returned by every tool execution."""

    success: bool
    data: Any = None
    error: str | None = None
    # True when `data` carries external content (web pages, documents). The
    # orchestrator wraps it in untrusted-content markers before the model sees it.
    untrusted: bool = False

    @classmethod
    def ok(cls, data: Any, *, untrusted: bool = False) -> "ToolResult":
        return cls(success=True, data=data, error=None, untrusted=untrusted)

    @classmethod
    def fail(cls, error: str) -> "ToolResult":
        return cls(success=False, data=None, error=error)


class BaseTool(ABC):
    """
    Abstract base class every concrete tool must extend.

    Subclasses set the class attributes below and implement `execute`.
    `input_model` must be a Pydantic model -- it is both the runtime
    validator for arguments Gemini returns, and the source of the JSON
    schema advertised to Gemini for function calling.
    """

    name: str
    description: str
    permission_level: PermissionLevel
    input_model: type[BaseModel]

    def permission_for(self, arguments: BaseModel) -> PermissionLevel:
        """
        Permission needed for THIS call. Tools with several actions override
        this (reading a note is LOW, deleting one is HIGH). `permission_level`
        stays the tool's highest level, used for listings.
        """
        return self.permission_level

    def describe_call(self, arguments: BaseModel) -> str:
        """
        Short, speakable sentence for what this call would do, used in the
        confirmation question ("I can save that note"). Tools override this.
        """
        return f"I can run {self.name}"

    def get_parameters_schema(self) -> dict[str, Any]:
        """JSON schema for this tool's arguments, as Gemini expects it."""
        schema = self.input_model.model_json_schema()
        # Gemini's function-calling schema doesn't use every JSON-schema
        # keyword (e.g. "title", "$defs" nesting) -- strip cosmetic ones.
        schema.pop("title", None)
        for prop in schema.get("properties", {}).values():
            prop.pop("title", None)
        return schema

    def validate_arguments(self, raw_arguments: dict[str, Any]) -> BaseModel:
        """
        Validate model-supplied arguments against this tool's schema.

        Raises pydantic.ValidationError on invalid input -- callers
        (the orchestrator) are responsible for catching this and turning
        it into a safe error message rather than executing anything.
        """
        return self.input_model.model_validate(raw_arguments)

    @abstractmethod
    async def execute(self, arguments: BaseModel) -> ToolResult:
        """
        Run the tool with validated arguments and return a ToolResult.

        Implementations must never raise for expected failure modes --
        catch them and return `ToolResult.fail(...)` instead. Only raise
        `ToolExecutionError` (or let it propagate) for truly unexpected
        failures; the orchestrator will convert it into a safe message.
        """
        raise NotImplementedError
