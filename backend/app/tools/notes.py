"""notes: create, retrieve, search and delete the user's notes."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.database.sqlite_store import SQLiteStore
from app.tools.base import BaseTool, PermissionLevel, ToolResult


class NotesAction(str, Enum):
    CREATE = "create"
    GET = "get"
    SEARCH = "search"
    DELETE = "delete"


class NotesInput(BaseModel):
    action: NotesAction = Field(..., description="create, get (by id), search (by keywords; blank lists recent), or delete.")
    note_id: int | None = Field(default=None, ge=1, description="Required for get and delete.")
    title: str | None = Field(default=None, max_length=200, description="Optional for create; derived from the content if omitted.")
    content: str | None = Field(default=None, max_length=20000, description="Required for create.")
    query: str | None = Field(default=None, max_length=200, description="Keywords for search.")

    @model_validator(mode="after")
    def _check(self) -> "NotesInput":
        if self.action == NotesAction.CREATE and not (self.content and self.content.strip()):
            raise ValueError("'content' is required to create a note.")
        if self.action in (NotesAction.GET, NotesAction.DELETE) and self.note_id is None:
            raise ValueError("'note_id' is required for get and delete.")
        return self


class NotesTool(BaseTool):
    name = "notes"
    description = "Create, retrieve, search and delete the user's saved notes."
    permission_level = PermissionLevel.HIGH  # highest action; see permission_for
    input_model = NotesInput

    def __init__(self, store: SQLiteStore):
        self._store = store

    def permission_for(self, arguments: NotesInput) -> PermissionLevel:
        if arguments.action == NotesAction.CREATE:
            return PermissionLevel.MEDIUM
        if arguments.action == NotesAction.DELETE:
            return PermissionLevel.HIGH  # permanent data loss
        return PermissionLevel.LOW

    def describe_call(self, arguments: NotesInput) -> str:
        if arguments.action == NotesAction.CREATE:
            return "I can save that note"
        if arguments.action == NotesAction.DELETE:
            return f"I can permanently delete note number {arguments.note_id}"
        return "I can look through your notes"

    async def execute(self, arguments: NotesInput) -> ToolResult:
        store = self._store
        if arguments.action == NotesAction.CREATE:
            content = arguments.content.strip()
            title = (arguments.title or content.splitlines()[0])[:80].strip() or "Untitled"
            return ToolResult.ok({"note": await store.run(store.create_note, title, content)})

        if arguments.action == NotesAction.GET:
            note = await store.run(store.get_note, arguments.note_id)
            if note is None:
                return ToolResult.fail(f"There is no note with id {arguments.note_id}.")
            return ToolResult.ok({"note": note})

        if arguments.action == NotesAction.SEARCH:
            notes = await store.run(store.search_notes, arguments.query, 10)
            return ToolResult.ok({"count": len(notes), "notes": notes})

        deleted = await store.run(store.delete_note, arguments.note_id)
        if not deleted:
            return ToolResult.fail(f"There is no note with id {arguments.note_id}.")
        return ToolResult.ok({"deleted_note_id": arguments.note_id})
