"""
Memory tests against a real PostgreSQL database.

Set TEST_DATABASE_URL to a *disposable* database (its alfred tables are emptied for every
test), e.g.  TEST_DATABASE_URL=postgresql://alfred:alfred@localhost:5432/alfred_test
Without it these tests are skipped.
"""

import os
import tempfile
import unittest
from pathlib import Path

from app.agent.orchestrator import AgentOrchestrator
from app.agent.state import ConversationState, SessionStore
from app.database import migrator
from app.database.postgres import DatabaseUnavailable, PostgresManager
from app.memory.coordinator import MemoryCoordinator
from app.memory.service import MemoryValidationError
from app.memory.tasks import TaskValidationError
from app.services.llm import GenerationResult, LLMProvider, ToolCallRequest
from app.tools.calculator import CalculatorTool
from app.tools.datetime_tool import DateTimeTool
from app.tools.memory_tool import MemoryTool
from app.tools.registry import ToolRegistry
from app.tools.tasks_tool import TasksTool

DSN = os.getenv("TEST_DATABASE_URL")
_TABLES = "task_updates, tasks, messages, memories, conversations"


@unittest.skipUnless(DSN, "TEST_DATABASE_URL is not set")
class PostgresTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = PostgresManager(DSN, min_size=1, max_size=4, connect_timeout=5)
        migrator.migrate(self.db)
        with self.db.connection() as conn:
            conn.execute(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE")
        self.memory = MemoryCoordinator(self.db)
        self.addCleanup(self.db.close)

    def restarted(self) -> MemoryCoordinator:
        """A brand-new manager + coordinator: what a backend restart looks like."""
        db = PostgresManager(DSN, min_size=1, max_size=2, connect_timeout=5)
        self.addCleanup(db.close)
        return MemoryCoordinator(db)


class ConnectivityAndMigrationTests(PostgresTestCase):
    def test_connectivity_report(self):
        report = self.db.check()
        self.assertTrue(report["connected"])
        self.assertIn("server_version", report)

    def test_migrations_are_recorded_and_idempotent(self):
        self.assertEqual(migrator.migrate(self.db), [])
        self.assertIn("001", migrator.applied_versions(self.db))
        with self.db.connection() as conn:
            tables = {r["tablename"] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
            indexes = {r["indexname"] for r in conn.execute("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")}
        self.assertTrue({"conversations", "messages", "memories", "tasks", "task_updates", "schema_migrations"} <= tables)
        self.assertTrue({"idx_memories_search", "idx_messages_conversation", "idx_tasks_status"} <= indexes)

    def test_new_migration_file_is_applied_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "900_probe.sql").write_text("CREATE TABLE IF NOT EXISTS migration_probe (id int);")
            try:
                self.assertEqual(migrator.migrate(self.db, Path(tmp)), ["900_probe.sql"])
                self.assertEqual(migrator.migrate(self.db, Path(tmp)), [])
            finally:
                with self.db.connection() as conn:
                    conn.execute("DROP TABLE IF EXISTS migration_probe")
                    conn.execute("DELETE FROM schema_migrations WHERE version = '900'")

    def test_failed_migration_rolls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "901_bad.sql").write_text("CREATE TABLE rollback_probe (id int); SELECT broken syntax here;")
            with self.assertRaises(Exception):
                migrator.migrate(self.db, Path(tmp))
        with self.db.connection() as conn:
            self.assertIsNone(conn.execute("SELECT to_regclass('rollback_probe') AS t").fetchone()["t"])
            self.assertEqual(conn.execute("SELECT count(*) AS n FROM schema_migrations WHERE version = '901'").fetchone()["n"], 0)

    def test_unreachable_database_raises_cleanly(self):
        bad = PostgresManager("postgresql://nobody@127.0.0.1:1/none", connect_timeout=1)
        with self.assertRaises(DatabaseUnavailable):
            with bad.connection():
                pass
        self.assertFalse(bad.check()["connected"])
        with self.assertRaises(DatabaseUnavailable):  # cooldown path returns quickly too
            with bad.connection():
                pass


class LongTermMemoryTests(PostgresTestCase):
    def test_create_read_update_delete(self):
        svc = self.memory.memories
        saved = svc.remember("The user prefers dark mode.", category="preference", importance=4, source="api")
        self.assertEqual(saved.action, "created")
        mid = saved.memory["id"]
        self.assertEqual(svc.get(mid)["content"], "The user prefers dark mode.")
        updated = svc.update(mid, content="The user prefers light mode.", importance=5)
        self.assertEqual((updated["content"], updated["importance"]), ("The user prefers light mode.", 5))
        self.assertEqual([m["id"] for m in svc.list(category="preference")], [mid])
        self.assertTrue(svc.delete(mid))
        self.assertIsNone(svc.get(mid))
        self.assertFalse(svc.delete(mid))
        self.assertIsNone(svc.update(mid, importance=2))

    def test_validation(self):
        svc = self.memory.memories
        for bad in ({"content": "  "}, {"content": "x", "category": "bogus"}, {"content": "x", "importance": 9}):
            with self.assertRaises(MemoryValidationError):
                svc.remember(**bad)

    def test_exact_and_near_duplicates_are_not_stored_twice(self):
        svc = self.memory.memories
        first = svc.remember("The user likes green tea.", category="preference")
        again = svc.remember("the user likes GREEN tea", category="preference", importance=5)
        near = svc.remember("The user really likes green tea.", category="preference")
        self.assertEqual((again.action, near.action), ("duplicate", "duplicate"))
        self.assertEqual(again.memory["id"], first.memory["id"])
        self.assertEqual(again.memory["importance"], 5)
        self.assertEqual(len(svc.list(status=None)), 1)

    def test_contradiction_replaces_old_memory(self):
        svc = self.memory.memories
        old = svc.remember("The user lives in Pune.", key="user.location").memory
        outcome = svc.remember("The user lives in London.", key="User.Location")
        self.assertEqual(outcome.action, "updated")
        self.assertEqual(outcome.replaced["id"], old["id"])
        active = svc.list()
        self.assertEqual([m["content"] for m in active], ["The user lives in London."])
        archived = svc.get(old["id"])
        self.assertEqual((archived["status"], archived["superseded_by"]), ("archived", outcome.memory["id"]))
        self.assertEqual(svc.search("Pune"), [])

    def test_search_ranks_and_ignores_archived_and_expired(self):
        svc = self.memory.memories
        svc.remember("The user's favorite food is sushi.", category="preference")
        svc.remember("The user is building a weather dashboard project.", category="project")
        gone = svc.remember("The user likes pizza.", category="preference").memory
        svc.update(gone["id"], status="archived")
        svc.remember("The user is travelling today.", expires_at=None)
        with self.db.connection() as conn:
            conn.execute("UPDATE memories SET expires_at = now() - interval '1 hour' WHERE content LIKE '%travelling%'")
        self.assertEqual(svc.search("what is my favorite food")[0]["content"], "The user's favorite food is sushi.")
        self.assertEqual(svc.search("pizza"), [])
        self.assertEqual(svc.search("travelling"), [])
        self.assertEqual(svc.search("the and of"), [])
        self.assertEqual(svc.search("sushi'; DROP TABLE memories; --")[:0], [])
        self.assertEqual(len(svc.search("dashboard project", categories=["project"])), 1)

    def test_maintenance_archives_expired_and_stale(self):
        svc = self.memory.memories
        a = svc.remember("The user has a meeting today.").memory
        b = svc.remember("The user once mentioned a minor thing.", importance=1).memory
        c = svc.remember("The user's name is Atharva.", importance=5, key="user.name").memory
        with self.db.connection() as conn:
            conn.execute("UPDATE memories SET expires_at = now() - interval '1 day' WHERE id = %s", (a["id"],))
            conn.execute("UPDATE memories SET updated_at = now() - interval '400 days' WHERE id IN (%s, %s)", (b["id"], c["id"]))
        self.assertEqual(svc.run_maintenance(180), {"expired": 1, "stale": 1})
        self.assertEqual(svc.get(a["id"])["status"], "archived")
        self.assertEqual(svc.get(b["id"])["status"], "archived")
        self.assertEqual(svc.get(c["id"])["status"], "active")  # important memories are never auto-archived

    def test_update_cannot_create_duplicate(self):
        svc = self.memory.memories
        svc.remember("The user likes tea.")
        other = svc.remember("The user likes coffee.").memory
        with self.assertRaises(MemoryValidationError):
            svc.update(other["id"], content="The user likes tea.")

    def test_transaction_rolls_back_on_error(self):
        with self.assertRaises(RuntimeError):
            with self.db.transaction() as conn:
                conn.execute("INSERT INTO conversations (id) VALUES ('rollback-me')")
                raise RuntimeError("boom")
        self.assertFalse(self.memory.conversations.exists("rollback-me"))


class PersistenceAfterRestartTests(PostgresTestCase):
    def test_memories_tasks_and_conversations_survive_a_restart(self):
        self.memory.memories.remember("The user's name is Atharva.", key="user.name", importance=5)
        task = self.memory.tasks.create("Build ALFRED Phase 4", project="ALFRED")
        self.memory.tasks.add_update(task["id"], "Use PostgreSQL for memory", kind="decision")
        self.memory.conversations.add_message("sess-1", "user", "hello")
        self.memory.conversations.add_message("sess-1", "assistant", "Good day, Sir.")
        self.db.close()

        fresh = self.restarted()
        self.assertEqual(fresh.memories.search("name")[0]["content"], "The user's name is Atharva.")
        self.assertEqual(fresh.tasks.get(task["id"])["updates"][0]["content"], "Use PostgreSQL for memory")
        self.assertEqual([m["content"] for m in fresh.conversations.messages("sess-1")], ["hello", "Good day, Sir."])


class TaskMemoryTests(PostgresTestCase):
    def test_task_lifecycle(self):
        tasks = self.memory.tasks
        task = tasks.create("Write the migration docs", description="Cover psql setup", project="ALFRED", priority=2)
        self.assertEqual((task["status"], task["priority"]), ("pending", 2))
        started = tasks.update(task["id"], status="in_progress")
        self.assertEqual(started["status"], "in_progress")
        tasks.add_update(task["id"], "Chose forward-only migrations", kind="decision")
        tasks.add_update(task["id"], "Schema reviewed", kind="milestone")
        done = tasks.update(task["id"], status="completed")
        self.assertIsNotNone(done["completed_at"])
        self.assertIsNone(tasks.update(task["id"], status="pending")["completed_at"])
        full = tasks.get(task["id"])
        self.assertEqual([u["kind"] for u in full["updates"]], ["decision", "milestone"])
        self.assertEqual(len(tasks.list(project="alfred")), 1)
        self.assertEqual(tasks.list(status="completed"), [])
        self.assertTrue(tasks.delete(task["id"]))
        self.assertIsNone(tasks.get(task["id"]))

    def test_validation_and_missing(self):
        tasks = self.memory.tasks
        with self.assertRaises(TaskValidationError):
            tasks.create("  ")
        with self.assertRaises(TaskValidationError):
            tasks.create("x", status="doing")
        self.assertIsNone(tasks.add_update(9999, "note"))

    def test_search_matches_updates_and_prefers_active(self):
        tasks = self.memory.tasks
        a = tasks.create("Refactor the voice pipeline", project="ALFRED")
        tasks.add_update(a["id"], "Decided to keep faster-whisper for transcription", kind="decision")
        b = tasks.create("Old voice experiment")
        tasks.update(b["id"], status="completed")
        hits = tasks.search("faster-whisper decision")
        self.assertEqual(hits[0]["id"], a["id"])
        self.assertEqual(hits[0]["recent_updates"][0]["kind"], "decision")
        self.assertEqual([t["id"] for t in tasks.search("voice")][:1], [a["id"]])
        self.assertEqual([t["id"] for t in tasks.recent_active()], [a["id"]])


class RetrievalTests(PostgresTestCase):
    def test_retrieves_only_what_is_relevant(self):
        svc = self.memory.memories
        svc.remember("The user's favorite food is sushi.", category="preference")
        svc.remember("The user lives in Pune.", key="user.location")
        svc.remember("The user is building a weather dashboard.", category="project")
        r = self.memory.retriever
        hit = r.retrieve("What is my favorite food?")
        self.assertEqual([m["content"] for m in hit.memories], ["The user's favorite food is sushi."])
        self.assertTrue(r.retrieve("Tell me a joke about cats").empty)
        self.assertTrue(r.retrieve("What is the capital of France?").empty)

    def test_standing_instructions_always_apply(self):
        self.memory.memories.remember("Standing instruction from the user: always answer briefly.", category="instruction", importance=4)
        self.memory.memories.remember("Standing instruction: minor stylistic wish.", category="instruction", importance=2)
        result = self.memory.retriever.retrieve("Explain photosynthesis")
        self.assertEqual(len(result.memories), 1)
        self.assertIn("answer briefly", result.memories[0]["content"])

    def test_continue_previous_work_uses_task_memory(self):
        tasks = self.memory.tasks
        t = tasks.create("Build the ALFRED memory layer", project="ALFRED", status="in_progress")
        tasks.add_update(t["id"], "Decision: PostgreSQL full-text search for retrieval", kind="decision")
        tasks.update(tasks.create("Finished chore")["id"], status="completed")
        result = self.memory.retriever.retrieve("Let's continue where we left off")
        self.assertEqual([x["id"] for x in result.tasks], [t["id"]])
        block = self.memory.retriever.format_context(result)
        self.assertIn("PostgreSQL full-text search", block)
        self.assertNotIn("Finished chore", block)
        by_topic = self.memory.retriever.retrieve("What did we decide about retrieval for the project?")
        self.assertEqual([x["id"] for x in by_topic.tasks], [t["id"]])

    def test_retrieval_records_access(self):
        mid = self.memory.memories.remember("The user's favorite food is sushi.").memory["id"]
        self.memory.retriever.retrieve("what is my favorite food")
        row = self.memory.memories.get(mid)
        self.assertEqual(row["access_count"], 1)
        self.assertIsNotNone(row["last_accessed_at"])


class ScriptedLLM(LLMProvider):
    def __init__(self, script):
        self.script, self.calls, self.instructions, self.histories = list(script), 0, [], []

    async def generate(self, messages, *, system_instruction=None):
        return await self.generate_with_tools(messages, [], system_instruction=system_instruction)

    async def generate_with_tools(self, messages, tools, *, system_instruction=None):
        self.instructions.append(system_instruction)
        self.histories.append(list(messages))
        result = self.script[self.calls]
        self.calls += 1
        return result


def text(t):
    return GenerationResult(text=t)


def call(name, **arguments):
    return GenerationResult(text=None, tool_calls=[ToolCallRequest(id="c1", name=name, arguments=arguments)])


class AgentIntegrationTests(PostgresTestCase):
    def agent(self, llm, *, memory=None, with_memory_tools=False):
        registry = ToolRegistry()
        registry.register(CalculatorTool())
        registry.register(DateTimeTool())
        if with_memory_tools:
            registry.register(MemoryTool(self.memory))
            registry.register(TasksTool(self.memory))
        return AgentOrchestrator(llm, registry, memory=memory or self.memory)

    async def test_learns_from_conversation_and_recalls_in_a_new_session_after_restart(self):
        llm = ScriptedLLM([text("Pleasure to meet you, Atharva.")])
        state = ConversationState("s1")
        result = await self.agent(llm).process(state, "My name is Atharva. I was born on 19 May 2007.")
        self.assertIn("memory_saved", [s.stage for s in result.trace])

        fresh = self.restarted()
        llm2 = ScriptedLLM([call("datetime", action="age", birth_date="2007-05-19", as_of_date="2026-11-24"),
                            text("You are 19 years old.")])
        agent2 = self.agent(llm2, memory=fresh)
        state2 = ConversationState("brand-new-session")
        result2 = await agent2.process(state2, "How old am I? Remember my birthday?")
        stages = [s.stage for s in result2.trace]
        self.assertIn("memory_retrieved", stages)
        self.assertIn("tool_selected", stages)  # memory informed the request but the tool still ran
        self.assertIn("19 May 2007", llm2.instructions[0])
        self.assertIn("never replaces a tool", llm2.instructions[0])
        self.assertEqual(result2.response_text, "You are 19 years old.")

    async def test_contradicting_statement_updates_memory(self):
        agent = self.agent(ScriptedLLM([text("Noted."), text("Noted again.")]))
        await agent.process(ConversationState("a"), "I live in Pune.")
        await agent.process(ConversationState("b"), "I live in London.")
        self.assertEqual([m["content"] for m in self.memory.memories.list()], ["The user lives in London."])
        self.assertEqual(len(self.memory.memories.list(status="archived")), 1)

    async def test_small_talk_is_not_saved_and_retrieves_nothing(self):
        llm = ScriptedLLM([text("Hello, Sir.")])
        result = await self.agent(llm).process(ConversationState("s"), "Hello there, how are you?")
        self.assertEqual(self.memory.memories.list(status=None), [])
        self.assertNotIn("Relevant background retrieved", llm.instructions[0])
        self.assertNotIn("memory_saved", [s.stage for s in result.trace])

    async def test_conversation_continuity_after_restart(self):
        llm = ScriptedLLM([text("First answer."), text("Second answer.")])
        await self.agent(llm).process(ConversationState("same-session"), "Tell me about volcanoes.")
        fresh = self.restarted()
        llm2 = ScriptedLLM([text("Continuing.")])
        store = SessionStore(max_context_messages=20)
        state = store.get_or_create("same-session")
        result = await self.agent(llm2, memory=fresh).process(state, "Go on.")
        self.assertIn("memory_restored", [s.stage for s in result.trace])
        sent = [m.content for m in llm2.histories[0]]
        self.assertEqual(sent, ["Tell me about volcanoes.", "First answer.", "Go on."])

    async def test_only_a_window_of_history_reaches_the_model(self):
        llm = ScriptedLLM([text(f"a{i}") for i in range(6)])
        agent = self.agent(llm)
        state = SessionStore(max_context_messages=4).get_or_create("long")
        for i in range(6):
            await agent.process(state, f"question {i}")
        self.assertLessEqual(len(llm.histories[-1]), 4)
        self.assertEqual(llm.histories[-1][-1].content, "question 5")

    async def test_task_memory_continues_previous_work(self):
        t = self.memory.tasks.create("Build the ALFRED history panel fix", project="ALFRED", status="in_progress")
        self.memory.tasks.add_update(t["id"], "Close button done, Escape handling remaining", kind="step")
        llm = ScriptedLLM([text("We were adding Escape handling.")])
        result = await self.agent(llm).process(ConversationState("n"), "Let's continue the ALFRED project")
        self.assertIn("Escape handling remaining", llm.instructions[0])
        self.assertIn("memory_retrieved", [s.stage for s in result.trace])

    async def test_agent_survives_database_outage(self):
        dead = MemoryCoordinator(PostgresManager("postgresql://nobody@127.0.0.1:1/none", connect_timeout=1))
        llm = ScriptedLLM([text("Still here, Sir.")])
        result = await self.agent(llm, memory=dead).process(ConversationState("x"), "My name is Atharva")
        self.assertEqual(result.response_text, "Still here, Sir.")

    async def test_memory_and_tasks_tools(self):
        llm = ScriptedLLM([
            call("memory", action="save", content="The user prefers metric units.", category="preference", importance=4),
            text("Saved."),
            call("tasks", action="create", title="Plan the launch", project="Apollo"),
            text("Task created."),
        ])
        agent = self.agent(llm, with_memory_tools=True)
        await agent.process(ConversationState("t"), "Please save that I prefer metric units")
        await agent.process(ConversationState("t2"), "Add a task to plan the Apollo launch")
        self.assertEqual(self.memory.memories.list()[0]["content"], "The user prefers metric units.")
        self.assertEqual(self.memory.tasks.list()[0]["title"], "Plan the launch")

    async def test_forget_and_task_delete_need_confirmation(self):
        mid = self.memory.memories.remember("The user likes tea.").memory["id"]
        llm = ScriptedLLM([call("memory", action="forget", memory_id=mid)])
        result = await self.agent(llm, with_memory_tools=True).process(ConversationState("f"), "Forget that I like tea")
        self.assertIsNotNone(result.pending_confirmation)
        self.assertIsNotNone(self.memory.memories.get(mid))  # nothing deleted before approval

    async def test_tool_errors_are_reported_not_raised(self):
        reg = ToolRegistry()
        reg.register(MemoryTool(self.memory))
        reg.register(TasksTool(self.memory))
        self.assertFalse((await reg.execute("memory", {"action": "forget", "memory_id": 4242})).success)
        self.assertFalse((await reg.execute("tasks", {"action": "get", "task_id": 4242})).success)
        self.assertFalse((await reg.execute("tasks", {"action": "create", "title": "x", "status": "bogus"})).success)
        self.assertFalse((await reg.execute("memory", {"action": "save"})).success)
