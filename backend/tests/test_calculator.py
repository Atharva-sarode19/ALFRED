import pytest

from app.tools.calculator import CalculatorInput, CalculatorTool, UnsafeExpressionError, safe_eval


def test_safe_eval_basic_arithmetic():
    assert safe_eval("2 + 3 * 4") == 14


def test_safe_eval_percentage_style():
    assert safe_eval("0.17 * 84000") == pytest.approx(14280.0)


def test_safe_eval_functions_and_constants():
    assert safe_eval("sqrt(16)") == 4
    assert safe_eval("round(pi, 2)") == 3.14


def test_safe_eval_rejects_names():
    with pytest.raises(UnsafeExpressionError):
        safe_eval("__import__('os')")


def test_safe_eval_rejects_arbitrary_calls():
    with pytest.raises(UnsafeExpressionError):
        safe_eval("os.system('ls')")


def test_safe_eval_rejects_too_long_expression():
    with pytest.raises(UnsafeExpressionError):
        safe_eval("1+" * 500 + "1")


@pytest.mark.asyncio
async def test_calculator_tool_execute_success():
    tool = CalculatorTool()
    args = tool.validate_arguments({"expression": "17 * 2"})
    result = await tool.execute(args)
    assert result.success
    assert result.data["result"] == 34


@pytest.mark.asyncio
async def test_calculator_tool_execute_division_by_zero():
    tool = CalculatorTool()
    args = CalculatorInput(expression="1/0")
    result = await tool.execute(args)
    assert not result.success
    assert "zero" in result.error.lower()
