"""
Memory management API (PostgreSQL-backed).

GET    /api/memory/status             database + memory health and counts
GET    /api/memory                    list memories (?category=&status=&limit=&offset=)
GET    /api/memory/search?q=          full-text search
POST   /api/memory                    create (deduplicates; replaces on same key)
GET    /api/memory/{id}  PATCH  DELETE
GET    /api/tasks  POST               list / create task memory
GET    /api/tasks/search?q=           search tasks and their updates
GET    /api/tasks/{id}  PATCH  DELETE
POST   /api/tasks/{id}/updates        add a note, decision, milestone or step
GET    /api/conversations             stored conversations
GET    /api/conversations/{id}/messages
DELETE /api/conversations/{id}
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import get_memory
from app.database.postgres import DatabaseUnavailable
from app.memory.coordinator import MemoryCoordinator
from app.memory.repository import CATEGORIES
from app.memory.service import MemoryValidationError
from app.memory.tasks import STATUSES, UPDATE_KINDS, TaskValidationError

router = APIRouter(prefix="/api", tags=["memory"])


def require_memory() -> MemoryCoordinator:
    memory = get_memory()
    if memory is None:
        raise HTTPException(status_code=503, detail="Persistent memory is disabled: set DATABASE_URL (see .env.example).")
    return memory


async def _ready(memory: MemoryCoordinator) -> None:
    try:
        await memory.ready()
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ---- schemas -----------------------------------------------------------------
class MemoryCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)
    category: str = "fact"
    key: str | None = Field(default=None, max_length=80)
    importance: int = Field(default=3, ge=1, le=5)


class MemoryPatch(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=1000)
    category: str | None = None
    importance: int | None = Field(default=None, ge=1, le=5)
    status: str | None = Field(default=None, description="active or archived")


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    project: str | None = Field(default=None, max_length=100)
    status: str = "pending"
    priority: int = Field(default=3, ge=1, le=5)


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    project: str | None = Field(default=None, max_length=100)
    status: str | None = None
    priority: int | None = Field(default=None, ge=1, le=5)


class TaskUpdateCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    kind: str = "note"


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def _not_found(what: str, ident: Any) -> HTTPException:
    return HTTPException(status_code=404, detail=f"No {what} with id {ident}.")


# ---- memories ----------------------------------------------------------------------
@router.get("/memory/status")
async def memory_status() -> dict:
    memory = get_memory()
    if memory is None:
        return {"enabled": False, "detail": "DATABASE_URL is not set."}
    health = await memory.db.run(memory.db.check)
    status: dict[str, Any] = {"enabled": True, **health}
    if health.get("connected"):
        try:
            await memory.ready()
            status["memories"] = await memory.db.run(memory.memories.counts)
        except DatabaseUnavailable as exc:
            status["detail"] = str(exc)
    return status


@router.get("/memory/search")
async def search_memories(q: str = Query(..., min_length=1), category: str | None = None, limit: int = Query(10, ge=1, le=50),
                          memory: MemoryCoordinator = Depends(require_memory)) -> list[dict]:
    await _ready(memory)
    return await memory.db.run(memory.memories.search, q, categories=[category] if category else None, limit=limit)


@router.get("/memory")
async def list_memories(category: str | None = None, status: str | None = "active", limit: int = Query(50, ge=1, le=200),
                        offset: int = Query(0, ge=0), memory: MemoryCoordinator = Depends(require_memory)) -> list[dict]:
    if category and category not in CATEGORIES:
        raise _bad_request(ValueError(f"Unknown category. Use one of {list(CATEGORIES)}."))
    await _ready(memory)
    return await memory.db.run(memory.memories.list, category=category, status=status or None, limit=limit, offset=offset)


@router.post("/memory", status_code=201)
async def create_memory(body: MemoryCreate, memory: MemoryCoordinator = Depends(require_memory)) -> dict:
    await _ready(memory)
    try:
        outcome = await memory.db.run(
            memory.memories.remember, body.content, category=body.category, key=body.key,
            importance=body.importance, source="api",
        )
    except MemoryValidationError as exc:
        raise _bad_request(exc) from exc
    return {"result": outcome.action, "memory": outcome.memory, "replaced": outcome.replaced}


@router.get("/memory/{memory_id}")
async def get_memory_item(memory_id: int, memory: MemoryCoordinator = Depends(require_memory)) -> dict:
    await _ready(memory)
    row = await memory.db.run(memory.memories.get, memory_id)
    if row is None:
        raise _not_found("memory", memory_id)
    return row


@router.patch("/memory/{memory_id}")
async def update_memory(memory_id: int, body: MemoryPatch, memory: MemoryCoordinator = Depends(require_memory)) -> dict:
    await _ready(memory)
    try:
        row = await memory.db.run(memory.memories.update, memory_id, **body.model_dump(exclude_none=True))
    except MemoryValidationError as exc:
        raise _bad_request(exc) from exc
    if row is None:
        raise _not_found("memory", memory_id)
    return row


@router.delete("/memory/{memory_id}", status_code=204)
async def delete_memory(memory_id: int, memory: MemoryCoordinator = Depends(require_memory)) -> None:
    await _ready(memory)
    if not await memory.db.run(memory.memories.delete, memory_id):
        raise _not_found("memory", memory_id)


# ---- tasks -------------------------------------------------------------------------------
@router.get("/tasks/search")
async def search_tasks(q: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=50),
                       memory: MemoryCoordinator = Depends(require_memory)) -> list[dict]:
    await _ready(memory)
    return await memory.db.run(memory.tasks.search, q, limit=limit)


@router.get("/tasks")
async def list_tasks(status: str | None = None, project: str | None = None, active_only: bool = False,
                     limit: int = Query(50, ge=1, le=200), memory: MemoryCoordinator = Depends(require_memory)) -> list[dict]:
    await _ready(memory)
    try:
        return await memory.db.run(memory.tasks.list, status=status, project=project, active_only=active_only, limit=limit)
    except TaskValidationError as exc:
        raise _bad_request(exc) from exc


@router.post("/tasks", status_code=201)
async def create_task(body: TaskCreate, memory: MemoryCoordinator = Depends(require_memory)) -> dict:
    await _ready(memory)
    try:
        return await memory.db.run(
            memory.tasks.create, body.title, description=body.description, project=body.project,
            priority=body.priority, status=body.status,
        )
    except TaskValidationError as exc:
        raise _bad_request(exc) from exc


@router.get("/tasks/{task_id}")
async def get_task(task_id: int, memory: MemoryCoordinator = Depends(require_memory)) -> dict:
    await _ready(memory)
    row = await memory.db.run(memory.tasks.get, task_id)
    if row is None:
        raise _not_found("task", task_id)
    return row


@router.patch("/tasks/{task_id}")
async def update_task(task_id: int, body: TaskPatch, memory: MemoryCoordinator = Depends(require_memory)) -> dict:
    await _ready(memory)
    try:
        row = await memory.db.run(memory.tasks.update, task_id, **body.model_dump(exclude_none=True))
    except TaskValidationError as exc:
        raise _bad_request(exc) from exc
    if row is None:
        raise _not_found("task", task_id)
    return row


@router.post("/tasks/{task_id}/updates", status_code=201)
async def add_task_update(task_id: int, body: TaskUpdateCreate, memory: MemoryCoordinator = Depends(require_memory)) -> dict:
    await _ready(memory)
    try:
        row = await memory.db.run(memory.tasks.add_update, task_id, body.content, kind=body.kind)
    except TaskValidationError as exc:
        raise _bad_request(exc) from exc
    if row is None:
        raise _not_found("task", task_id)
    return row


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: int, memory: MemoryCoordinator = Depends(require_memory)) -> None:
    await _ready(memory)
    if not await memory.db.run(memory.tasks.delete, task_id):
        raise _not_found("task", task_id)


# ---- conversations -------------------------------------------------------------------------
@router.get("/conversations")
async def list_conversations(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                             memory: MemoryCoordinator = Depends(require_memory)) -> list[dict]:
    await _ready(memory)
    return await memory.db.run(memory.conversations.list, limit=limit, offset=offset)


@router.get("/conversations/{conversation_id}/messages")
async def conversation_messages(conversation_id: str, limit: int = Query(200, ge=1, le=1000),
                                memory: MemoryCoordinator = Depends(require_memory)) -> list[dict]:
    await _ready(memory)
    if not await memory.db.run(memory.conversations.exists, conversation_id):
        raise _not_found("conversation", conversation_id)
    return await memory.db.run(memory.conversations.messages, conversation_id, limit=limit)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str, memory: MemoryCoordinator = Depends(require_memory)) -> None:
    await _ready(memory)
    if not await memory.db.run(memory.conversations.delete, conversation_id):
        raise _not_found("conversation", conversation_id)
