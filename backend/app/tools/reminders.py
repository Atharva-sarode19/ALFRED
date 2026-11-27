"""reminders: create, list and delete reminders (stored in UTC, shown in local time)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, model_validator

from app.database.sqlite_store import SQLiteStore, utc_now_iso
from app.tools.base import BaseTool, PermissionLevel, ToolResult


class ReminderTimeError(ValueError):
    """The requested reminder time is missing, malformed, unknown-zone or in the past."""


def resolve_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ReminderTimeError(f"Unknown timezone '{name}'. Use an IANA name such as 'Asia/Kolkata'.") from exc


def parse_due_at(due_at: str, tz_name: str, *, now: datetime | None = None) -> datetime:
    """Parse an ISO 8601 time (naive times use `tz_name`) into UTC; reject the past."""
    zone = resolve_zone(tz_name)
    try:
        parsed = datetime.fromisoformat(due_at.strip())
    except ValueError as exc:
        raise ReminderTimeError("due_at must be an ISO 8601 date-time, e.g. 2026-11-03T09:00:00.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    parsed_utc = parsed.astimezone(timezone.utc).replace(microsecond=0)

    current = now or datetime.now(timezone.utc)
    if parsed_utc < current - timedelta(minutes=1):
        local_now = current.astimezone(zone).isoformat(timespec="minutes")
        raise ReminderTimeError(f"That time has already passed. The current time is {local_now} ({tz_name}).")
    return parsed_utc


def present_reminder(row: dict, tz_name: str) -> dict:
    zone = resolve_zone(tz_name)
    local = datetime.fromisoformat(row["due_at"]).astimezone(zone)
    return {
        "id": row["id"],
        "title": row["title"],
        "notes": row.get("notes"),
        "due_local": local.isoformat(timespec="minutes"),
        "due_utc": row["due_at"],
        "timezone": tz_name,
    }


class RemindersAction(str, Enum):
    CREATE = "create"
    LIST = "list"
    DELETE = "delete"


class ListScope(str, Enum):
    UPCOMING = "upcoming"
    PAST = "past"
    ALL = "all"


class RemindersInput(BaseModel):
    action: RemindersAction = Field(..., description="create, list or delete.")
    title: str | None = Field(default=None, max_length=200, description="What to be reminded of (create).")
    due_at: str | None = Field(default=None, description="ISO 8601 date-time (create). Without an offset it is read in `timezone`.")
    timezone: str | None = Field(default=None, description="IANA timezone for a due_at without an offset. Defaults to the user's timezone.")
    notes: str | None = Field(default=None, max_length=2000, description="Optional extra detail (create).")
    reminder_id: int | None = Field(default=None, ge=1, description="Required for delete.")
    scope: ListScope = Field(default=ListScope.UPCOMING, description="Which reminders to list.")

    @model_validator(mode="after")
    def _check(self) -> "RemindersInput":
        if self.action == RemindersAction.CREATE and not ((self.title or "").strip() and self.due_at):
            raise ValueError("'title' and 'due_at' are required to create a reminder.")
        if self.action == RemindersAction.DELETE and self.reminder_id is None:
            raise ValueError("'reminder_id' is required to delete a reminder.")
        return self


class RemindersTool(BaseTool):
    name = "reminders"
    description = "Create, list and delete reminders. Resolve relative times like 'tomorrow 9am' before calling."
    permission_level = PermissionLevel.MEDIUM
    input_model = RemindersInput

    def __init__(self, store: SQLiteStore, default_timezone: str = "UTC"):
        self._store = store
        self._tz = default_timezone

    def permission_for(self, arguments: RemindersInput) -> PermissionLevel:
        if arguments.action == RemindersAction.LIST:
            return PermissionLevel.LOW
        return PermissionLevel.MEDIUM

    def describe_call(self, arguments: RemindersInput) -> str:
        if arguments.action == RemindersAction.CREATE:
            when = arguments.due_at or "the requested time"
            try:
                tz_name = arguments.timezone or self._tz
                local = parse_due_at(arguments.due_at, tz_name).astimezone(resolve_zone(tz_name))
                when = f"{local:%A %d %B} at {local:%H:%M}"
            except (ReminderTimeError, TypeError):
                pass
            return f"I can set a reminder to {arguments.title} for {when}"
        if arguments.action == RemindersAction.DELETE:
            return f"I can delete reminder number {arguments.reminder_id}"
        return "I can list your reminders"

    async def execute(self, arguments: RemindersInput) -> ToolResult:
        store = self._store
        tz_name = arguments.timezone or self._tz
        try:
            if arguments.action == RemindersAction.CREATE:
                due_utc = parse_due_at(arguments.due_at, tz_name)
                row = await store.run(
                    store.create_reminder, arguments.title.strip(), due_utc.isoformat(), arguments.notes
                )
                return ToolResult.ok({"reminder": present_reminder(row, tz_name)})

            if arguments.action == RemindersAction.LIST:
                rows = await store.run(store.list_reminders, arguments.scope.value, utc_now_iso())
                return ToolResult.ok(
                    {"count": len(rows), "reminders": [present_reminder(r, tz_name) for r in rows]}
                )
        except ReminderTimeError as exc:
            return ToolResult.fail(str(exc))

        deleted = await store.run(store.delete_reminder, arguments.reminder_id)
        if not deleted:
            return ToolResult.fail(f"There is no reminder with id {arguments.reminder_id}.")
        return ToolResult.ok({"deleted_reminder_id": arguments.reminder_id})
