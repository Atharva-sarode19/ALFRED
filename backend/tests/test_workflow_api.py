"""HTTP-level tests for /api/workflows and the `workflow` tool inside the chat loop (fake LLM, no network)."""

import time
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from app.agent.orchestrator import AgentOrchestrator
from app.agent.state import ConversationState
from app.api import deps
from app.main import app
from app.tools.workflow_tool import WorkflowTool
from tests.workflow_helpers import FakeLLM, SaveTool, build_registry, call, chain_plan, make_engine, plan_json, text

BAD_ID = "z" * 32
MISSING = "0" * 32


@pytest.fixture
def api():
    save = SaveTool()
    llm = FakeLLM([plan_json(chain_plan(3, {"t2": ["save"]}))], scripts={"t2": [call("save", text="n"), text("saved")]})
    engine = make_engine(llm, build_registry(save))
    app.dependency_overrides[deps.get_workflow_engine] = lambda: engine
    yield TestClient(app), engine, save, llm
    app.dependency_overrides.clear()


def create(client, **body):
    return client.post("/api/workflows", json={"request": "search, analyse and save a note", "wait": True, **body})


def test_create_runs_and_pauses_for_approval(api):
    client, _, save, _ = api
    res = create(client)
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "waiting_for_approval" and body["completed_tasks"] == 1 and body["total_tasks"] == 3
    waiting = next(t for t in body["tasks"] if t["status"] == "waiting_for_approval")
    assert waiting["pending_approval"]["tool_name"] == "save" and save.saved == []


def test_approve_resumes_and_completes(api):
    client, _, save, _ = api
    wf = create(client).json()
    call_id = next(t for t in wf["tasks"] if t["pending_approval"])["pending_approval"]["call_id"]
    done = client.post(f"/api/workflows/{wf['id']}/approve", json={"call_id": call_id, "wait": True}).json()
    assert done["status"] == "completed" and save.saved == ["n"]
    assert done["result"] == "done t3" and done["summary"].startswith("3 of 3")


def test_reject_never_runs_the_action(api):
    client, _, save, _ = api
    wf = create(client).json()
    res = client.post(f"/api/workflows/{wf['id']}/reject", json={"wait": True})
    assert res.status_code == 200
    body = res.json()
    assert save.saved == [] and body["status"] == "failed"
    assert {t["id"]: t["status"] for t in body["tasks"]} == {"t1": "completed", "t2": "cancelled", "t3": "blocked"}


def test_approve_with_stale_call_id_is_409(api):
    client, _, save, _ = api
    wf = create(client).json()
    res = client.post(f"/api/workflows/{wf['id']}/approve", json={"call_id": "forged"})
    assert res.status_code == 409 and save.saved == []


def test_approve_with_nothing_pending_is_409(api):
    client, _, _, _ = api
    wf = create(client).json()
    client.post(f"/api/workflows/{wf['id']}/approve", json={"wait": True})
    assert client.post(f"/api/workflows/{wf['id']}/approve", json={}).status_code == 409


def test_get_list_and_tasks(api):
    client, _, _, _ = api
    wf = create(client).json()
    one = client.get(f"/api/workflows/{wf['id']}").json()
    assert one["id"] == wf["id"] and one["events"]
    tasks = client.get(f"/api/workflows/{wf['id']}/tasks").json()
    assert [t["id"] for t in tasks] == ["t1", "t2", "t3"] and tasks[1]["dependencies"] == ["t1"]
    listing = client.get("/api/workflows").json()
    assert [w["id"] for w in listing] == [wf["id"]]
    assert "events" not in listing[0] and listing[0]["tasks"]
    assert client.get("/api/workflows", params={"status": "completed"}).json() == []
    assert client.get("/api/workflows", params={"status": "bogus"}).status_code == 422


def test_unknown_and_malformed_ids(api):
    client, _, _, _ = api
    assert client.get(f"/api/workflows/{MISSING}").status_code == 404
    assert client.get(f"/api/workflows/{BAD_ID}").status_code == 422
    assert client.post(f"/api/workflows/{BAD_ID}/cancel").status_code == 422
    assert client.post(f"/api/workflows/{MISSING}/cancel").status_code == 404
    assert client.post(f"/api/workflows/{MISSING}/approve", json={}).status_code == 404


def test_cancel_and_conflicts(api):
    client, _, save, _ = api
    wf = create(client).json()
    cancelled = client.post(f"/api/workflows/{wf['id']}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert save.saved == []
    assert client.post(f"/api/workflows/{wf['id']}/cancel").status_code == 409
    assert client.post(f"/api/workflows/{wf['id']}/resume", json={}).status_code == 409


def test_resume_while_waiting_for_approval_is_409(api):
    client, _, save, _ = api
    wf = create(client).json()
    assert client.post(f"/api/workflows/{wf['id']}/resume", json={}).status_code == 409
    assert save.saved == []


def test_validation_of_create_request(api):
    client, _, _, _ = api
    assert client.post("/api/workflows", json={"request": ""}).status_code == 422
    assert client.post("/api/workflows", json={}).status_code == 422


def test_planning_failure_is_502_with_safe_message():
    engine = make_engine(FakeLLM(["not json"]))
    app.dependency_overrides[deps.get_workflow_engine] = lambda: engine
    try:
        res = TestClient(app).post("/api/workflows", json={"request": "x"})
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 502 and "valid plan" in res.json()["detail"]


def test_background_run_without_wait():
    llm = FakeLLM([plan_json(chain_plan(2))])
    engine = make_engine(llm)
    app.dependency_overrides[deps.get_workflow_engine] = lambda: engine
    try:
        with TestClient(app) as client:
            res = client.post("/api/workflows", json={"request": "x"})
            assert res.status_code == 201
            wid = res.json()["id"]
            for _ in range(100):
                body = client.get(f"/api/workflows/{wid}").json()
                if body["status"] == "completed":
                    break
                time.sleep(0.05)
            assert body["status"] == "completed"
    finally:
        app.dependency_overrides.clear()


def test_real_default_registry_gets_the_workflow_tool(tmp_path, monkeypatch):
    monkeypatch.setenv("ALFRED_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(deps, "_store", None)
    with mock.patch.object(deps, "_registry", None), mock.patch.object(deps, "_engine", None), \
            mock.patch.object(deps, "_memory", None), mock.patch.object(deps, "_memory_built", True):
        registry = deps.get_tool_registry()
        names = {t.name for t in registry.list_tools()}
        assert {"workflow", "calculator", "web_search", "notes", "weather"} <= names
        assert deps.get_workflow_engine() is deps._engine


# ---------------------------------------------------------------- the workflow tool in the chat loop
async def test_chat_triggers_a_workflow_via_function_calling():
    registry = build_registry(SaveTool())
    task_llm = FakeLLM([plan_json(chain_plan(2))])
    engine = make_engine(task_llm, registry)
    registry.register(WorkflowTool(engine, wait_seconds=5))

    from app.services.llm import GenerationResult

    class Chat(FakeLLM):
        """The chat model calls the workflow tool, then answers from its result."""

        def __init__(self):
            super().__init__()
            self.turn = 0

        async def generate_with_tools(self, messages, tools, *, system_instruction=None):
            self.turn += 1
            if self.turn == 1:
                return call("workflow", action="start", request="research and summarise")
            return GenerationResult(text="Workflow finished.")

    chat_llm = Chat()
    orchestrator = AgentOrchestrator(
        chat_llm, registry, workflow_context=engine.context_block
    )
    state = ConversationState(session_id="chat-1")
    result = await orchestrator.process(state, "Research three frameworks and summarise")
    assert result.response_text == "Workflow finished."
    assert any(s.stage == "tool_result" and "workflow" in s.detail for s in result.trace)
    (wf,) = await engine.list(conversation_id="chat-1")  # tied to the chat session
    assert wf.status.value == "completed" and wf.completed_tasks == 2

    # next turn: the model is told about the workflow through the context block
    block = await engine.context_block("chat-1")
    assert wf.id in block


async def test_tool_status_result_cancel_and_errors():
    registry = build_registry(SaveTool())
    engine = make_engine(FakeLLM([plan_json(chain_plan(2))]), registry)
    tool = WorkflowTool(engine, wait_seconds=5)
    registry.register(tool)

    assert (await registry.execute("workflow", {"action": "status"})).error == "There is no workflow to refer to yet."
    assert not (await registry.execute("workflow", {"action": "start"})).success  # request required
    started = await registry.execute("workflow", {"action": "start", "request": "do it"})
    assert started.success and started.data["status"] == "completed" and started.data["result"] == "done t2"
    assert started.untrusted  # results derive from tools/web content
    status = await registry.execute("workflow", {"action": "status"})
    assert status.data["progress"] == "2/2 tasks completed" and "result" not in status.data
    assert (await registry.execute("workflow", {"action": "result"})).data["result"] == "done t2"
    cancel = await registry.execute("workflow", {"action": "cancel"})
    assert not cancel.success and "already" in cancel.error


async def test_tool_has_no_approval_action():
    from app.tools.workflow_tool import WorkflowAction

    assert {a.value for a in WorkflowAction} == {"start", "status", "result", "resume", "cancel"}
