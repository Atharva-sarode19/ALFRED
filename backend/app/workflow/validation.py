"""
Plan and workflow validation and dependency analysis.

Pure functions: a plan is checked before any workflow is created, and a workflow
is re-checked before it runs, so a cyclic or malformed graph can never execute.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.workflow.models import (
    TASK_DONE_STATES,
    Plan,
    TaskStatus,
    Workflow,
    WorkflowTask,
)

TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")


class PlanValidationError(ValueError):
    """The plan or workflow is structurally invalid. `problems` lists every issue found."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


def find_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    """A cycle as a list of ids (first == last), or None. `graph` maps task id -> its dependencies."""
    WHITE, GREY, BLACK = 0, 1, 2
    color = {node: WHITE for node in graph}
    for root in graph:
        if color[root] != WHITE:
            continue
        stack: list[tuple[str, Iterable[str]]] = [(root, iter(graph[root]))]
        path = [root]
        color[root] = GREY
        while stack:
            node, children = stack[-1]
            advanced = False
            for child in children:
                if child not in color:
                    continue  # missing dependency: reported separately
                if color[child] == GREY:
                    return path[path.index(child):] + [child]
                if color[child] == WHITE:
                    color[child] = GREY
                    path.append(child)
                    stack.append((child, iter(graph[child])))
                    advanced = True
                    break
            if not advanced:
                color[node] = BLACK
                path.pop()
                stack.pop()
    return None


def _problems(
    items: list[tuple[str, str, list[str], list[str]]],
    *,
    max_tasks: int,
    known_tools: set[str] | None,
) -> list[str]:
    """`items` are (id, description, dependencies, tools)."""
    problems: list[str] = []
    if not items:
        return ["The plan has no tasks."]
    if len(items) > max_tasks:
        problems.append(f"The plan has {len(items)} tasks but at most {max_tasks} are allowed.")

    seen: set[str] = set()
    for task_id, description, _deps, tools in items:
        if not TASK_ID_PATTERN.match(task_id or ""):
            problems.append(f"Invalid task id {task_id!r}: use letters, digits, '_' or '-' (max 40 characters).")
        if task_id in seen:
            problems.append(f"Duplicate task id '{task_id}'.")
        seen.add(task_id)
        if not (description or "").strip():
            problems.append(f"Task '{task_id}' has no description.")
        if known_tools is not None:
            for tool in tools:
                if tool not in known_tools:
                    problems.append(f"Task '{task_id}' names an unknown tool '{tool}'.")

    for task_id, _description, deps, _tools in items:
        if len(set(deps)) != len(deps):
            problems.append(f"Task '{task_id}' lists a dependency more than once.")
        for dep in deps:
            if dep == task_id:
                problems.append(f"Task '{task_id}' depends on itself.")
            elif dep not in seen:
                problems.append(f"Task '{task_id}' depends on missing task '{dep}'.")

    if not problems:
        cycle = find_cycle({task_id: deps for task_id, _d, deps, _t in items})
        if cycle:
            problems.append("Circular dependency: " + " -> ".join(cycle) + ".")
    return problems


def validate_plan(plan: Plan, *, max_tasks: int = 15, known_tools: set[str] | None = None) -> None:
    items = [(t.id, t.description, list(t.depends_on), list(t.tools)) for t in plan.tasks]
    problems = _problems(items, max_tasks=max_tasks, known_tools=known_tools)
    if problems:
        raise PlanValidationError(problems)


def validate_workflow(workflow: Workflow, *, max_tasks: int = 15) -> None:
    items = [(t.id, t.description, list(t.dependencies), list(t.tools)) for t in workflow.tasks]
    problems = _problems(items, max_tasks=max_tasks, known_tools=None)
    if problems:
        raise PlanValidationError(problems)


def ready_tasks(workflow: Workflow) -> list[WorkflowTask]:
    """Tasks that may start now: not started yet and every dependency COMPLETED (explicit edges, not list order)."""
    done = {t.id for t in workflow.tasks if t.status == TaskStatus.COMPLETED}
    return [
        t
        for t in workflow.tasks
        if t.status in (TaskStatus.PENDING, TaskStatus.READY) and all(dep in done for dep in t.dependencies)
    ]


def blocked_by(workflow: Workflow) -> dict[str, str]:
    """Not-yet-started tasks that can never run because a dependency failed, was cancelled or is blocked.

    Maps task id -> the id of an upstream task that stopped the chain. Transitive: resolved to a fixpoint.
    """
    dead = {t.id for t in workflow.tasks if t.status in (TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.BLOCKED)}
    result: dict[str, str] = {}
    changed = True
    while changed:
        changed = False
        for task in workflow.tasks:
            if task.id in dead or task.status not in (TaskStatus.PENDING, TaskStatus.READY):
                continue
            culprit = next((dep for dep in task.dependencies if dep in dead), None)
            if culprit is not None:
                result[task.id] = culprit
                dead.add(task.id)
                changed = True
    return result


def leaf_tasks(workflow: Workflow) -> list[WorkflowTask]:
    """Tasks nothing else depends on: their results make up the workflow's final result."""
    needed = {dep for t in workflow.tasks for dep in t.dependencies}
    return [t for t in workflow.tasks if t.id not in needed]


def all_done(workflow: Workflow) -> bool:
    return all(t.status in TASK_DONE_STATES for t in workflow.tasks)
