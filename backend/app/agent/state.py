"""
Conversation state for a single agent session.

Holds bounded short-term conversation history. "Bounded" means we never
send an ever-growing transcript to the LLM -- old turns are trimmed once
the history exceeds `max_messages`, keeping the most recent context (the
system instruction is always kept separately and re-applied every call).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.memory.short_term import context_window
from app.services.llm import Message, Role, ToolCallRequest


@dataclass
class PendingAction:
    """A tool call waiting for the user's yes/no, plus the calls queued behind it."""

    call: ToolCallRequest
    remaining: list[ToolCallRequest]
    iteration: int
    reprompts: int = 0  # times we re-asked after an unclear spoken answer


@dataclass
class ConversationState:
    """In-memory conversation history for one session (Phase 1: no DB yet)."""

    session_id: str
    max_messages: int = 40
    messages: list[Message] = field(default_factory=list)
    pending: PendingAction | None = None
    # Short-term memory window: how much of `messages` is sent to the model (None = all).
    max_context_messages: int | None = None
    max_context_chars: int | None = None
    # Phase 4: set by the memory layer each turn.
    hydrated: bool = False
    memory_block: str | None = None
    turn_input: str = ""

    def add(self, message: Message) -> None:
        self.messages.append(message)
        self._trim()

    def add_many(self, messages: list[Message]) -> None:
        self.messages.extend(messages)
        self._trim()

    def _trim(self) -> None:
        if len(self.messages) > self.max_messages:
            # Keep the most recent turns, but never start mid-exchange: a history
            # that opens with a tool result (or an assistant turn) is invalid for Gemini.
            trimmed = self.messages[-self.max_messages :]
            start = 0
            while start < len(trimmed) and trimmed[start].role != Role.USER:
                start += 1
            self.messages = trimmed[start:] if start < len(trimmed) else trimmed

    def history(self) -> list[Message]:
        """The messages to send to the model: the recent window, never the whole transcript."""
        return context_window(
            self.messages, max_messages=self.max_context_messages, max_chars=self.max_context_chars
        )


class SessionStore:
    """
    In-memory cache of active sessions.

    The transcript itself is persisted to PostgreSQL by the memory layer and restored
    into a fresh `ConversationState` on the first turn after a restart.
    """

    def __init__(self, *, max_context_messages: int | None = None, max_context_chars: int | None = None) -> None:
        self._sessions: dict[str, ConversationState] = {}
        self._max_context_messages = max_context_messages
        self._max_context_chars = max_context_chars

    def get(self, session_id: str) -> ConversationState | None:
        return self._sessions.get(session_id)

    def get_or_create(self, session_id: str) -> ConversationState:
        if session_id not in self._sessions:
            self._sessions[session_id] = ConversationState(
                session_id=session_id,
                max_context_messages=self._max_context_messages,
                max_context_chars=self._max_context_chars,
            )
        return self._sessions[session_id]
