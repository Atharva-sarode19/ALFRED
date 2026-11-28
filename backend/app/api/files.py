"""
POST /api/files/upload  -- upload a PDF, DOCX or TXT document.
GET  /api/files         -- list uploaded documents (newest first).
POST /api/files/search  -- search uploaded documents by name and content.
DELETE /api/files/{id}  -- remove a document: stored file, text, chunks and search index.

Uploads are validated by extension, size and real content signature, saved
under a generated name (never the client's), and their text is indexed.
No authentication yet -- it arrives with the security phase.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import get_store
from app.config.settings import get_settings
from app.database.sqlite_store import SQLiteStore
from app.services.documents import (
    MEDIA_TYPES,
    DocumentError,
    chunk_text,
    detect_kind,
    extract_text,
    sanitize_filename,
)

logger = logging.getLogger("alfred.api.files")

router = APIRouter(prefix="/api/files", tags=["files"])


class FileInfo(BaseModel):
    id: str
    name: str
    media_type: str
    size_bytes: int
    char_count: int
    uploaded_at: str


class FileSearchRequest(BaseModel):
    query: str | None = Field(default=None, max_length=300)
    max_results: int = Field(default=5, ge=1, le=20)


class FileSearchHit(FileInfo):
    name_match: bool
    snippets: list[str]


class FileSearchResponse(BaseModel):
    files: list[FileSearchHit]


@router.post("/upload", response_model=FileInfo, status_code=201)
async def upload_file(file: UploadFile, store: SQLiteStore = Depends(get_store)) -> FileInfo:
    settings = get_settings()
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail=f"File is larger than {settings.max_upload_bytes // (1024 * 1024)} MB.")

    display_name = sanitize_filename(file.filename or "")
    try:
        kind = detect_kind(display_name, data, settings.max_upload_bytes)
        text = await asyncio.to_thread(extract_text, kind, data)
    except DocumentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    file_id = uuid.uuid4().hex
    stored_name = f"{file_id}.{kind}"
    uploads: Path = settings.uploads_dir
    try:
        uploads.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread((uploads / stored_name).write_bytes, data)
        info = await store.run(
            store.add_file, file_id, display_name, stored_name, MEDIA_TYPES[kind], len(data), text, chunk_text(text)
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to store uploaded file")
        (uploads / stored_name).unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="The file could not be saved.") from exc
    return FileInfo(**info)


@router.get("", response_model=list[FileInfo])
async def list_files(store: SQLiteStore = Depends(get_store)) -> list[FileInfo]:
    return [FileInfo(**f) for f in await store.run(store.list_files, 50)]


@router.post("/search", response_model=FileSearchResponse)
async def search_files(request: FileSearchRequest, store: SQLiteStore = Depends(get_store)) -> FileSearchResponse:
    rows = await store.run(store.search_files, request.query, request.max_results)
    return FileSearchResponse(files=[FileSearchHit(**r) for r in rows])


@router.delete("/{file_id}", status_code=204)
async def delete_file(file_id: str, store: SQLiteStore = Depends(get_store)) -> None:
    stored_name = await store.run(store.get_stored_name, file_id)
    if stored_name is None:
        raise HTTPException(status_code=404, detail="No such document.")
    try:
        # Stored file first: if it cannot be removed the record stays, so nothing is half-deleted silently.
        await asyncio.to_thread((get_settings().uploads_dir / stored_name).unlink, True)
        await store.run(store.delete_file, file_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to delete document %s", file_id)
        raise HTTPException(status_code=500, detail="The document could not be removed.") from exc
