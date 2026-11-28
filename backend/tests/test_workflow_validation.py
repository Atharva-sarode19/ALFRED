import pytest

from app.workflow.models import (
    InvalidTransition,
    Plan,
    PlannedTask,
    TaskStatus,
    Workflow,
    WorkflowStatus,
    WorkflowTask,
)
from app.workflow.validation import (
    PlanValidationError,
    blocked_by,
    find_cycle,
    leaf_tasks,
    ready_tasks,
    validate_plan,
    validate_workflow,
)


def plan(*tasks: tuple[str, list[str]]) -> Plan:
    return Plan(tasks=[PlannedTask(id=i, description=f"do {i}", depends_on=d) for i, d in tasks])


def workflow(*tasks: tuple[str, list[str]]) -> Workflow:
    return Workflow(request="r", tasks=[WorkflowTask(id=i, description=i, dependencies=d) for i, d in tasks])


def test_valid_plan_passes():
    validate_plan(plan(("a", []), ("b", ["a"]), ("c", ["a", "b"])))


def test_empty_plan_rejected():
    with pytest.raises(PlanValidationError, match="no tasks"):
        validate_plan(Plan(tasks=[]))


def test_duplicate_ids_rejected():
    with pytest.raises(PlanValidationError, match="Duplicate task id 'a'"):
        validate_plan(plan(("a", []), ("a", [])))


@pytest.mark.parametrize("bad", ["", "has space", "-lead", "x" * 41, "a/b"])
def test_invalid_ids_rejected(bad):
    with pytest.raises(PlanValidationError, match="Invalid task id"):
        validate_plan(plan((bad, [])))


def test_missing_dependency_rejected():
    with pytest.raises(PlanValidationError, match="missing task 'zzz'"):
        validate_plan(plan(("a", ["zzz"])))


def test_self_dependency_rejected():
    with pytest.raises(PlanValidationError, match="depends on itself"):
        validate_plan(plan(("a", ["a"])))


def test_duplicate_dependency_rejected():
    with pytest.raises(PlanValidationError, match="more than once"):
        validate_plan(plan(("a", []), ("b", ["a", "a"])))


def test_circular_dependency_rejected():
    with pytest.raises(PlanValidationError, match="Circular dependency: a -> c -> b -> a"):
        validate_plan(plan(("a", ["c"]), ("b", ["a"]), ("c", ["b"])))


def test_find_cycle_none_for_dag_and_ignores_missing_nodes():
    assert find_cycle({"a": [], "b": ["a"], "c": ["a", "b"]}) is None
    assert find_cycle({"a": ["ghost"]}) is None


def test_too_many_tasks_rejected():
    with pytest.raises(PlanValidationError, match="at most 2"):
        validate_plan(plan(("a", []), ("b", []), ("c", [])), max_tasks=2)


def test_unknown_tool_rejected_only_when_tools_are_known():
    p = Plan(tasks=[PlannedTask(id="a", description="x", tools=["nope"])])
    validate_plan(p)
    with pytest.raises(PlanValidationError, match="unknown tool 'nope'"):
        validate_plan(p, known_tools={"echo"})


def test_all_problems_are_reported_together():
    with pytest.raises(PlanValidationError) as exc:
        validate_plan(plan(("a", ["ghost"]), ("a", [])))
    assert len(exc.value.problems) >= 2


def test_workflow_validation_blocks_cycles():
    with pytest.raises(PlanValidationError):
        validate_workflow(workflow(("a", ["b"]), ("b", ["a"])))


def test_ready_tasks_use_explicit_dependencies_not_list_order():
    wf = workflow(("c", ["a", "b"]), ("b", ["a"]), ("a", []))
    assert [t.id for t in ready_tasks(wf)] == ["a"]
    wf.task("a").status = TaskStatus.COMPLETED
    assert [t.id for t in ready_tasks(wf)] == ["b"]
    wf.task("b").status = TaskStatus.COMPLETED
    assert [t.id for t in ready_tasks(wf)] == ["c"]


def test_independent_tasks_are_all_ready():
    wf = workflow(("a", []), ("b", []), ("c", ["a", "b"]))
    assert {t.id for t in ready_tasks(wf)} == {"a", "b"}


def test_running_and_failed_dependencies_do_not_unblock():
    wf = workflow(("a", []), ("b", ["a"]))
    for status in (TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.WAITING_FOR_APPROVAL, TaskStatus.RETRYING):
        wf.task("a").status = status
        assert ready_tasks(wf) == []


def test_blocked_by_is_transitive():
    wf = workflow(("a", []), ("b", ["a"]), ("c", ["b"]), ("d", []))
    wf.task("a").status = TaskStatus.FAILED
    assert blocked_by(wf) == {"b": "a", "c": "b"}


def test_leaf_tasks():
    wf = workflow(("a", []), ("b", ["a"]), ("c", ["a"]))
    assert {t.id for t in leaf_tasks(wf)} == {"b", "c"}


def test_task_state_transitions():
    task = WorkflowTask(id="a", description="x")
    task.transition(TaskStatus.READY)
    task.transition(TaskStatus.RUNNING)
    task.transition(TaskStatus.COMPLETED)
    for status in TaskStatus:
        if status != TaskStatus.COMPLETED:
            with pytest.raises(InvalidTransition):
                task.transition(status)


def test_task_cannot_skip_to_completed():
    task = WorkflowTask(id="a", description="x")
    with pytest.raises(InvalidTransition):
        task.transition(TaskStatus.COMPLETED)


def test_workflow_state_transitions():
    wf = Workflow(request="r")
    wf.transition(WorkflowStatus.PLANNING)
    wf.transition(WorkflowStatus.READY)
    wf.transition(WorkflowStatus.RUNNING)
    wf.transition(WorkflowStatus.WAITING_FOR_APPROVAL)
    wf.transition(WorkflowStatus.RUNNING)
    wf.transition(WorkflowStatus.COMPLETED)
    assert wf.completed_at is not None
    with pytest.raises(InvalidTransition):
        wf.transition(WorkflowStatus.RUNNING)


def test_cancelled_workflow_is_final():
    wf = Workflow(request="r", status=WorkflowStatus.RUNNING)
    wf.transition(WorkflowStatus.CANCELLED)
    with pytest.raises(InvalidTransition):
        wf.transition(WorkflowStatus.RUNNING)


def test_progress_fields():
    wf = workflow(("a", []), ("b", ["a"]))
    wf.task("a").status = TaskStatus.COMPLETED
    dumped = wf.model_dump()
    assert (dumped["completed_tasks"], dumped["total_tasks"]) == (1, 2)
