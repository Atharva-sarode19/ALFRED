import asyncio

import pytest

from app.services.llm import LLMAuthenticationError, LLMRateLimitError, LLMUnavailableError
from app.tools.calculator import CalculatorTool
from app.tools.registry import ToolRegistry
from app.workflow.engine import WorkflowNotFound, WorkflowStateError
from app.workflow.models import Plan, PlannedTask, TaskStatus, WorkflowStatus
from app.workflow.store import InMemoryWorkflowStore
from app.workflow.validation import PlanValidationError
from tests.workflow_helpers import (
    FakeLLM,
    SaveTool,
    build_registry,
    call,
    chain_plan,
    make_engine,
    plan_json,
    text,
)

W, T = WorkflowStatus, TaskStatus


def statuses(wf):
    return {t.id: t.status for t in wf.tasks}


async def created(engine, plan=None, **kw):
    return await engine.create_from_plan("do the thing", plan or chain_plan(3), **kw)


# ---------------------------------------------------------------- creation
async def test_create_plans_with_llm_and_persists_ready_workflow():
    llm = FakeLLM([plan_json(chain_plan(3))])
    engine = make_engine(llm)
    wf = await engine.create("Research X and summarise", conversation_id="s1")
    assert wf.status == W.READY and wf.conversation_id == "s1"
    assert [t.id for t in wf.tasks] == ["t1", "t2", "t3"]
    assert wf.task("t1").status == T.READY and wf.task("t2").status == T.PENDING
    kinds = [e.kind for e in wf.events]
    assert kinds[:1] == ["workflow_created"] and "plan_generated" in kinds and "tasks_identified" in kinds
    assert (await engine.get(wf.id)).title == "Chain"


async def test_invalid_plan_never_becomes_a_runnable_workflow():
    engine = make_engine(FakeLLM())
    cyc = Plan(tasks=[PlannedTask(id="a", description="x", depends_on=["b"]), PlannedTask(id="b", description="y", depends_on=["a"])])
    with pytest.raises(PlanValidationError):
        await engine.create_from_plan("r", cyc)


async def test_failed_planning_is_recorded_not_left_planning():
    engine = make_engine(FakeLLM(["nonsense"]))
    from app.workflow.planner import PlanningError

    with pytest.raises(PlanningError):
        await engine.create("x")
    (wf,) = await engine.list()
    assert wf.status == W.FAILED and wf.failure


async def test_unknown_workflow_is_not_found():
    with pytest.raises(WorkflowNotFound):
        await make_engine(FakeLLM()).get("0" * 32)


# ---------------------------------------------------------------- sequential execution
async def test_runs_in_dependency_order_and_completes():
    llm = FakeLLM()
    engine = make_engine(llm)
    wf = await created(engine)
    done = await engine.run(wf.id)
    assert done.status == W.COMPLETED
    assert llm.order == ["t1", "t2", "t3"]
    assert all(s == T.COMPLETED for s in statuses(done).values())
    assert done.completed_tasks == 3
    assert done.result == "done t3"  # result of the leaf task
    assert "3 of 3 tasks completed" in done.summary
    kinds = [e.kind for e in done.events]
    assert kinds.count("task_started") == 3 and kinds[-1] == "workflow_completed"


async def test_dependency_results_are_passed_downstream_as_untrusted_data():
    llm = FakeLLM(scripts={"t1": [text("FINDINGS ALPHA")]})
    engine = make_engine(llm)
    wf = await created(engine, chain_plan(2))
    await engine.run(wf.id)
    assert "FINDINGS ALPHA" in llm.prompts["t2"]
    assert "UNTRUSTED_CONTENT" in llm.prompts["t2"]
    assert "FINDINGS ALPHA" not in llm.prompts["t1"]


async def test_task_uses_existing_tool_registry_and_records_tool_trace():
    llm = FakeLLM(scripts={"t1": [call("echo", value="hi"), text("echoed hi")]})
    engine = make_engine(llm)
    wf = await created(engine, chain_plan(1, {"t1": ["echo"]}))
    done = await engine.run(wf.id)
    assert done.task("t1").result_summary == "echoed hi"
    kinds = [e.kind for e in done.events]
    assert "tool_selected" in kinds and "tool_result" in kinds


async def test_real_calculator_tool_through_workflow():
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    llm = FakeLLM(scripts={"t1": [call("calculator", expression="6*7"), text("42")]})
    engine = make_engine(llm, registry)
    wf = await engine.create_from_plan("math", chain_plan(1, {"t1": ["calculator"]}))
    done = await engine.run(wf.id)
    assert done.status == W.COMPLETED and done.task("t1").result_summary == "42"
    assert any("calculator" in e.message and e.kind == "tool_result" for e in done.events)


async def test_workflow_tool_is_not_available_inside_tasks():
    from tests.workflow_helpers import EchoTool

    class FakeWorkflowTool(EchoTool):
        name = "workflow"

    registry = build_registry(FakeWorkflowTool())
    engine = make_engine(FakeLLM(), registry)
    assert not engine._task_registry().is_allowed("workflow")  # noqa: SLF001
    assert engine._task_registry().is_allowed("echo")  # noqa: SLF001


# ---------------------------------------------------------------- failure, blocking, recovery
async def test_failed_task_blocks_dependents_but_independent_work_continues():
    plan = Plan(tasks=[
        PlannedTask(id="a", description="a"),
        PlannedTask(id="b", description="b", depends_on=["a"]),
        PlannedTask(id="c", description="c", depends_on=["b"]),
        PlannedTask(id="d", description="independent"),
    ])
    llm = FakeLLM(scripts={"a": [LLMAuthenticationError("bad key")]})
    engine = make_engine(llm)
    done = await engine.run((await engine.create_from_plan("r", plan)).id)
    assert statuses(done) == {"a": T.FAILED, "b": T.BLOCKED, "c": T.BLOCKED, "d": T.COMPLETED}
    assert done.status == W.FAILED
    assert "b" not in llm.task_calls and "c" not in llm.task_calls
    assert "credentials" in done.task("a").error
    assert "Traceback" not in (done.failure or "") and "bad key" not in (done.failure or "")
    assert "Blocked" in done.summary and "Failed" in done.summary
    assert done.task("b").error.startswith("Blocked because task 'a'")


async def test_transient_llm_error_is_retried_then_succeeds():
    llm = FakeLLM(scripts={"t1": [LLMRateLimitError("429"), LLMUnavailableError("503"), text("ok")]})
    engine = make_engine(llm, max_task_retries=2)
    done = await engine.run((await created(engine, chain_plan(1))).id)
    assert done.status == W.COMPLETED
    assert done.task("t1").attempts == 3
    kinds = [e.kind for e in done.events]
    assert kinds.count("task_retrying") == 2 and kinds.count("task_retry_started") == 2
    assert "Retried" in done.summary


async def test_retries_are_bounded():
    llm = FakeLLM(scripts={"t1": [LLMUnavailableError("503")] * 10})
    engine = make_engine(llm, max_task_retries=2)
    done = await engine.run((await created(engine, chain_plan(2))).id)
    assert llm.task_calls["t1"] == 3  # 1 attempt + 2 retries
    assert done.task("t1").status == T.FAILED and done.task("t2").status == T.BLOCKED
    assert done.status == W.FAILED


async def test_zero_retries_means_one_attempt():
    llm = FakeLLM(scripts={"t1": [LLMUnavailableError("503")] * 5})
    engine = make_engine(llm, max_task_retries=0)
    await engine.run((await created(engine, chain_plan(1))).id)
    assert llm.task_calls["t1"] == 1


async def test_permanent_llm_error_is_not_retried():
    llm = FakeLLM(scripts={"t1": [LLMAuthenticationError("bad")] * 5})
    engine = make_engine(llm, max_task_retries=3)
    await engine.run((await created(engine, chain_plan(1))).id)
    assert llm.task_calls["t1"] == 1


async def test_no_automatic_retry_after_a_side_effect():
    """The note was saved (after approval), then the model failed: retrying could save it twice."""
    save = SaveTool()
    llm = FakeLLM(scripts={"t1": [call("save", text="x"), LLMUnavailableError("503"), text("late")]})
    engine = make_engine(llm, build_registry(save), max_task_retries=3, confirm_medium=False)
    done = await engine.run((await created(engine, chain_plan(1, {"t1": ["save"]}))).id)
    assert save.saved == ["x"]
    assert done.task("t1").status == T.FAILED and llm.task_calls["t1"] == 2


async def test_unexpected_exception_fails_the_task_safely():
    class Boom(FakeLLM):
        async def generate_with_tools(self, messages, tools, *, system_instruction=None):
            raise RuntimeError("secret internal detail /etc/passwd")

    engine = make_engine(Boom())
    done = await engine.run((await created(engine, chain_plan(1))).id)
    assert done.task("t1").status == T.FAILED
    assert "secret" not in done.task("t1").error and "passwd" not in " ".join(e.message for e in done.events)


async def test_tool_failure_is_surfaced_in_trace_and_model_can_explain():
    llm = FakeLLM(scripts={"t1": [call("flaky"), text("The tool failed, sorry.")]})
    engine = make_engine(llm)
    done = await engine.run((await created(engine, chain_plan(1))).id)
    assert done.status == W.COMPLETED
    assert any(e.kind == "tool_result" and "failed" in e.message for e in done.events)


async def test_iteration_limit_fails_task_without_retry():
    llm = FakeLLM(scripts={"t1": [call("echo", tool_id=f"c{i}") for i in range(10)]})
    engine = make_engine(llm, max_iterations=2, max_task_retries=2)
    done = await engine.run((await created(engine, chain_plan(1))).id)
    assert done.task("t1").status == T.FAILED and "limit" in done.task("t1").error
    assert llm.task_calls["t1"] == 2


async def test_timeout_stops_scheduling_and_leaves_rest_resumable():
    class Slow(FakeLLM):
        async def generate_with_tools(self, messages, tools, *, system_instruction=None):
            await asyncio.sleep(0.3)
            return await super().generate_with_tools(messages, tools, system_instruction=system_instruction)

    engine = make_engine(Slow(), timeout_seconds=1)
    stopped = await engine.run((await engine.create_from_plan("r", chain_plan(8))).id)
    assert stopped.status == W.FAILED
    assert any(t.status == T.COMPLETED for t in stopped.tasks)
    assert stopped.task("t8").status in (T.PENDING, T.READY, T.BLOCKED)
    assert "time limit" in stopped.failure or "Stopped after 1 seconds" in stopped.failure or stopped.failure


# ---------------------------------------------------------------- approvals
async def approval_workflow(save=None, **kw):
    save = save or SaveTool()
    llm = FakeLLM(scripts={"t2": [call("save", text="meeting notes"), text("note saved")]})
    engine = make_engine(llm, build_registry(save), **kw)
    wf = await engine.create_from_plan("search, analyse, save a note", chain_plan(3, {"t2": ["save"]}))
    return engine, llm, save, wf


async def test_task_pauses_for_approval_and_nothing_runs_before_it():
    engine, llm, save, wf = await approval_workflow()
    paused = await engine.run(wf.id)
    assert paused.status == W.WAITING_FOR_APPROVAL
    assert statuses(paused) == {"t1": T.COMPLETED, "t2": T.WAITING_FOR_APPROVAL, "t3": T.PENDING}
    assert save.saved == []
    pending = paused.task("t2").pending_approval
    assert pending.tool_name == "save" and pending.arguments == {"text": "meeting notes"} and pending.decision is None
    assert "t3" not in llm.task_calls
    assert any(e.kind == "permission_requested" for e in paused.events)


async def test_approval_executes_exact_stored_call_and_resumes():
    engine, llm, save, wf = await approval_workflow()
    await engine.run(wf.id)
    await engine.approve(wf.id, call_id="c1")
    done = await engine.run(wf.id)
    assert done.status == W.COMPLETED and save.saved == ["meeting notes"]
    assert llm.order == ["t1", "t2", "t3"]
    kinds = [e.kind for e in done.events]
    assert "approval_received" in kinds and "task_resumed" in kinds


async def test_resuming_without_approval_does_nothing():
    engine, _, save, wf = await approval_workflow()
    await engine.run(wf.id)
    with pytest.raises(WorkflowStateError, match="waiting for your approval"):
        await engine.resume(wf.id)
    assert save.saved == []


async def test_stale_call_id_is_rejected():
    engine, _, save, wf = await approval_workflow()
    await engine.run(wf.id)
    with pytest.raises(WorkflowStateError, match="out of date"):
        await engine.approve(wf.id, call_id="some-other-call")
    assert save.saved == []


async def test_approve_when_nothing_waits_is_an_error():
    engine = make_engine(FakeLLM())
    wf = await created(engine)
    with pytest.raises(WorkflowStateError):
        await engine.approve(wf.id)


async def test_rejection_never_runs_the_action_and_blocks_dependents():
    engine, llm, save, wf = await approval_workflow()
    await engine.run(wf.id)
    await engine.reject(wf.id)
    done = await engine.run(wf.id)
    assert save.saved == []
    assert statuses(done) == {"t1": T.COMPLETED, "t2": T.CANCELLED, "t3": T.BLOCKED}
    assert done.status == W.FAILED and "declined" in done.failure.lower() + done.task("t2").error.lower()
    assert "t3" not in llm.task_calls
    assert any(e.kind == "approval_rejected" for e in done.events)
    with pytest.raises(WorkflowStateError):
        await engine.resume(done.id)  # a declined action is never silently retried


async def test_medium_permission_runs_without_approval_when_policy_disabled():
    engine, _, save, wf = await approval_workflow(confirm_medium=False)
    done = await engine.run(wf.id)
    assert done.status == W.COMPLETED and save.saved == ["meeting notes"]


async def test_second_approval_in_same_task():
    save = SaveTool()
    llm = FakeLLM(scripts={"t1": [call("save", tool_id="a", text="one"), call("save", tool_id="b", text="two"), text("both")]})
    engine = make_engine(llm, build_registry(save))
    wf = await engine.create_from_plan("r", chain_plan(1))
    first = await engine.run(wf.id)
    assert first.task("t1").pending_approval.arguments == {"text": "one"}
    await engine.approve(wf.id)
    second = await engine.run(wf.id)
    assert second.status == W.WAITING_FOR_APPROVAL and second.task("t1").pending_approval.arguments == {"text": "two"}
    assert save.saved == ["one"]
    await engine.approve(wf.id)
    assert (await engine.run(wf.id)).status == W.COMPLETED and save.saved == ["one", "two"]


async def test_approval_survives_restart_via_persisted_record():
    save = SaveTool()
    store = InMemoryWorkflowStore()
    llm = FakeLLM(scripts={"t2": [call("save", text="persisted"), text("unused")]})
    engine = make_engine(llm, build_registry(save), store=store)
    wf = await engine.create_from_plan("r", chain_plan(3, {"t2": ["save"]}))
    await engine.run(wf.id)
    assert save.saved == []

    llm2 = FakeLLM(scripts={"t2": [text("finished after restart")]})
    engine2 = make_engine(llm2, build_registry(save), store=store)  # brand-new process: no in-memory state
    reloaded = await engine2.get(wf.id)
    assert reloaded.status == W.WAITING_FOR_APPROVAL
    await engine2.approve(wf.id)
    done = await engine2.run(wf.id)
    assert done.status == W.COMPLETED
    assert save.saved == ["persisted"]  # the exact stored call ran exactly once
    assert "persisted" in llm2.prompts["t2"]


# ---------------------------------------------------------------- cancellation
async def test_cancel_before_start_cancels_every_task():
    engine = make_engine(FakeLLM())
    wf = await created(engine)
    cancelled = await engine.cancel(wf.id)
    assert cancelled.status == W.CANCELLED
    assert all(s == T.CANCELLED for s in statuses(cancelled).values())
    assert [e.kind for e in cancelled.events].count("workflow_cancelled") == 1
    assert len(cancelled.events) >= 3  # history preserved
    with pytest.raises(WorkflowStateError):
        await engine.cancel(wf.id)
    assert (await engine.run(wf.id)).status == W.CANCELLED


async def test_cancel_while_waiting_for_approval_never_runs_action():
    engine, _, save, wf = await approval_workflow()
    await engine.run(wf.id)
    cancelled = await engine.cancel(wf.id)
    assert cancelled.status == W.CANCELLED and save.saved == []
    assert statuses(cancelled) == {"t1": T.COMPLETED, "t2": T.CANCELLED, "t3": T.CANCELLED}
    with pytest.raises(WorkflowStateError):
        await engine.approve(wf.id)


async def test_cancel_mid_run_stops_scheduling_and_preserves_history():
    gate = asyncio.Event()

    class Gated(FakeLLM):
        async def generate_with_tools(self, messages, tools, *, system_instruction=None):
            result = await super().generate_with_tools(messages, tools, system_instruction=system_instruction)
            if self.task_calls.get("t1") == 1 and "t1" in self.order and len(self.order) == 1:
                gate.set()
                await asyncio.sleep(30)
            return result

    llm = Gated()
    engine = make_engine(llm)
    wf = await created(engine)
    run = engine.spawn(wf.id)
    await asyncio.wait_for(gate.wait(), 5)
    cancelled = await engine.cancel(wf.id)
    await asyncio.wait([run], timeout=5)
    final = await engine.get(wf.id)
    assert cancelled.status == W.CANCELLED and final.status == W.CANCELLED
    assert statuses(final) == {"t1": T.CANCELLED, "t2": T.CANCELLED, "t3": T.CANCELLED}
    assert llm.order == ["t1"]
    assert "may have completed" in final.task("t1").error
    assert any(e.kind == "task_started" for e in final.events)


# ---------------------------------------------------------------- resume / continuation
async def test_retry_failed_resets_failed_and_blocked_tasks_explicitly():
    llm = FakeLLM(scripts={"t1": [LLMAuthenticationError("x")]})
    engine = make_engine(llm)
    failed = await engine.run((await created(engine, chain_plan(3))).id)
    assert failed.status == W.FAILED
    with pytest.raises(WorkflowStateError, match="nothing left to resume"):
        await engine.resume(failed.id)  # failures are never retried implicitly
    await engine.resume(failed.id, retry_failed=True)
    done = await engine.run(failed.id)
    assert done.status == W.COMPLETED and done.task("t1").attempts == 2
    assert any(e.kind == "tasks_reset" for e in done.events)


async def test_resume_completed_workflow_is_rejected():
    engine = make_engine(FakeLLM())
    done = await engine.run((await created(engine, chain_plan(1))).id)
    with pytest.raises(WorkflowStateError, match="already completed"):
        await engine.resume(done.id)


async def test_resume_continues_only_unfinished_tasks_after_interruption():
    store = InMemoryWorkflowStore()
    engine = make_engine(FakeLLM(), store=store)
    wf = await created(engine)
    # Simulate a crash: t1 finished, t2 was mid-flight, the process died.
    live = engine._live[wf.id]  # noqa: SLF001
    live.transition(W.RUNNING)
    live.task("t1").transition(T.RUNNING)
    live.task("t1").transition(T.COMPLETED)
    live.task("t1").result_summary = "earlier result"
    live.task("t2").transition(T.RUNNING)
    await store.save(live)

    llm = FakeLLM()
    engine2 = make_engine(llm, store=store)
    with pytest.raises(WorkflowStateError):
        await engine2.resume(wf.id)  # interrupted work is not re-run without an explicit retry
    prepared = await engine2.get(wf.id)
    assert prepared.task("t2").status == T.FAILED and "Interrupted" in prepared.task("t2").error
    await engine2.resume(wf.id, retry_failed=True)
    done = await engine2.run(wf.id)
    assert done.status == W.COMPLETED
    assert "t1" not in llm.task_calls  # already completed: not run again
    assert "earlier result" in llm.prompts["t2"]


async def test_resume_when_run_is_active_is_a_noop():
    gate = asyncio.Event()

    class Slow(FakeLLM):
        async def generate_with_tools(self, messages, tools, *, system_instruction=None):
            gate.set()
            await asyncio.sleep(0.2)
            return await super().generate_with_tools(messages, tools, system_instruction=system_instruction)

    engine = make_engine(Slow())
    wf = await created(engine, chain_plan(1))
    run = engine.spawn(wf.id)
    await gate.wait()
    assert engine.spawn(wf.id) is run  # one run per workflow
    await engine.resume(wf.id)
    await run
    assert (await engine.get(wf.id)).task("t1").attempts == 1


# ---------------------------------------------------------------- concurrency
async def test_default_is_sequential_even_for_independent_tasks():
    active, peak = 0, 0

    class Probe(FakeLLM):
        async def generate_with_tools(self, messages, tools, *, system_instruction=None):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.05)
            active -= 1
            return await super().generate_with_tools(messages, tools, system_instruction=system_instruction)

    plan = Plan(tasks=[PlannedTask(id=i, description=i, tools=["echo"]) for i in "abc"])
    engine = make_engine(Probe())
    await engine.run((await engine.create_from_plan("r", plan)).id)
    assert peak == 1


async def test_concurrency_only_for_independent_read_only_tasks():
    active, peak = 0, 0

    class Probe(FakeLLM):
        async def generate_with_tools(self, messages, tools, *, system_instruction=None):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.05)
            active -= 1
            return await super().generate_with_tools(messages, tools, system_instruction=system_instruction)

    plan = Plan(tasks=[
        PlannedTask(id="a", description="a", tools=["echo"]),
        PlannedTask(id="b", description="b", tools=["echo"]),
        PlannedTask(id="c", description="c", depends_on=["a", "b"]),
    ])
    engine = make_engine(Probe(), concurrency=3)
    done = await engine.run((await engine.create_from_plan("r", plan)).id)
    assert peak == 2 and done.status == W.COMPLETED

    peak = 0  # tasks that may write (MEDIUM tool) or declare no tools never run concurrently
    plan2 = Plan(tasks=[PlannedTask(id="a", description="a", tools=["save"]), PlannedTask(id="b", description="b", tools=["save"])])
    engine2 = make_engine(Probe(), build_registry(SaveTool()), concurrency=3, confirm_medium=False)
    await engine2.run((await engine2.create_from_plan("r", plan2)).id)
    assert peak == 1


# ---------------------------------------------------------------- persistence / retrieval / context
async def test_every_change_is_persisted_and_retrievable():
    store = InMemoryWorkflowStore()
    engine = make_engine(FakeLLM(), store=store)
    wf = await created(engine)
    await engine.run(wf.id)
    fresh = make_engine(FakeLLM(), store=store)
    loaded = await fresh.get(wf.id)
    assert loaded.status == W.COMPLETED and loaded.completed_tasks == 3
    assert [t.dependencies for t in loaded.tasks] == [[], ["t1"], ["t2"]]
    assert loaded.task("t3").result_summary == "done t3"
    assert [w.id for w in await fresh.list()] == [wf.id]
    assert (await fresh.list(status="failed")) == []


async def test_context_block_describes_conversation_workflows_only():
    engine, _, _, wf = await approval_workflow()
    # workflow belongs to no conversation yet
    assert await engine.context_block("s1") is None
    wf2 = await engine.create_from_plan("r", chain_plan(2), conversation_id="s1")
    await engine.run(wf.id)
    block = await engine.context_block("s1")
    assert wf2.id in block and wf.id not in block
    assert "0/2 tasks done" in block
    assert await engine.context_block(None) is None


async def test_context_block_reports_pending_approval_and_failures():
    engine, _, _, _ = await approval_workflow()
    wf = await engine.create_from_plan("save a note", chain_plan(3, {"t2": ["save"]}), conversation_id="s9")
    await engine.run(wf.id)
    assert "waiting for the user's approval" in await engine.context_block("s9")


async def test_latest_for_prefers_conversation():
    engine = make_engine(FakeLLM())
    a = await engine.create_from_plan("r", chain_plan(1), conversation_id="s1")
    await engine.create_from_plan("r", chain_plan(1), conversation_id="s2")
    assert (await engine.latest_for("s1")).id == a.id
