"""
MemoryCoordinator: what the agent talks to. Wires the PostgreSQL manager, services,
retrieval and extraction together and guards the conversation against memory failures:
if PostgreSQL is down or a memory operation fails, the agent carries on without memory.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.config.settings import Settings
from app.database.migrator import ensure_schema
from app.database.postgres import DatabaseUnavailable, PostgresManager
from app.memory.conversations import ConversationManager
from app.memory.extraction import ExtractionResult, LLMMemoryExtractor, MemoryExtractor
from app.memory.retrieval import MemoryRetriever
from app.memory.service import MemoryService
from app.memory.tasks import TaskMemoryManager

if TYPE_CHECKING:  # pragma: no cover
    from app.agent.state import ConversationState
    from app.services.llm import LLMProvider

logger = logging.getLogger("alfred.memory")


@dataclass
class TurnContext:
    """What memory contributes to one turn: a prompt block plus safe trace notes."""

    block: str | None = None
    notes: list[tuple[str, str]] = field(default_factory=list)


class MemoryCoordinator:
    def __init__(
        self,
        db: PostgresManager,
        *,
        max_retrieved: int = 5,
        min_score: float = 0.15,
        history_limit: int = 40,
        auto_migrate: bool = True,
        llm: "LLMProvider | None" = None,
        use_llm_extraction: bool = False,
    ):
        self.db = db
        self.memories = MemoryService(db)
        self.tasks = TaskMemoryManager(db)
        self.conversations = ConversationManager(db)
        self.retriever = MemoryRetriever(self.memories, self.tasks, max_items=max_retrieved, min_score=min_score)
        self._extractor = MemoryExtractor()
        self._llm_extractor = LLMMemoryExtractor(llm) if (llm and use_llm_extraction) else None
        self._history_limit = history_limit
        self._auto_migrate = auto_migrate

    # ---- setup ---------------------------------------------------------------------
    def prepare(self, archive_after_days: int = 180) -> None:
        """Migrate (if enabled) and run housekeeping. Safe to call repeatedly."""
        self._ensure_ready()
        self.memories.run_maintenance(archive_after_days)

    def _ensure_ready(self) -> None:
        if self._auto_migrate:
            ensure_schema(self.db)

    async def ready(self) -> None:
        """Raises DatabaseUnavailable if memory cannot be used right now."""
        await self.db.run(self._ensure_ready)

    # ---- agent hooks -------------------------------------------------------------------
    async def begin_turn(self, state: "ConversationState", user_input: str) -> TurnContext:
        """Restore history after a restart, record the user message and retrieve relevant memory."""
        ctx = TurnContext()
        try:
            await self.ready()
            if not state.hydrated:
                state.hydrated = True
                if not state.messages:
                    restored = await self.db.run(
                        self.conversations.load_history, state.session_id, limit=self._history_limit
                    )
                    if restored:
                        state.add_many(restored)
                        ctx.notes.append(("memory_restored", f"Restored {len(restored)} earlier messages"))
            await self.db.run(self.conversations.add_message, state.session_id, "user", user_input)
            result = await self.db.run(self.retriever.retrieve, user_input)
            ctx.block = self.retriever.format_context(result)
            if not result.empty:
                ctx.notes.append(
                    ("memory_retrieved", f"Recalled {len(result.memories)} memories and {len(result.tasks)} tasks")
                )
        except DatabaseUnavailable as exc:
            logger.warning("Memory unavailable, continuing without it: %s", exc)
        except Exception:  # noqa: BLE001 - memory must never break a conversation
            logger.exception("Memory retrieval failed; continuing without it")
        return ctx

    async def end_turn(self, state: "ConversationState", user_input: str, response: str) -> list[tuple[str, str]]:
        """Record the reply and store anything worth remembering. Returns trace notes."""
        notes: list[tuple[str, str]] = []
        try:
            await self.db.run(self.conversations.add_message, state.session_id, "assistant", response)
            extracted = self._extractor.extract(user_input)
            if self._llm_extractor is not None:
                extra = await self._llm_extractor.extract(user_input)
                extracted.candidates.extend(extra.candidates)
            saved = await self.db.run(self._store, extracted, state.session_id)
            if saved:
                notes.append(("memory_saved", f"Remembered {saved} new or updated item(s)"))
        except DatabaseUnavailable as exc:
            logger.warning("Memory unavailable, nothing was saved: %s", exc)
        except Exception:  # noqa: BLE001
            logger.exception("Memory storage failed")
        return notes

    def _store(self, extracted: ExtractionResult, conversation_id: str) -> int:
        changed = 0
        for key in extracted.retract_keys:
            changed += self.memories.retract(key)
        for c in extracted.candidates:
            outcome = self.memories.remember(
                c.content, category=c.category, key=c.key, importance=c.importance, source=c.source,
                conversation_id=conversation_id, expires_at=c.expires_at,
            )
            changed += outcome.action in ("created", "updated")
        return changed


def build_memory_coordinator(settings: Settings, llm: "LLMProvider | None" = None) -> MemoryCoordinator | None:
    """None when memory is disabled (no DATABASE_URL / MEMORY_ENABLED=false)."""
    if not settings.memory_enabled:
        return None
    db = PostgresManager(
        settings.database_url,
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
        connect_timeout=settings.db_connect_timeout,
    )
    return MemoryCoordinator(
        db,
        max_retrieved=settings.memory_max_retrieved,
        min_score=settings.memory_min_score,
        history_limit=settings.max_context_messages,
        auto_migrate=settings.db_auto_migrate,
        llm=llm,
        use_llm_extraction=settings.memory_llm_extraction,
    )
