import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.database.sqlite_store import SQLiteStore
from app.services.search import SearchError, SearchProvider, SearchResult
from app.tools.base import PermissionLevel
from app.tools.document_analyzer import DocumentAnalyzerTool
from app.tools.file_search import FileSearchTool
from app.tools.notes import NotesTool
from app.tools.registry import ToolRegistry
from app.tools.reminders import RemindersTool, ReminderTimeError, parse_due_at
from app.tools.weather import WeatherTool
from app.tools.web_search import WebSearchTool


class ToolTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = SQLiteStore(Path(self._tmp.name) / "t.db")
        self.registry = ToolRegistry()


class NotesToolTests(ToolTestCase):
    async def asyncSetUp(self):
        self.registry.register(NotesTool(self.store))

    async def test_lifecycle(self):
        created = await self.registry.execute("notes", {"action": "create", "content": "Buy milk\nand eggs"})
        self.assertTrue(created.success)
        note = created.data["note"]
        self.assertEqual(note["title"], "Buy milk")

        got = await self.registry.execute("notes", {"action": "get", "note_id": note["id"]})
        self.assertEqual(got.data["note"]["content"], "Buy milk\nand eggs")
        found = await self.registry.execute("notes", {"action": "search", "query": "eggs"})
        self.assertEqual(found.data["count"], 1)
        deleted = await self.registry.execute("notes", {"action": "delete", "note_id": note["id"]})
        self.assertTrue(deleted.success)
        again = await self.registry.execute("notes", {"action": "delete", "note_id": note["id"]})
        self.assertFalse(again.success)

    async def test_invalid_arguments_never_execute(self):
        for args in ({"action": "create"}, {"action": "get"}, {"action": "explode"}):
            result = await self.registry.execute("notes", args)
            self.assertFalse(result.success)
            self.assertIn("invalid arguments", result.error.lower())
        self.assertEqual(self.store.search_notes(None), [])


class RemindersToolTests(ToolTestCase):
    async def asyncSetUp(self):
        self.registry.register(RemindersTool(self.store, default_timezone="Asia/Kolkata"))

    def future(self, **delta):
        return (datetime.now(timezone.utc) + timedelta(**delta)).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    async def test_create_list_delete(self):
        created = await self.registry.execute(
            "reminders", {"action": "create", "title": "Call mom", "due_at": self.future(days=1)}
        )
        self.assertTrue(created.success, created.error)
        reminder = created.data["reminder"]
        self.assertTrue(reminder["due_local"].endswith("+05:30"))  # shown in the default timezone

        listed = await self.registry.execute("reminders", {"action": "list"})
        self.assertEqual(listed.data["count"], 1)
        self.assertTrue((await self.registry.execute("reminders", {"action": "delete", "reminder_id": reminder["id"]})).success)
        self.assertEqual((await self.registry.execute("reminders", {"action": "list"})).data["count"], 0)

    async def test_naive_time_uses_given_timezone(self):
        due = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT09:00:00")
        result = await self.registry.execute(
            "reminders", {"action": "create", "title": "x", "due_at": due, "timezone": "UTC"}
        )
        self.assertTrue(result.success, result.error)
        self.assertTrue(result.data["reminder"]["due_utc"].endswith("T09:00:00+00:00"))

    async def test_rejects_past_bad_and_unknown_zone(self):
        base = {"action": "create", "title": "x"}
        past = await self.registry.execute("reminders", {**base, "due_at": "2020-01-01T09:00:00+00:00"})
        self.assertIn("already passed", past.error)
        bad = await self.registry.execute("reminders", {**base, "due_at": "tomorrow morning"})
        self.assertIn("ISO 8601", bad.error)
        zone = await self.registry.execute("reminders", {**base, "due_at": self.future(days=1), "timezone": "Mars/Base"})
        self.assertIn("Unknown timezone", zone.error)
        self.assertEqual(self.store.list_reminders("all", "2000-01-01T00:00:00+00:00"), [])

    def test_parse_due_at_accepts_z_suffix(self):
        now = datetime(2026, 11, 2, tzinfo=timezone.utc)
        self.assertEqual(parse_due_at("2026-11-03T09:00:00Z", "UTC", now=now).hour, 9)
        with self.assertRaises(ReminderTimeError):
            parse_due_at("2026-11-01T09:00:00Z", "UTC", now=now)


class FakeSearch(SearchProvider):
    def __init__(self, results=None, error=None):
        self.results, self.error, self.calls = results or [], error, []

    async def search(self, query, *, max_results, recency=None):
        self.calls.append((query, max_results, recency))
        if self.error:
            raise self.error
        return self.results


class WebSearchToolTests(ToolTestCase):
    async def test_results_are_marked_untrusted(self):
        provider = FakeSearch([SearchResult("T", "https://x.test", "snippet")])
        self.registry.register(WebSearchTool(provider, default_max_results=5))
        result = await self.registry.execute("web_search", {"query": "ai agents", "recency": "week"})
        self.assertTrue(result.success)
        self.assertTrue(result.untrusted)
        self.assertEqual(result.data["results"][0]["url"], "https://x.test")
        self.assertEqual(provider.calls, [("ai agents", 5, "week")])

    async def test_any_recency_passes_none(self):
        provider = FakeSearch()
        self.registry.register(WebSearchTool(provider))
        await self.registry.execute("web_search", {"query": "q", "max_results": 3})
        self.assertEqual(provider.calls, [("q", 3, None)])

    async def test_provider_failure_is_reported_without_internals(self):
        self.registry.register(WebSearchTool(FakeSearch(error=SearchError("HTTP 429 secret-detail"))))
        result = await self.registry.execute("web_search", {"query": "q"})
        self.assertFalse(result.success)
        self.assertNotIn("secret-detail", result.error)


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, routes, error=None):
        self.routes, self.error, self.calls = routes, error, []

    async def get(self, url, params=None):
        self.calls.append((url, params))
        if self.error:
            raise self.error
        return FakeResponse(self.routes[url])


GEO = {"results": [
    {"name": "Springfield", "admin1": "Illinois", "country": "United States", "country_code": "US", "latitude": 1.0, "longitude": 2.0},
    {"name": "Springfield", "admin1": "Missouri", "country": "United States", "country_code": "US", "latitude": 3.0, "longitude": 4.0},
]}
FORECAST = {
    "timezone": "America/Chicago",
    "current_units": {"temperature_2m": "°C", "wind_speed_10m": "km/h"},
    "current": {"time": "2026-11-02T10:00", "temperature_2m": 12.5, "apparent_temperature": 11.0,
                "relative_humidity_2m": 60, "precipitation": 0.0, "weather_code": 61, "wind_speed_10m": 9.0},
    "daily": {"time": ["2026-11-02", "2026-11-03"], "weather_code": [3, 95],
              "temperature_2m_max": [14, 16], "temperature_2m_min": [6, 8],
              "precipitation_probability_max": [10, 80]},
}
GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


class WeatherToolTests(ToolTestCase):
    async def test_current_and_forecast(self):
        client = FakeClient({GEO_URL: GEO, FORECAST_URL: FORECAST})
        self.registry.register(WeatherTool(client))
        result = await self.registry.execute("weather", {"location": "Springfield, Missouri", "forecast_days": 2})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["location"], "Springfield, Missouri, United States")
        self.assertEqual(result.data["current"]["conditions"], "light rain")
        self.assertEqual([d["conditions"] for d in result.data["forecast"]], ["overcast", "thunderstorm"])
        forecast_call = client.calls[1][1]
        self.assertEqual((forecast_call["latitude"], forecast_call["forecast_days"]), (3.0, 2))  # hint picked Missouri

    async def test_imperial_units_and_no_forecast(self):
        client = FakeClient({GEO_URL: GEO, FORECAST_URL: FORECAST})
        self.registry.register(WeatherTool(client))
        result = await self.registry.execute("weather", {"location": "Springfield", "units": "imperial"})
        self.assertNotIn("forecast", result.data)
        self.assertEqual(client.calls[1][1]["temperature_unit"], "fahrenheit")

    async def test_unknown_place(self):
        self.registry.register(WeatherTool(FakeClient({GEO_URL: {}})))
        result = await self.registry.execute("weather", {"location": "Nowhereville"})
        self.assertFalse(result.success)
        self.assertIn("couldn't find", result.error)

    async def test_network_failure_is_generic(self):
        self.registry.register(WeatherTool(FakeClient({}, error=RuntimeError("socket exploded at 10.0.0.1"))))
        result = await self.registry.execute("weather", {"location": "Pune"})
        self.assertEqual(result.error, "The weather service is unavailable right now.")


class FileToolTests(ToolTestCase):
    async def asyncSetUp(self):
        self.registry.register(FileSearchTool(self.store))
        self.registry.register(DocumentAnalyzerTool(self.store))
        self.text = "Architecture overview. " + ("The system uses a queue. " * 400)
        self.fid = "a" * 32
        self.store.add_file(self.fid, "project_report.txt", self.fid + ".txt", "text/plain",
                            len(self.text), self.text, [self.text[:900], "Deployment uses containers."])

    async def test_search_marks_untrusted_and_returns_ids(self):
        result = await self.registry.execute("file_search", {"query": "project report"})
        self.assertTrue(result.untrusted)
        self.assertEqual(result.data["files"][0]["file_id"], self.fid)

    async def test_blank_search_lists_recent(self):
        result = await self.registry.execute("file_search", {})
        self.assertEqual(result.data["count"], 1)

    async def test_read_in_pages(self):
        first = await self.registry.execute("document_analyzer", {"file_id": self.fid, "max_chars": 500})
        self.assertTrue(first.untrusted)
        self.assertTrue(first.data["has_more"])
        self.assertEqual(first.data["returned_chars"], 500)
        second = await self.registry.execute(
            "document_analyzer", {"file_id": self.fid, "offset": first.data["next_offset"], "max_chars": 500}
        )
        self.assertEqual(second.data["offset"], 500)

    async def test_last_page_has_no_next_offset(self):
        result = await self.registry.execute(
            "document_analyzer", {"file_id": self.fid, "offset": len(self.text) - 100, "max_chars": 500}
        )
        self.assertFalse(result.data["has_more"])
        self.assertIsNone(result.data["next_offset"])

    async def test_focus_returns_relevant_passages(self):
        result = await self.registry.execute("document_analyzer", {"file_id": self.fid, "focus": "containers"})
        self.assertEqual(result.data["passages"], ["Deployment uses containers."])

    async def test_unknown_file(self):
        result = await self.registry.execute("document_analyzer", {"file_id": "nope"})
        self.assertFalse(result.success)
        self.assertIn("file_search", result.error)

    def test_permissions_are_low(self):
        self.assertEqual(self.registry.get("file_search").permission_level, PermissionLevel.LOW)


if __name__ == "__main__":
    unittest.main()
