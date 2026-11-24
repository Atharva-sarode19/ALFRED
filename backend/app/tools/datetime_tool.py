"""
Date/Time tool.

Supports: current date/time (optionally in a given IANA timezone),
converting a datetime between timezones, and simple date arithmetic
(adding/subtracting days/hours/minutes). Uses the stdlib `zoneinfo` module
for correct, DST-aware timezone handling -- no naive UTC-offset math.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, model_validator

from app.tools.base import BaseTool, PermissionLevel, ToolResult

_ISO_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def _resolve_zone(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            f"Unknown timezone '{tz_name}'. Use an IANA name, e.g. "
            "'Asia/Tokyo', 'America/New_York', 'UTC'."
        ) from exc


class DateTimeAction(str, Enum):
    CURRENT = "current"
    CONVERT = "convert"
    CALCULATE = "calculate"


class DateTimeInput(BaseModel):
    action: DateTimeAction = Field(
        default=DateTimeAction.CURRENT,
        description=(
            "'current' returns the current date/time in `timezone`. "
            "'convert' converts `datetime_iso` from `from_timezone` to "
            "`timezone`. 'calculate' adds `delta_days`/`delta_hours`/"
            "`delta_minutes` (any may be negative) to `datetime_iso` "
            "(or now, if omitted) in `timezone`."
        ),
    )
    timezone: str = Field(
        default="UTC",
        description="IANA timezone name, e.g. 'Asia/Tokyo', 'UTC', 'America/New_York'.",
    )
    from_timezone: str | None = Field(
        default=None,
        description="Source timezone for 'convert' (defaults to 'timezone' if omitted).",
    )
    datetime_iso: str | None = Field(
        default=None,
        description="ISO-8601 datetime string, required for 'convert' and optional for 'calculate'.",
    )
    delta_days: int = 0
    delta_hours: int = 0
    delta_minutes: int = 0

    @model_validator(mode="after")
    def _check_requirements(self) -> "DateTimeInput":
        if self.action == DateTimeAction.CONVERT and not self.datetime_iso:
            raise ValueError("'datetime_iso' is required for the 'convert' action.")
        return self


class DateTimeTool(BaseTool):
    name = "datetime"
    description = (
        "Get the current date/time in a timezone, convert a datetime between "
        "timezones, or perform date arithmetic (add/subtract days, hours, "
        "minutes)."
    )
    permission_level = PermissionLevel.LOW
    input_model = DateTimeInput

    async def execute(self, arguments: DateTimeInput) -> ToolResult:
        try:
            if arguments.action == DateTimeAction.CURRENT:
                return self._current(arguments)
            if arguments.action == DateTimeAction.CONVERT:
                return self._convert(arguments)
            return self._calculate(arguments)
        except ValueError as exc:
            return ToolResult.fail(str(exc))

    def _current(self, args: DateTimeInput) -> ToolResult:
        zone = _resolve_zone(args.timezone)
        now = datetime.now(zone)
        return ToolResult.ok(
            {
                "timezone": args.timezone,
                "iso": now.isoformat(),
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "weekday": now.strftime("%A"),
            }
        )

    def _convert(self, args: DateTimeInput) -> ToolResult:
        source_zone = _resolve_zone(args.from_timezone or args.timezone)
        target_zone = _resolve_zone(args.timezone)

        parsed = datetime.fromisoformat(args.datetime_iso)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=source_zone)

        converted = parsed.astimezone(target_zone)
        return ToolResult.ok(
            {
                "original": parsed.isoformat(),
                "converted": converted.isoformat(),
                "from_timezone": args.from_timezone or args.timezone,
                "to_timezone": args.timezone,
            }
        )

    def _calculate(self, args: DateTimeInput) -> ToolResult:
        zone = _resolve_zone(args.timezone)
        base = (
            datetime.fromisoformat(args.datetime_iso).replace(tzinfo=zone)
            if args.datetime_iso
            else datetime.now(zone)
        )
        result = base + timedelta(
            days=args.delta_days, hours=args.delta_hours, minutes=args.delta_minutes
        )
        return ToolResult.ok(
            {
                "base": base.isoformat(),
                "result": result.isoformat(),
                "delta_days": args.delta_days,
                "delta_hours": args.delta_hours,
                "delta_minutes": args.delta_minutes,
            }
        )
