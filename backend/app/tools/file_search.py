"""file_search: find uploaded documents by name and content."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.database.sqlite_store import SQLiteStore
from app.tools.base import BaseTool, PermissionLevel, ToolResult


class FileSearchInput(BaseModel):
    query: str | None = Field(
        default=None,
        max_length=300,
        description="Keywords from the file name or contents. Leave empty to list the newest uploads first.",
    )
    max_results: int = Field(default=5, ge=1, le=10)


class FileSearchTool(BaseTool):
    name = "file_search"
    description = (
        "Search the user's uploaded documents (PDF, DOCX, TXT) by file name and content. "
        "Returns file ids and matching excerpts; read a whole document with document_analyzer."
    )
    permission_level = PermissionLevel.LOW
    input_model = FileSearchInput

    def __init__(self, store: SQLiteStore):
        self._store = store

    async def execute(self, arguments: FileSearchInput) -> ToolResult:
        files = await self._store.run(self._store.search_files, arguments.query, arguments.max_results)
        return ToolResult.ok(
            {
                "query": arguments.query,
                "count": len(files),
                "files": [
                    {
                        "file_id": f["id"],
                        "name": f["name"],
                        "media_type": f["media_type"],
                        "uploaded_at": f["uploaded_at"],
                        "name_match": f["name_match"],
                        "excerpts": f["snippets"],
                    }
                    for f in files
                ],
            },
            untrusted=True,  # file names and excerpts come from user-supplied documents
        )
