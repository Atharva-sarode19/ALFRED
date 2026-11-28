"""
ALFRED FastAPI application entrypoint.

Health check, tool listing, and the chat, voice, files, reminders and memory routers.
The agent chain is AgentOrchestrator -> GeminiProvider -> ToolRegistry.
Later phases add more routers without touching this file.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from contextlib import asynccontextmanager

from app.api.chat import router as chat_router
from app.api.deps import get_memory, get_tool_registry
from app.api.files import router as files_router
from app.api.memory import router as memory_router
from app.api.reminders import router as reminders_router
from app.api.voice import router as voice_router
from app.api.workflows import router as workflows_router
from app.config.runtime_check import check_python
from app.config.settings import ALLOWED_ORIGINS, get_settings
from app.database.postgres import DatabaseUnavailable

check_python()
settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("alfred.main")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Prepare PostgreSQL memory (migrate + housekeeping). A database outage must not stop ALFRED starting."""
    memory = get_memory()
    if memory is None:
        logger.info("Persistent memory disabled (DATABASE_URL not set).")
    else:
        try:
            await memory.db.run(memory.prepare, settings.memory_archive_after_days)
            logger.info("Persistent memory ready.")
        except DatabaseUnavailable as exc:
            logger.warning("Persistent memory unavailable at startup; will retry on use: %s", exc)
        except Exception:  # noqa: BLE001
            logger.exception("Persistent memory setup failed; continuing without it")
    yield
    if memory is not None:
        memory.db.close()


app = FastAPI(
    title="ALFRED",
    description="Adaptive Language Framework for Reasoning, Execution & Dialogue",
    version="0.4.0",
    lifespan=lifespan,
)


@app.exception_handler(DatabaseUnavailable)
async def database_unavailable_handler(_: Request, exc: DatabaseUnavailable) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})

# Phase 1: permissive CORS for local frontend dev. Tighten before any
# real deployment (see docs/SECURITY.md once Phase 3+ lands).
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(voice_router)
app.include_router(files_router)
app.include_router(reminders_router)
app.include_router(memory_router)
app.include_router(workflows_router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}


@app.get("/api/tools")
async def list_tools() -> list[dict]:
    registry = get_tool_registry()
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "permission_level": tool.permission_level.value,
            "parameters": tool.get_parameters_schema(),
        }
        for tool in registry.list_tools()
    ]
