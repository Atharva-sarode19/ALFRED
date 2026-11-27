import tempfile
from pathlib import Path

import pytest

from app.database.sqlite_store import SQLiteStore
from app.tools.base import PermissionLevel
from app.tools.registry import ToolNotFoundError, build_default_registry

EXPECTED_TOOLS = {
    "calculator",
    "datetime",
    "web_search",
    "weather",
    "notes",
    "reminders",
    "file_search",
    "document_analyzer",
}


def make_registry():
    """The real default registry, backed by a throwaway SQLite file."""
    tmp = tempfile.mkdtemp(prefix="alfred-test-")
    return build_default_registry(store=SQLiteStore(Path(tmp) / "test.db"))


def test_default_registry_has_all_tools():
    registry = make_registry()
    assert {t.name for t in registry.list_tools()} == EXPECTED_TOOLS


def test_get_tool_definitions_shapes_for_llm():
    registry = make_registry()
    defs = registry.get_tool_definitions()
    calc_def = next(d for d in defs if d.name == "calculator")
    assert "expression" in calc_def.parameters["properties"]


def test_unknown_tool_raises_not_found():
    registry = make_registry()
    with pytest.raises(ToolNotFoundError):
        registry.get("send_email")


@pytest.mark.asyncio
async def test_execute_rejects_non_allowlisted_tool():
    registry = make_registry()
    result = await registry.execute("delete_everything", {})
    assert not result.success
    assert "not allowed" in result.error.lower()


@pytest.mark.asyncio
async def test_execute_rejects_invalid_arguments():
    registry = make_registry()
    # calculator requires "expression"; omit it.
    result = await registry.execute("calculator", {})
    assert not result.success
    assert "invalid arguments" in result.error.lower()


@pytest.mark.asyncio
async def test_execute_runs_valid_call():
    registry = make_registry()
    result = await registry.execute("calculator", {"expression": "2+2"})
    assert result.success
    assert result.data["result"] == 4


def test_every_tool_schema_is_gemini_safe():
    """Optional and enum fields must survive the Gemini schema cleaner (no $ref/anyOf left)."""
    from app.services.gemini import _clean_schema_for_gemini

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                assert key not in {"$ref", "$defs", "anyOf", "allOf", "oneOf"}, key
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for definition in make_registry().get_tool_definitions():
        cleaned = _clean_schema_for_gemini(definition.parameters)
        assert cleaned["type"] == "object"
        walk(cleaned)


def test_permissions_are_per_action():
    level = make_registry().permission_for_call
    assert level("notes", {"action": "search"}) == PermissionLevel.LOW
    assert level("notes", {"action": "create", "content": "x"}) == PermissionLevel.MEDIUM
    assert level("notes", {"action": "delete", "note_id": 1}) == PermissionLevel.HIGH
    assert level("reminders", {"action": "list"}) == PermissionLevel.LOW
    assert level("notes", {"action": "get"}) is None  # invalid: note_id missing


def test_confirmation_rules():
    registry = make_registry()
    create = {"action": "create", "content": "x"}
    delete = {"action": "delete", "note_id": 1}
    assert registry.requires_confirmation("notes", create)
    assert not registry.requires_confirmation("notes", create, confirm_medium=False)
    assert registry.requires_confirmation("notes", delete, confirm_medium=False)  # HIGH always asks
    assert not registry.requires_confirmation("calculator", {"expression": "1+1"})
