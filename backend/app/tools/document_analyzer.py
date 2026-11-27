"""document_analyzer: read an uploaded document (paged) or pull passages relevant to a topic."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.database.sqlite_store import SQLiteStore
from app.tools.base import BaseTool, PermissionLevel, ToolResult


class DocumentAnalyzerInput(BaseModel):
    file_id: str = Field(..., min_length=1, max_length=64, description="File id from file_search.")
    focus: str | None = Field(
        default=None,
        max_length=200,
        description="Keywords. When set, returns only the most relevant passages instead of reading in order.",
    )
    offset: int = Field(default=0, ge=0, description="Character offset to start reading from (for long documents).")
    max_chars: int = Field(default=12000, ge=500, le=20000, description="Most characters to return.")


class DocumentAnalyzerTool(BaseTool):
    name = "document_analyzer"
    description = (
        "Read text from an uploaded document so you can summarize it or answer questions. "
        "Long documents come back in pages: use next_offset to continue, or pass `focus` "
        "keywords to get just the relevant passages."
    )
    permission_level = PermissionLevel.LOW
    input_model = DocumentAnalyzerInput

    def __init__(self, store: SQLiteStore):
        self._store = store

    async def execute(self, arguments: DocumentAnalyzerInput) -> ToolResult:
        store = self._store
        meta = await store.run(store.get_file, arguments.file_id)
        if meta is None:
            return ToolResult.fail("No document has that id. Use file_search to find the right one.")

        base = {"file_id": meta["id"], "name": meta["name"], "total_chars": meta["char_count"]}

        if arguments.focus:
            hits = await store.run(store.search_chunks_in_file, meta["id"], arguments.focus, 5)
            return ToolResult.ok(
                {**base, "focus": arguments.focus, "passages": [h["text"] for h in hits]}, untrusted=True
            )

        text = await store.run(store.read_file_text, meta["id"], arguments.offset, arguments.max_chars)
        text = text or ""
        end = arguments.offset + len(text)
        has_more = end < meta["char_count"]
        return ToolResult.ok(
            {
                **base,
                "offset": arguments.offset,
                "returned_chars": len(text),
                "has_more": has_more,
                "next_offset": end if has_more else None,
                "text": text,
            },
            untrusted=True,
        )
