import pytest

from app.tools.registry import ToolNotFoundError, build_default_registry


def test_default_registry_has_calculator_and_datetime():
    registry = build_default_registry()
    names = {t.name for t in registry.list_tools()}
    assert names == {"calculator", "datetime"}


def test_get_tool_definitions_shapes_for_llm():
    registry = build_default_registry()
    defs = registry.get_tool_definitions()
    calc_def = next(d for d in defs if d.name == "calculator")
    assert "expression" in calc_def.parameters["properties"]


def test_unknown_tool_raises_not_found():
    registry = build_default_registry()
    with pytest.raises(ToolNotFoundError):
        registry.get("send_email")


@pytest.mark.asyncio
async def test_execute_rejects_non_allowlisted_tool():
    registry = build_default_registry()
    result = await registry.execute("delete_everything", {})
    assert not result.success
    assert "not allowed" in result.error.lower()


@pytest.mark.asyncio
async def test_execute_rejects_invalid_arguments():
    registry = build_default_registry()
    # calculator requires "expression"; omit it.
    result = await registry.execute("calculator", {})
    assert not result.success
    assert "invalid arguments" in result.error.lower()


@pytest.mark.asyncio
async def test_execute_runs_valid_call():
    registry = build_default_registry()
    result = await registry.execute("calculator", {"expression": "2+2"})
    assert result.success
    assert result.data["result"] == 4
