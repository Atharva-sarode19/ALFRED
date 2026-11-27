"""HTTP-level tests for the memory, task and conversation endpoints."""

import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.api import deps
from app.database import migrator
from app.database.postgres import PostgresManager
from app.main import app
from app.memory.coordinator import MemoryCoordinator

DSN = os.getenv("TEST_DATABASE_URL")


class DisabledMemoryApiTests(unittest.TestCase):
    def test_endpoints_report_disabled_memory(self):
        with mock.patch.object(deps, "_memory", None), mock.patch.object(deps, "_memory_built", True):
            client = TestClient(app)
            self.assertEqual(client.get("/api/memory/status").json()["enabled"], False)
            self.assertEqual(client.get("/api/memory").status_code, 503)
            self.assertEqual(client.get("/api/tasks").status_code, 503)

    def test_unreachable_database_is_503_not_500(self):
        dead = MemoryCoordinator(PostgresManager("postgresql://nobody@127.0.0.1:1/none", connect_timeout=1))
        with mock.patch.object(deps, "_memory", dead), mock.patch.object(deps, "_memory_built", True):
            client = TestClient(app)
            self.assertEqual(client.get("/api/memory").status_code, 503)
            status = client.get("/api/memory/status").json()
            self.assertEqual((status["enabled"], status["connected"]), (True, False))


@unittest.skipUnless(DSN, "TEST_DATABASE_URL is not set")
class MemoryApiTests(unittest.TestCase):
    def setUp(self):
        db = PostgresManager(DSN, connect_timeout=5)
        migrator.migrate(db)
        with db.connection() as conn:
            conn.execute("TRUNCATE task_updates, tasks, messages, memories, conversations RESTART IDENTITY CASCADE")
        self.memory = MemoryCoordinator(db)
        patches = [mock.patch.object(deps, "_memory", self.memory), mock.patch.object(deps, "_memory_built", True)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(db.close)
        self.client = TestClient(app)

    def test_status(self):
        status = self.client.get("/api/memory/status").json()
        self.assertTrue(status["connected"])
        self.assertEqual(status["memories"], {})

    def test_memory_crud_and_search(self):
        created = self.client.post("/api/memory", json={"content": "The user likes sushi.", "category": "preference"})
        self.assertEqual(created.status_code, 201)
        mid = created.json()["memory"]["id"]
        self.assertEqual(self.client.post("/api/memory", json={"content": "the user likes sushi"}).json()["result"], "duplicate")
        self.assertEqual(self.client.get(f"/api/memory/{mid}").json()["content"], "The user likes sushi.")
        self.assertEqual(self.client.get("/api/memory", params={"category": "preference"}).json()[0]["id"], mid)
        self.assertEqual(self.client.get("/api/memory/search", params={"q": "sushi"}).json()[0]["id"], mid)
        patched = self.client.patch(f"/api/memory/{mid}", json={"content": "The user loves ramen.", "importance": 5})
        self.assertEqual((patched.json()["content"], patched.json()["importance"]), ("The user loves ramen.", 5))
        self.assertEqual(self.client.patch(f"/api/memory/{mid}", json={"status": "archived"}).json()["status"], "archived")
        self.assertEqual(self.client.get("/api/memory").json(), [])
        self.assertEqual(self.client.delete(f"/api/memory/{mid}").status_code, 204)
        self.assertEqual(self.client.get(f"/api/memory/{mid}").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/memory/{mid}").status_code, 404)

    def test_validation_errors(self):
        self.assertEqual(self.client.post("/api/memory", json={"content": "x", "category": "bogus"}).status_code, 422)
        self.assertEqual(self.client.post("/api/memory", json={"content": ""}).status_code, 422)
        self.assertEqual(self.client.get("/api/memory", params={"category": "bogus"}).status_code, 422)
        self.assertEqual(self.client.post("/api/tasks", json={"title": "x", "status": "bogus"}).status_code, 422)
        self.assertEqual(self.client.patch("/api/memory/999", json={"importance": 2}).status_code, 404)

    def test_task_endpoints(self):
        task = self.client.post("/api/tasks", json={"title": "Ship Phase 4", "project": "ALFRED"}).json()
        tid = task["id"]
        self.assertEqual(self.client.patch(f"/api/tasks/{tid}", json={"status": "in_progress"}).json()["status"], "in_progress")
        update = self.client.post(f"/api/tasks/{tid}/updates", json={"content": "Use PostgreSQL", "kind": "decision"})
        self.assertEqual(update.status_code, 201)
        self.assertEqual(self.client.post(f"/api/tasks/{tid}/updates", json={"content": "x", "kind": "bogus"}).status_code, 422)
        self.assertEqual(self.client.post("/api/tasks/999/updates", json={"content": "x"}).status_code, 404)
        self.assertEqual(self.client.get(f"/api/tasks/{tid}").json()["updates"][0]["kind"], "decision")
        self.assertEqual(self.client.get("/api/tasks", params={"active_only": True}).json()[0]["id"], tid)
        self.assertEqual(self.client.get("/api/tasks/search", params={"q": "postgresql"}).json()[0]["id"], tid)
        self.assertEqual(self.client.delete(f"/api/tasks/{tid}").status_code, 204)
        self.assertEqual(self.client.get(f"/api/tasks/{tid}").status_code, 404)

    def test_conversation_endpoints(self):
        self.memory.conversations.add_message("c1", "user", "hello alfred")
        self.memory.conversations.add_message("c1", "assistant", "Good day, Sir.")
        listing = self.client.get("/api/conversations").json()
        self.assertEqual((listing[0]["id"], listing[0]["message_count"], listing[0]["title"]), ("c1", 2, "hello alfred"))
        messages = self.client.get("/api/conversations/c1/messages").json()
        self.assertEqual([m["role"] for m in messages], ["user", "assistant"])
        self.assertEqual(self.client.get("/api/conversations/nope/messages").status_code, 404)
        self.assertEqual(self.client.delete("/api/conversations/c1").status_code, 204)
        self.assertEqual(self.client.delete("/api/conversations/c1").status_code, 404)
