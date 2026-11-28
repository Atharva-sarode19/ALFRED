import json

import pytest

from app.services.llm import LLMUnavailableError
from app.workflow.planner import PlanningError, WorkflowPlanner, extract_json
from tests.workflow_helpers import FakeLLM, build_registry, chain_plan, plan_json


class ExplodingLLM(FakeLLM):
    async def generate(self, messages, *, system_instruction=None):
        raise LLMUnavailableError("down")


def planner(llm, **kw):
    return WorkflowPlanner(llm, build_registry(), **kw)


def test_extract_json_handles_fences_and_prose():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Here you go: {"a": {"b": 2}} thanks') == {"a": {"b": 2}}
    with pytest.raises(ValueError):
        extract_json("no json here")


async def test_valid_plan_is_returned():
    llm = FakeLLM([plan_json(chain_plan(3, {"t1": ["echo"]}))])
    plan = await planner(llm).plan("research things")
    assert [t.id for t in plan.tasks] == ["t1", "t2", "t3"]
    assert plan.tasks[1].depends_on == ["t1"]
    assert llm.plan_calls == 1


async def test_plan_is_generated_not_canned():
    llm_a = FakeLLM([plan_json(chain_plan(2))])
    llm_b = FakeLLM([plan_json(chain_plan(4))])
    assert len((await planner(llm_a).plan("x")).tasks) == 2
    assert len((await planner(llm_b).plan("y")).tasks) == 4


async def test_cyclic_plan_is_repaired_once():
    cyclic = json.dumps({"tasks": [
        {"id": "a", "description": "x", "depends_on": ["b"]}, {"id": "b", "description": "y", "depends_on": ["a"]}]})
    llm = FakeLLM([cyclic, plan_json(chain_plan(2))])
    plan = await planner(llm).plan("x")
    assert llm.plan_calls == 2
    assert len(plan.tasks) == 2


async def test_unknown_tool_in_plan_is_rejected_then_fails():
    bad = json.dumps({"tasks": [{"id": "a", "description": "x", "tools": ["rm_rf"]}]})
    llm = FakeLLM([bad])
    with pytest.raises(PlanningError):
        await planner(llm).plan("x")
    assert llm.plan_calls == 2  # bounded: one repair attempt, then give up


async def test_garbage_reply_fails_cleanly():
    with pytest.raises(PlanningError):
        await planner(FakeLLM(["I cannot do that"])).plan("x")


async def test_llm_outage_is_a_planning_error():
    with pytest.raises(PlanningError, match="language model"):
        await planner(ExplodingLLM()).plan("x")


async def test_workflow_tool_is_not_offered_to_planner():
    seen = {}

    class Spy(FakeLLM):
        async def generate(self, messages, *, system_instruction=None):
            seen["instruction"] = system_instruction
            return await super().generate(messages, system_instruction=system_instruction)

    await planner(Spy([plan_json(chain_plan(1))])).plan("x", exclude_tools={"echo"})
    assert "- flaky:" in seen["instruction"] and "- echo:" not in seen["instruction"]
