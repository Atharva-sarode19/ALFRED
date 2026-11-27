"""
GET    /api/reminders       -- list reminders (scope: upcoming | past | all).
POST   /api/reminders       -- create a reminder.
DELETE /api/reminders/{id}  -- delete a reminder.

The agent's `reminders` tool and these routes share the same time parsing.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.api.deps import get_store
from app.config.settings import get_settings
from app.database.sqlite_store import SQLiteStore, utc_now_iso
from app.tools.reminders import ReminderTimeError, parse_due_at, present_reminder

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


class ReminderCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    due_at: str = Field(..., description="ISO 8601 date-time. Without an offset it is read in `timezone`.")
    timezone: str | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ReminderOut(BaseModel):
    id: int
    title: str
    notes: str | None = None
    due_local: str
    due_utc: str
    timezone: str


@router.get("", response_model=list[ReminderOut])
async def list_reminders(
    scope: Literal["upcoming", "past", "all"] = "upcoming", store: SQLiteStore = Depends(get_store)
) -> list[ReminderOut]:
    tz = get_settings().default_timezone
    rows = await store.run(store.list_reminders, scope, utc_now_iso())
    return [ReminderOut(**present_reminder(r, tz)) for r in rows]


@router.post("", response_model=ReminderOut, status_code=201)
async def create_reminder(body: ReminderCreate, store: SQLiteStore = Depends(get_store)) -> ReminderOut:
    tz = body.timezone or get_settings().default_timezone
    try:
        due_utc = parse_due_at(body.due_at, tz)
    except ReminderTimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    row = await store.run(store.create_reminder, body.title.strip(), due_utc.isoformat(), body.notes)
    return ReminderOut(**present_reminder(row, tz))


@router.delete("/{reminder_id}", status_code=204)
async def delete_reminder(reminder_id: int, store: SQLiteStore = Depends(get_store)) -> Response:
    if not await store.run(store.delete_reminder, reminder_id):
        raise HTTPException(status_code=404, detail="Reminder not found.")
    return Response(status_code=204)
