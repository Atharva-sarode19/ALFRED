"""
Calculator tool.

Evaluates arithmetic expressions using a restricted AST walker -- never
Python's `eval()`. Only numeric literals and a fixed whitelist of
operators/functions are permitted; anything else (names, attribute access,
calls to non-whitelisted functions, etc.) is rejected before evaluation.
"""

from __future__ import annotations

import ast
import math
import operator

from pydantic import BaseModel, Field

from app.tools.base import BaseTool, PermissionLevel, ToolResult

# Whitelisted binary/unary operators.
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
# Whitelisted "safe" functions/constants callable inside expressions.
_SAFE_FUNCTIONS = {
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
    "log": math.log,
    "log10": math.log10,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "floor": math.floor,
    "ceil": math.ceil,
}
_SAFE_CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
}

_MAX_EXPRESSION_LENGTH = 200


class UnsafeExpressionError(ValueError):
    """Raised when an expression contains anything outside the whitelist."""


def safe_eval(expression: str) -> float:
    """Safely evaluate a numeric expression string. Never uses eval()."""
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise UnsafeExpressionError("Expression is too long.")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise UnsafeExpressionError(f"Could not parse expression: {exc}") from exc

    return _eval_node(tree.body)


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise UnsafeExpressionError(f"Unsupported constant: {node.value!r}")

    if isinstance(node, ast.BinOp):
        op_fn = _BIN_OPS.get(type(node.op))
        if op_fn is None:
            raise UnsafeExpressionError(f"Operator {type(node.op).__name__} is not allowed.")
        return op_fn(_eval_node(node.left), _eval_node(node.right))

    if isinstance(node, ast.UnaryOp):
        op_fn = _UNARY_OPS.get(type(node.op))
        if op_fn is None:
            raise UnsafeExpressionError(f"Unary operator {type(node.op).__name__} is not allowed.")
        return op_fn(_eval_node(node.operand))

    if isinstance(node, ast.Name):
        if node.id in _SAFE_CONSTANTS:
            return _SAFE_CONSTANTS[node.id]
        raise UnsafeExpressionError(f"Name '{node.id}' is not allowed.")

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _SAFE_FUNCTIONS:
            raise UnsafeExpressionError("Only whitelisted functions may be called.")
        if node.keywords:
            raise UnsafeExpressionError("Keyword arguments are not allowed.")
        args = [_eval_node(arg) for arg in node.args]
        return _SAFE_FUNCTIONS[node.func.id](*args)

    raise UnsafeExpressionError(f"Expression node type {type(node).__name__} is not allowed.")


class CalculatorInput(BaseModel):
    expression: str = Field(
        ...,
        description=(
            "A mathematical expression to evaluate, e.g. '17% of 84000' should "
            "be provided as '0.17 * 84000'. Supports + - * / // % **, "
            "parentheses, and sqrt/abs/round/log/log10/sin/cos/tan/floor/ceil, "
            "plus the constants pi and e."
        ),
    )


class CalculatorTool(BaseTool):
    name = "calculator"
    description = (
        "Evaluate a mathematical expression and return the numeric result. "
        "Use this for arithmetic, percentages (expressed as decimals, e.g. "
        "17% -> 0.17), and basic functions like sqrt, log, sin, cos, tan."
    )
    permission_level = PermissionLevel.LOW
    input_model = CalculatorInput

    async def execute(self, arguments: CalculatorInput) -> ToolResult:
        try:
            result = safe_eval(arguments.expression)
        except UnsafeExpressionError as exc:
            return ToolResult.fail(str(exc))
        except ZeroDivisionError:
            return ToolResult.fail("Division by zero.")
        except (ValueError, OverflowError) as exc:
            return ToolResult.fail(f"Math error: {exc}")

        return ToolResult.ok({"expression": arguments.expression, "result": result})
