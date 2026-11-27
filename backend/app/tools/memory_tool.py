"""memory: save, search and forget long-term memories (PostgreSQL)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.database.postgres import DatabaseUnavailable
from app.memory.coordinator import MemoryCoordinator
from app.memory.service import MemoryValidationError
from app.tools.base import BaseTool, PermissionLevel, ToolResult


class MemoryAction(str, Enum):
    SAVE = "save"
    SEARCH = "search"
    LIST = "list"
    FORGET = "forget"


class MemoryInput(BaseModel):
    action: MemoryAction = Field(..., description="save, search, list (recent/important), or forget (by id).")
    content: str | None = Field(default=None, max_length=1000, description="Required for save: one self-contained fact, in the third person ('The user prefers tea.').")
    category: str = Field(default="fact", description="For save: preference, fact, instruction, project or other.")
    key: str | None = Field(default=None, max_length=80, description="Optional slot for save, e.g. 'user.location'. A new memory with the same key replaces the old one.")
    importance: int = Field(default=3, ge=1, le=5)
    query: str | None = Field(default=None, max_length=200, description="Keywords for search.")
    memory_id: int | None = Field(default=None, ge=1, description="Required for forget.")

    @model_validator(mode="after")
    def _check(self) -> "MemoryInput":
        if self.action == MemoryAction.SAVE and not (self.content and self.content.strip()):
            raise ValueError("'content' is required to save a memory.")
        if self.action == MemoryAction.FORGET and self.memory_id is None:
            raise ValueError("'memory_id' is required to forget a memory.")
        return self


class MemoryTool(BaseTool):
    name = "memory"
    description = (
        "ALFRED's long-term memory. Save something the user asked you to remember, search what is remembered "
        "about the user, or forget a memory. Never use it for exact or current facts that a tool can compute."
    )
    permission_level = PermissionLevel.HIGH  # highest action; see permission_for
    input_model = MemoryInput

    def __init__(self, memory: MemoryCoordinator):
        self._memory = memory

    def permission_for(self, arguments: MemoryInput) -> PermissionLevel:
        return PermissionLevel.HIGH if arguments.action == MemoryAction.FORGET else PermissionLevel.LOW

    def describe_call(self, arguments: MemoryInput) -> str:
        return f"I can permanently forget memory number {arguments.memory_id}"

    async def execute(self, arguments: MemoryInput) -> ToolResult:
        memory = self._memory
        service = memory.memories
        try:
            if arguments.action == MemoryAction.SAVE:
                outcome = await memory.db.run(
                    service.remember, arguments.content, category=arguments.category, key=arguments.key,
                    importance=arguments.importance, source="explicit",
                )
                return ToolResult.ok({"result": outcome.action, "memory": outcome.memory, "replaced": outcome.replaced})
            if arguments.action == MemoryAction.SEARCH:
                rows = await memory.db.run(service.search, arguments.query or "", limit=10, touch=True)
                return ToolResult.ok({"count": len(rows), "memories": rows})
            if arguments.action == MemoryAction.LIST:
                rows = await memory.db.run(service.list, limit=15)
                return ToolResult.ok({"count": len(rows), "memories": rows})
            if not await memory.db.run(service.delete, arguments.memory_id):
                return ToolResult.fail(f"There is no memory with id {arguments.memory_id}.")
            return ToolResult.ok({"forgotten_memory_id": arguments.memory_id})
        except MemoryValidationError as exc:
            return ToolResult.fail(str(exc))
        except DatabaseUnavailable:
            return ToolResult.fail("Persistent memory is unavailable right now.")
