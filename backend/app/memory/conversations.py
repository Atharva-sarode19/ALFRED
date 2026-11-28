"""ConversationManager: persists conversations and their messages in PostgreSQL."""

from __future__ import annotations

from typing import Any

from app.database.postgres import PostgresManager
from app.services.llm import Message, Role


class ConversationManager:
    def __init__(self, db: PostgresManager):
        self._db = db

    def add_message(self, conversation_id: str, role: str, content: str) -> None:
        """Append a message, creating the conversation on first use (one transaction)."""
        if role not in ("user", "assistant") or not content or not content.strip():
            return
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO conversations (id, title) VALUES (%s, %s) "
                "ON CONFLICT (id) DO UPDATE SET updated_at = now()",
                (conversation_id, content.strip()[:80] if role == "user" else None),
            )
            conn.execute(
                "UPDATE conversations SET title = coalesce(title, %s) WHERE id = %s AND title IS NULL",
                (content.strip()[:80], conversation_id),
            )
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)",
                (conversation_id, role, content),
            )

    def messages(self, conversation_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        """The most recent `limit` messages, oldest first."""
        with self._db.connection() as conn:
            rows = conn.execute(
                "SELECT id, role, content, created_at FROM messages WHERE conversation_id = %s "
                "ORDER BY id DESC LIMIT %s",
                (conversation_id, limit),
            ).fetchall()
        return list(reversed(rows))

    def load_history(self, conversation_id: str, *, limit: int) -> list[Message]:
        """Stored turns as provider messages, for resuming a conversation after a restart."""
        return [
            Message(role=Role(row["role"]), content=row["content"]) for row in self.messages(conversation_id, limit=limit)
        ]

    def list(self, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        with self._db.connection() as conn:
            return conn.execute(
                "SELECT c.id, c.title, c.created_at, c.updated_at, "
                "(SELECT count(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count "
                "FROM conversations c ORDER BY c.updated_at DESC LIMIT %s OFFSET %s",
                (limit, offset),
            ).fetchall()

    def exists(self, conversation_id: str) -> bool:
        with self._db.connection() as conn:
            return conn.execute("SELECT 1 FROM conversations WHERE id = %s", (conversation_id,)).fetchone() is not None

    def delete(self, conversation_id: str) -> bool:
        with self._db.transaction() as conn:
            return conn.execute("DELETE FROM conversations WHERE id = %s", (conversation_id,)).rowcount > 0
