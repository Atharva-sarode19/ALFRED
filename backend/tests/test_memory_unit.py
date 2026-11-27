"""Memory tests that need no database."""

import os
import unittest
from datetime import datetime, timezone
from unittest import mock

from app.agent.state import ConversationState
from app.config.settings import Settings
from app.database.postgres import redact_dsn
from app.memory.extraction import LLMMemoryExtractor, MemoryExtractor, third_person
from app.memory.retrieval import MemoryRetriever, RetrievalResult
from app.memory.short_term import context_window
from app.memory.text import content_hash, similarity
from app.services.llm import GenerationResult, LLMProvider, Message, Role, ToolCallRequest

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)


def extract(text):
    return MemoryExtractor().extract(text, now=NOW)


class ExtractionTests(unittest.TestCase):
    def test_explicit_remember(self):
        (c,) = extract("Remember that I prefer dark mode in every app.").candidates
        self.assertEqual((c.content, c.category, c.source), ("The user prefers dark mode in every app.", "preference", "explicit"))

    def test_name_and_birthday_slots(self):
        result = extract("My name is Atharva and I like tea. I was born on 19 May 2007.")
        keys = {c.key: c for c in result.candidates}
        self.assertEqual(keys["user.name"].content, "The user's name is Atharva.")
        self.assertIn("2007-05-19", keys["user.birthday"].content)

    def test_remember_slot_is_flagged_explicit(self):
        (c,) = extract("Remember my birthday is 19 May 2007").candidates
        self.assertEqual((c.key, c.source), ("user.birthday", "explicit"))

    def test_instruction_project_decision(self):
        cats = {c.category for c in extract("Always answer briefly. I'm working on the ALFRED backend. We decided to use PostgreSQL.").candidates}
        self.assertEqual(cats, {"instruction", "project"})

    def test_ordinary_messages_yield_nothing(self):
        for text in ("hello there", "What is my name?", "What's the weather in Pune?", "I like how you explained that",
                     "Can you remember what I said earlier?", "thanks"):
            self.assertFalse(extract(text), text)

    def test_secrets_are_never_extracted(self):
        for text in ("Remember that my password is hunter2", "my api key is abc123", "remember my card number 4111111111111111"):
            self.assertFalse(extract(text), text)

    def test_retraction(self):
        result = extract("I no longer like sushi")
        self.assertEqual(result.retract_keys, ["attitude.sushi"])
        self.assertFalse(result.candidates)

    def test_opinions_share_a_slot_so_they_can_be_updated(self):
        like, love = extract("I like sushi").candidates[0], extract("I hate sushi").candidates[0]
        self.assertEqual(like.key, love.key)

    def test_temporary_statements_expire(self):
        (c,) = extract("I'm working on the report today").candidates
        self.assertIsNotNone(c.expires_at)
        self.assertGreater(c.expires_at, NOW)

    def test_third_person(self):
        self.assertEqual(third_person("I like my coffee black"), "The user likes the user's coffee black.")


class FakeLLM(LLMProvider):
    def __init__(self, text):
        self.text = text

    async def generate(self, messages, *, system_instruction=None):
        return GenerationResult(text=self.text)

    async def generate_with_tools(self, messages, tools, *, system_instruction=None):
        return GenerationResult(text=self.text)


class LLMExtractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_parses_and_validates_json(self):
        payload = '```json\n[{"content": "The user prefers vim.", "category": "preference", "importance": 4}, {"nope": 1}, {"content": "token is abc", "category": "fact"}]\n```'
        result = await LLMMemoryExtractor(FakeLLM(payload)).extract("I always use vim for editing things")
        self.assertEqual([c.content for c in result.candidates], ["The user prefers vim"])

    async def test_garbage_output_is_ignored(self):
        self.assertFalse(await LLMMemoryExtractor(FakeLLM("not json")).extract("some long enough message here"))


class ShortTermWindowTests(unittest.TestCase):
    @staticmethod
    def convo(turns):
        out = []
        for i in range(turns):
            out += [Message(role=Role.USER, content=f"q{i}"), Message(role=Role.ASSISTANT, content=f"a{i}")]
        return out

    def test_limits_message_count_and_starts_on_user(self):
        window = context_window(self.convo(10), max_messages=5, max_chars=None)
        self.assertEqual(window[0].role, Role.USER)
        self.assertLessEqual(len(window), 5)
        self.assertEqual(window[-1].content, "a9")

    def test_limits_characters_but_keeps_latest_user_message(self):
        messages = self.convo(5) + [Message(role=Role.USER, content="x" * 5000)]
        window = context_window(messages, max_messages=None, max_chars=100)
        self.assertEqual([m.content for m in window], ["x" * 5000])

    def test_tool_exchange_is_not_split(self):
        call = ToolCallRequest(id="1", name="calculator", arguments={})
        messages = [Message(role=Role.USER, content="old"), Message(role=Role.ASSISTANT, content="ok"),
                    Message(role=Role.USER, content="calc"), Message(role=Role.ASSISTANT, tool_calls=[call]),
                    Message(role=Role.TOOL, content="4", name="calculator", tool_call_id="1")]
        window = context_window(messages, max_messages=2, max_chars=None)
        self.assertEqual(window[0].content, "calc")
        self.assertEqual(len(window), 3)

    def test_state_history_uses_window(self):
        state = ConversationState("s", max_context_messages=4)
        state.add_many(self.convo(10))
        self.assertLessEqual(len(state.history()), 4)
        self.assertEqual(len(state.messages), 20)


class AssessmentTests(unittest.TestCase):
    def test_context_cues(self):
        for q in ("What did we decide last time?", "Continue where we left off", "what is my favorite food", "remember the project plan"):
            self.assertTrue(MemoryRetriever.assess(q).needs_context, q)
        for q in ("tell me a joke", "what is the capital of France"):
            self.assertFalse(MemoryRetriever.assess(q).needs_context, q)

    def test_tools_required_for_exact_or_fresh_information(self):
        self.assertIn("age", MemoryRetriever.assess("How old am I?").tools_required)
        self.assertIn("calculator", MemoryRetriever.assess("calculate 15% of 240").tools_required)
        self.assertIn("weather", MemoryRetriever.assess("what's the weather like").tools_required)
        self.assertEqual(MemoryRetriever.assess("tell me a joke").tools_required, [])

    def test_context_block_warns_memory_is_not_a_tool_substitute(self):
        result = RetrievalResult(MemoryRetriever.assess("How old am I?"), memories=[
            {"id": 1, "category": "fact", "content": "The user's date of birth is 19 May 2007.", "created_at": NOW}])
        block = MemoryRetriever.format_context(result)
        self.assertIn("19 May 2007", block)
        self.assertIn("never replaces a tool", block)
        self.assertIn("age", block.split("This request needs")[1])
        self.assertIsNone(MemoryRetriever.format_context(RetrievalResult(MemoryRetriever.assess("hi"))))


class HelperTests(unittest.TestCase):
    def test_hash_and_similarity(self):
        self.assertEqual(content_hash("The user likes Tea."), content_hash("the user likes tea"))
        self.assertGreater(similarity("The user likes green tea", "the user likes green tea a lot"), 0.7)
        self.assertLess(similarity("likes tea", "lives in Pune"), 0.2)

    def test_redact_dsn(self):
        self.assertNotIn("s3cret", redact_dsn("postgresql://alfred:s3cret@db:5432/alfred"))
        self.assertNotIn("s3cret", redact_dsn("host=db user=a password=s3cret dbname=x"))

    def test_database_url_from_parts_and_disabled_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(Settings().database_url)
            self.assertFalse(Settings().memory_enabled)
        parts = {"POSTGRES_DB": "alfred", "POSTGRES_USER": "me", "POSTGRES_PASSWORD": "p@ss", "POSTGRES_HOST": "h"}
        with mock.patch.dict(os.environ, parts, clear=True):
            self.assertEqual(Settings().database_url, "postgresql://me:p%40ss@h:5432/alfred")
        with mock.patch.dict(os.environ, {"DATABASE_URL": "postgresql://x/y", "MEMORY_ENABLED": "false"}, clear=True):
            self.assertFalse(Settings().memory_enabled)
