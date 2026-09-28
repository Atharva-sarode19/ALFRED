"""
ALFRED FastAPI application entrypoint.

Phase 1 scope: health check, tool listing, and POST /api/chat wired through
the AgentOrchestrator -> GeminiProvider -> ToolRegistry (calculator,
datetime) chain. Later phases add more routers without touching this file.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import get_tool_registry, router as chat_router
from app.api.voice import router as voice_router
from app.config.settings import get_settings

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("alfred.main")

app = FastAPI(
    title="ALFRED",
    description="Adaptive Language Framework for Reasoning, Execution & Dialogue",
    version="0.2.0",
)

# Phase 1: permissive CORS for local frontend dev. Tighten before any
# real deployment (see docs/SECURITY.md once Phase 3+ lands).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(voice_router)


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
