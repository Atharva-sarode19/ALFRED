"""
ALFRED FastAPI application entrypoint.

Health check, tool listing, and the chat, voice, files and reminders routers.
The agent chain is AgentOrchestrator -> GeminiProvider -> ToolRegistry.
Later phases add more routers without touching this file.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.deps import get_tool_registry
from app.api.files import router as files_router
from app.api.reminders import router as reminders_router
from app.api.voice import router as voice_router
from app.config.settings import ALLOWED_ORIGINS, get_settings

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("alfred.main")


app = FastAPI(
    title="ALFRED",
    description="Adaptive Language Framework for Reasoning, Execution & Dialogue",
    version="0.3.0",
)

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
