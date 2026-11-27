"""
Helpers for treating external content (web pages, search results, uploaded
documents) as untrusted DATA rather than instructions.

The wrapper cannot make a model immune to prompt injection, but it gives the
system prompt a clear boundary to refer to, and it prevents the content from
forging the closing delimiter.
"""

from __future__ import annotations

OPEN_MARKER = "<<<UNTRUSTED_CONTENT"
CLOSE_MARKER = "<<<END_UNTRUSTED_CONTENT>>>"


def wrap_untrusted(source: str, text: str, *, max_chars: int = 20000) -> str:
    """Wrap `text` in delimiters, neutralizing any attempt to forge them."""
    safe = text.replace("<<<", "\u2039\u2039\u2039").replace(">>>", "\u203a\u203a\u203a")
    if len(safe) > max_chars:
        safe = safe[:max_chars] + "\n[truncated]"
    safe_source = "".join(ch for ch in source if ch.isalnum() or ch in "_-.")[:40]
    return f"{OPEN_MARKER} source={safe_source}>>>\n{safe}\n{CLOSE_MARKER}"
