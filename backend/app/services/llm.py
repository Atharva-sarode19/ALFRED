"""
Provider-agnostic LLM abstraction.

The agent orchestrator depends ONLY on the `LLMProvider` interface defined
here -- never on a concrete vendor SDK. This is what lets ALFRED swap or add
LLM providers later without rewriting agent logic. Phase 1 ships a single
concrete implementation, `GeminiProvider` (see `gemini.py`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ToolDefinition:
    """Vendor-agnostic description of a tool the LLM may call."""

    name: str
    description: str
    # JSON-schema-style dict describing the tool's input arguments.
    parameters: dict[str, Any]


@dataclass
class ToolCallRequest:
    """A single structured tool call the model asked to make."""

    id: str
    name: str
    arguments: dict[str, Any]
    thought_signature: Any | None = None


@dataclass
class Message:
    """A single turn in the conversation, in provider-agnostic form."""

    role: Role
    content: str | None = None
    # Populated on assistant messages that request tool calls.
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    # Populated on tool-result messages fed back to the model.
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class GenerationResult:
    """Normalized result of a single LLM turn."""

    text: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str | None = None
    raw: Any = None  # Original provider response, kept for debugging/logs.

    @property
    def requires_tool_execution(self) -> bool:
        return bool(self.tool_calls)


class LLMProviderError(RuntimeError):
    """Raised when a provider call fails (timeout, API error, bad response)."""


class LLMUnavailableError(LLMProviderError):
    """Raised when a provider remains unavailable after retrying (e.g. 503)."""


class LLMAuthenticationError(LLMProviderError):
    """Raised when the provider rejects our credentials (e.g. 401/403)."""


class LLMRateLimitError(LLMProviderError):
    """Raised when the provider is rate-limiting us (e.g. 429, retries exhausted)."""


class LLMBadRequestError(LLMProviderError):
    """Raised when the provider rejects the request itself (e.g. 400 malformed request)."""


class LLMProvider(ABC):
    """
    Abstract interface every LLM backend must implement.

    The agent orchestrator (`app.agent.orchestrator.AgentOrchestrator`)
    is written entirely against this interface.
    """

    @abstractmethod
    async def generate(
        self,
        messages: list[Message],
        *,
        system_instruction: str | None = None,
    ) -> GenerationResult:
        """Generate a plain-text response with no tool-calling capability."""
        raise NotImplementedError

    @abstractmethod
    async def generate_with_tools(
        self,
        messages: list[Message],
        tools: list[ToolDefinition],
        *,
        system_instruction: str | None = None,
    ) -> GenerationResult:
        """
        Generate a response where the model may choose to request one or
        more structured tool calls instead of (or alongside) plain text.
        """
        raise NotImplementedError