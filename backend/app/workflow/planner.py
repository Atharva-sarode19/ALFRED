"""
Task planning.

Asks the LLM (through the provider abstraction) to break a request into tasks with
explicit dependencies, then validates the result. The planner only plans: it never
calls tools and never executes anything.
"""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from app.services.llm import LLMProvider, LLMProviderError, Message, Role
from app.tools.registry import ToolRegistry
from app.workflow.models import Plan
from app.workflow.validation import PlanValidationError, validate_plan

logger = logging.getLogger("alfred.workflow.planner")

PLANNER_INSTRUCTION = (
    "You are the planning component of ALFRED, an AI assistant. Break the user's request into a short "
    "list of concrete tasks that can be carried out one at a time. Reply with ONLY a JSON object, no "
    "prose and no code fences, in exactly this shape:\n"
    '{"title": "<short title>", "tasks": [{"id": "t1", "description": "<what to do>", '
    '"depends_on": [], "tools": ["<tool name>"], "expected_outcome": "<what this task produces>"}]}\n'
    "Rules:\n"
    "- Task ids are short and unique (t1, t2, ...). depends_on lists the ids of tasks whose results this task needs; "
    "a task with no prerequisites has an empty list. Never create circular dependencies.\n"
    "- Use at most {max_tasks} tasks, and as few as the request genuinely needs.\n"
    "- tools lists only names from the available tools below that the task is likely to need; use an empty list "
    "when a task only needs reasoning over earlier results (for example comparing or summarising).\n"
    "- End with a task that produces the final answer for the user.\n"
    "- Do not invent facts and do not include private reasoning.\n\n"
    "Available tools:\n{tools}"
)


class PlanningError(RuntimeError):
    """A usable plan could not be produced."""


def extract_json(text: str) -> dict:
    """Parse the first JSON object in `text`, tolerating code fences and surrounding prose."""
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("The reply contained no JSON object.")
    value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("The reply was not a JSON object.")
    return value


class WorkflowPlanner:
    def __init__(self, llm: LLMProvider, tools: ToolRegistry, *, max_tasks: int = 15, max_attempts: int = 2):
        self._llm = llm
        self._tools = tools
        self._max_tasks = max_tasks
        self._max_attempts = max(1, max_attempts)

    def _instruction(self, exclude: set[str]) -> str:
        listing = "\n".join(f"- {t.name}: {t.description}" for t in self._tools.list_tools() if t.name not in exclude)
        return PLANNER_INSTRUCTION.replace("{max_tasks}", str(self._max_tasks)).replace("{tools}", listing or "(none)")

    async def plan(self, request: str, *, exclude_tools: set[str] | None = None) -> Plan:
        exclude = exclude_tools or set()
        known = {t.name for t in self._tools.list_tools()} - exclude
        messages = [Message(role=Role.USER, content=f"Request:\n{request}")]
        instruction = self._instruction(exclude)
        last_problem = "no attempt made"

        for attempt in range(1, self._max_attempts + 1):
            try:
                result = await self._llm.generate(messages, system_instruction=instruction)
            except LLMProviderError as exc:
                logger.error("Planner LLM call failed: %s", exc)
                raise PlanningError("I couldn't reach the language model to plan that request.") from exc
            text = result.text or ""
            try:
                plan = Plan.model_validate(extract_json(text))
                validate_plan(plan, max_tasks=self._max_tasks, known_tools=known)
                return plan
            except (ValueError, ValidationError, PlanValidationError) as exc:
                last_problem = str(exc)
                logger.warning("Plan attempt %s rejected: %s", attempt, last_problem)
                messages += [
                    Message(role=Role.ASSISTANT, content=text),
                    Message(
                        role=Role.USER,
                        content=f"That plan was rejected: {last_problem[:600]}\nReply again with a corrected JSON object only.",
                    ),
                ]
        raise PlanningError(f"I couldn't build a valid plan for that request ({last_problem[:200]}).")
