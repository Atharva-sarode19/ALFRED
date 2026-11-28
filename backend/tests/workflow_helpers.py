"""Shared fakes for the Phase 5 workflow tests: no Gemini key and no network are ever needed."""

from __future__ import annotations

import json
import re

from pydantic import BaseModel

from app.services.llm import GenerationResult, LLMProvider, ToolCallRequest
from app.tools.base import BaseTool, PermissionLevel, ToolResult
from app.tools.registry import ToolRegistry
from app.workflow.engine import EngineConfig, WorkflowEngine
from app.workflow.models import Plan, PlannedTask
from app.workflow.store import InMemoryWorkflowStore

_STEP = re.compile(r"This step \(([A-Za-z0-9_-]+)\)")


def call(name: str, tool_id: str = "c1", **arguments) -> GenerationResult:
    return GenerationResult(text=None, tool_calls=[ToolCallRequest(id=tool_id, name=name, arguments=arguments)])


def text(value: str) -> GenerationResult:
    return GenerationResult(text=value)


class FakeLLM(LLMProvider):
    """Planner calls (`generate`) return `plan_replies`; task calls (`generate_with_tools`) follow `scripts[task_id]`.

    A script item is a GenerationResult to return or an Exception to raise. When a task's script runs out
    the model simply answers "done <task id>".
    """

    def __init__(self, plan_replies: list[str] | None = None, scripts: dict[str, list] | None = None):
        self.plan_replies = list(plan_replies or [])
        self.scripts = {k: list(v) for k, v in (scripts or {}).items()}
        self.plan_calls = 0
        self.task_calls: dict[str, int] = {}
        self.prompts: dict[str, str] = {}
        self.order: list[str] = []

    async def generate(self, messages, *, system_instruction=None):
        self.plan_calls += 1
        reply = self.plan_replies[min(self.plan_calls - 1, len(self.plan_replies) - 1)]
        return text(reply)

    async def generate_with_tools(self, messages, tools, *, system_instruction=None):
        first = next(m.content for m in messages if m.content)
        match = _STEP.search(first)
        task_id = match.group(1) if match else "?"
        self.prompts.setdefault(task_id, first)
        self.task_calls[task_id] = self.task_calls.get(task_id, 0) + 1
        if self.task_calls[task_id] == 1:
            self.order.append(task_id)
        script = self.scripts.get(task_id)
        if script:
            item = script.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        return text(f"done {task_id}")


class EchoInput(BaseModel):
    value: str = "x"


class EchoTool(BaseTool):
    name = "echo"
    description = "Read-only echo."
    permission_level = PermissionLevel.LOW
    input_model = EchoInput

    async def execute(self, arguments):
        return ToolResult.ok({"echo": arguments.value})


class FlakyTool(EchoTool):
    name = "flaky"
    description = "Always fails."

    async def execute(self, arguments):
        return ToolResult.fail("backend exploded")


class SaveInput(BaseModel):
    text: str = ""


class SaveTool(BaseTool):
    """A MEDIUM-permission tool with a visible side effect, standing in for notes/reminders."""

    name = "save"
    description = "Save something."
    permission_level = PermissionLevel.MEDIUM
    input_model = SaveInput

    def __init__(self):
        self.saved: list[str] = []

    def describe_call(self, arguments):
        return f"I can save '{arguments.text}'"

    async def execute(self, arguments):
        self.saved.append(arguments.text)
        return ToolResult.ok({"saved": arguments.text})


def build_registry(*extra: BaseTool) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in (EchoTool(), FlakyTool(), *extra):
        registry.register(tool)
    return registry


def chain_plan(n: int = 3, tools: dict[str, list[str]] | None = None) -> Plan:
    """t1 <- t2 <- t3 ..."""
    tools = tools or {}
    return Plan(
        title="Chain",
        tasks=[
            PlannedTask(
                id=f"t{i}", description=f"step {i}", depends_on=[f"t{i - 1}"] if i > 1 else [],
                tools=tools.get(f"t{i}", []), expected_outcome=f"outcome {i}",
            )
            for i in range(1, n + 1)
        ],
    )


def plan_json(plan: Plan) -> str:
    return json.dumps(
        {
            "title": plan.title,
            "tasks": [
                {"id": t.id, "description": t.description, "depends_on": t.depends_on, "tools": t.tools,
                 "expected_outcome": t.expected_outcome}
                for t in plan.tasks
            ],
        }
    )


def make_engine(llm: LLMProvider, registry: ToolRegistry | None = None, store=None, **config) -> WorkflowEngine:
    config.setdefault("retry_delay", 0)
    return WorkflowEngine(
        llm, registry or build_registry(), store or InMemoryWorkflowStore(), EngineConfig(**config)
    )
