"""
Short-term memory: choose which recent turns of the current conversation go to the model.

The full conversation stays in `ConversationState`; only a bounded window is sent,
so long chats do not balloon token usage. The window always starts at a user
message (a history opening with a tool result or assistant turn is invalid for Gemini),
which also keeps tool-call/result pairs together, and always contains the latest user message.
"""

from __future__ import annotations

from app.services.llm import Message, Role


def _size(message: Message) -> int:
    extra = sum(len(str(call.arguments)) + len(call.name) for call in message.tool_calls)
    return len(message.content or "") + extra


def context_window(messages: list[Message], *, max_messages: int | None, max_chars: int | None) -> list[Message]:
    last_user = next((i for i in range(len(messages) - 1, -1, -1) if messages[i].role == Role.USER), None)
    if last_user is None:
        return list(messages)

    start = 0
    if max_messages is not None:
        start = max(0, len(messages) - max_messages)
    start = min(start, last_user)
    if max_chars is not None:
        total = sum(_size(m) for m in messages[start:])
        while start < last_user and total > max_chars:
            total -= _size(messages[start])
            start += 1
    while start < last_user and messages[start].role != Role.USER:
        start += 1
    return messages[start:]
