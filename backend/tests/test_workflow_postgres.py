"""
Workflow persistence against a real PostgreSQL database.

Set TEST_DATABASE_URL to a *disposable* database (the workflow tables are emptied for every test).
Without it these tests are skipped.
"""

import os
import unittest

from app.database import migrator
from app.database.postgres import PostgresManager
from app.memory.coordinator import MemoryCoordinator
from app.workflow.models import TaskStatus, WorkflowStatus
from app.workflow.store import PostgresWorkflowStore
from tests.workflow_helpers import FakeLLM, SaveTool, build_registry, call, chain_plan, make_engine, text

DSN = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(DSN, "TEST_DATABASE_URL is not set")
class PostgresWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = PostgresManager(DSN, min_size=1, max_size=4, connect_timeout=5)
        migrator.migrate(self.db)
        with self.db.connection() as conn:
            conn.execute("TRUNCATE workflows CASCADE")
        self.addCleanup(self.db.close)
        self.store = PostgresWorkflowStore(self.db)

    def test_migration_adds_only_workflow_tables(self):
        self.assertIn("002", migrator.applied_versions(self.db))
        self.assertEqual(migrator.migrate(self.db), [])
        with self.db.connection() as conn:
            tables = {r["tablename"] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
        self.assertTrue({"workflows", "workflow_tasks", "workflow_events", "memories", "tasks", "messages"} <= tables)

    async def test_full_workflow_round_trips_through_postgres(self):
        engine = make_engine(FakeLLM(), store=self.store)
        wf = await engine.create_from_plan("persist me", chain_plan(3), conversation_id="conv-1")
        done = await engine.run(wf.id)
        self.assertEqual(done.status, WorkflowStatus.COMPLETED)

        fresh = make_engine(FakeLLM(), store=PostgresWorkflowStore(self.db))
        loaded = await fresh.get(wf.id)
        self.assertEqual(loaded.status, WorkflowStatus.COMPLETED)
        self.assertEqual(loaded.conversation_id, "conv-1")
        self.assertEqual([t.dependencies for t in loaded.tasks], [[], ["t1"], ["t2"]])
        self.assertEqual([t.status for t in loaded.tasks], [TaskStatus.COMPLETED] * 3)
        self.assertEqual(loaded.task("t3").result_summary, "done t3")
        self.assertEqual(loaded.task("t1").attempts, 1)
        self.assertEqual([e.seq for e in loaded.events], list(range(1, len(loaded.events) + 1)))
        self.assertEqual(loaded.summary, done.summary)
        self.assertIsNotNone(loaded.completed_at)

        listed = await fresh.list(conversation_id="conv-1")
        self.assertEqual([w.id for w in listed], [wf.id])
        self.assertEqual(listed[0].events, [])
        self.assertEqual(await fresh.list(status="failed"), [])

    async def test_approval_state_survives_restart_and_resumes(self):
        save = SaveTool()
        llm = FakeLLM(scripts={"t2": [call("save", text="pg note"), text("x")]})
        engine = make_engine(llm, build_registry(save), store=self.store)
        wf = await engine.create_from_plan("r", chain_plan(3, {"t2": ["save"]}))
        paused = await engine.run(wf.id)
        self.assertEqual(paused.status, WorkflowStatus.WAITING_FOR_APPROVAL)

        engine2 = make_engine(FakeLLM(scripts={"t2": [text("finished")]}), build_registry(save), store=PostgresWorkflowStore(self.db))
        reloaded = await engine2.get(wf.id)
        pending = reloaded.task("t2").pending_approval
        self.assertEqual((pending.tool_name, pending.arguments, pending.decision), ("save", {"text": "pg note"}, None))
        await engine2.approve(wf.id)
        done = await engine2.run(wf.id)
        self.assertEqual(done.status, WorkflowStatus.COMPLETED)
        self.assertEqual(save.saved, ["pg note"])
        stored = await PostgresWorkflowStore(self.db).get(wf.id)
        self.assertEqual(stored.task("t2").pending_approval.decision, "approved")

    async def test_failure_and_cancellation_are_persisted(self):
        from app.services.llm import LLMAuthenticationError

        engine = make_engine(FakeLLM(scripts={"t1": [LLMAuthenticationError("k")]}), store=self.store)
        wf = await engine.create_from_plan("r", chain_plan(2))
        await engine.run(wf.id)
        stored = await self.store.get(wf.id)
        self.assertEqual((stored.status, stored.task("t1").status, stored.task("t2").status),
                         (WorkflowStatus.FAILED, TaskStatus.FAILED, TaskStatus.BLOCKED))
        self.assertIn("credentials", stored.task("t1").error)

        other = await engine.create_from_plan("r2", chain_plan(2))
        await engine.cancel(other.id)
        self.assertEqual((await self.store.get(other.id)).status, WorkflowStatus.CANCELLED)

    async def test_phase4_memory_data_is_untouched_by_workflow_tables(self):
        memory = MemoryCoordinator(self.db)
        await self.db.run(memory.memories.remember, "The user likes tea.", category="preference")
        engine = make_engine(FakeLLM(), store=self.store)
        await engine.run((await engine.create_from_plan("r", chain_plan(1))).id)
        with self.db.connection() as conn:
            conn.execute("TRUNCATE workflows CASCADE")
            self.assertEqual(conn.execute("SELECT count(*) AS n FROM memories").fetchone()["n"], 1)
            conn.execute("TRUNCATE memories, messages, tasks, task_updates, conversations RESTART IDENTITY CASCADE")
