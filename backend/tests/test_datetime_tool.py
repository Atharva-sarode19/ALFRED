import pytest

from app.tools.datetime_tool import DateTimeInput, DateTimeTool


@pytest.mark.asyncio
async def test_current_time_in_timezone():
    tool = DateTimeTool()
    args = DateTimeInput(action="current", timezone="Asia/Tokyo")
    result = await tool.execute(args)
    assert result.success
    assert result.data["timezone"] == "Asia/Tokyo"
    assert "T" in result.data["iso"]


@pytest.mark.asyncio
async def test_convert_between_timezones():
    tool = DateTimeTool()
    args = DateTimeInput(
        action="convert",
        datetime_iso="2026-01-15T09:00:00",
        from_timezone="UTC",
        timezone="Asia/Tokyo",
    )
    result = await tool.execute(args)
    assert result.success
    # Tokyo is UTC+9, no DST.
    assert result.data["converted"].startswith("2026-01-15T18:00:00")


@pytest.mark.asyncio
async def test_calculate_date_arithmetic():
    tool = DateTimeTool()
    args = DateTimeInput(
        action="calculate",
        datetime_iso="2026-01-01T00:00:00",
        timezone="UTC",
        delta_days=10,
    )
    result = await tool.execute(args)
    assert result.success
    assert result.data["result"].startswith("2026-01-11")


@pytest.mark.asyncio
async def test_unknown_timezone_fails_gracefully():
    tool = DateTimeTool()
    args = DateTimeInput(action="current", timezone="Not/AZone")
    result = await tool.execute(args)
    assert not result.success
    assert "Unknown timezone" in result.error


def test_convert_requires_datetime_iso():
    with pytest.raises(ValueError):
        DateTimeInput(action="convert")
