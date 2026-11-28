"""
Memory extraction: decide which things the user said are worth keeping.

Only the *user's own words* are inspected -- never assistant text, tool output or web
content -- so untrusted content cannot write to memory. Most messages yield nothing:
only explicit "remember ..." requests, stable facts (name, birthday, location, work),
preferences, standing instructions, projects and decisions are kept. Anything that looks
like a secret is skipped.

`MemoryExtractor` is deterministic. `LLMMemoryExtractor` optionally adds model-based
extraction (MEMORY_LLM_EXTRACTION=true) for facts the patterns cannot catch.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.memory.text import normalize
from app.services.llm import LLMProvider, LLMProviderError, Message, Role
from app.tools.date_math import parse_date

logger = logging.getLogger("alfred.memory.extract")

_SENSITIVE = re.compile(
    r"pass(?:word|code|phrase)|\bpin\b|api[\s_-]?key|secret|token|credential|\bssn\b|social security|"
    r"credit card|card number|cvv|private key|\b\d{13,19}\b",
    re.I,
)
_QUESTION_START = re.compile(
    r"^(?:what|when|where|who|whom|whose|why|how|which|do|does|did|can|could|would|should|is|are|was|were|will|have|has)\b",
    re.I,
)
_TEMPORARY = (
    (re.compile(r"\b(?:today|tonight|this (?:morning|afternoon|evening))\b", re.I), timedelta(days=1)),
    (re.compile(r"\btomorrow\b", re.I), timedelta(days=2)),
    (re.compile(r"\bthis (?:week|weekend)\b", re.I), timedelta(days=7)),
)
_VERB_S = {"have": "has", "do": "does", "go": "goes"}
_VERB_AFTER_USER = (
    "like|love|prefer|hate|dislike|live|work|need|want|use|enjoy|play|speak|drive|own|study|teach|eat|drink|"
    "read|watch|know|get|run|build|write|have|do|go|take|make|ride|cook"
)
_JUNK_OBJECT = re.compile(r"^(?:it|that|this|them|you|how|when|what|the way|to hear|when you|the fact)\b", re.I)

CATEGORY_PREFERENCE, CATEGORY_FACT, CATEGORY_INSTRUCTION, CATEGORY_PROJECT = "preference", "fact", "instruction", "project"


@dataclass
class MemoryCandidate:
    content: str
    category: str = "fact"
    key: str | None = None
    importance: int = 3
    source: str = "extracted"
    expires_at: datetime | None = None


@dataclass
class ExtractionResult:
    candidates: list[MemoryCandidate] = field(default_factory=list)
    retract_keys: list[str] = field(default_factory=list)  # slots the user said no longer apply

    def __bool__(self) -> bool:
        return bool(self.candidates or self.retract_keys)


def _tidy(value: str, limit: int = 160) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t.,;:!?\"'")[:limit].strip()


def third_person(text: str) -> str:
    """'I like my coffee black' -> "The user likes the user's coffee black." (simple, predictable)."""
    out = f" {text.strip()} "
    for pattern, repl in (
        (r"\bi(?:'m| am)\b", "the user is"),
        (r"\bi(?:'ve| have)\b", "the user has"),
        (r"\bi(?:'ll| will)\b", "the user will"),
        (r"\bi(?:'d| would)\b", "the user would"),
        (r"\bmy\b", "the user's"),
        (r"\bmine\b", "the user's"),
        (r"\bmyself\b", "the user"),
        (r"\bme\b", "the user"),
        (r"\bi\b", "the user"),
    ):
        out = re.sub(pattern, repl, out, flags=re.I)
    out = re.sub(
        rf"\bthe user ({_VERB_AFTER_USER})\b",
        lambda m: f"the user {_VERB_S.get(m.group(1).lower(), m.group(1).lower() + 's')}",
        out,
        flags=re.I,
    )
    out = out.strip()
    out = out[:1].upper() + out[1:]
    return out if out.endswith((".", "!", "?")) else out + "."


def _expiry(sentence: str, now: datetime) -> datetime | None:
    for pattern, delta in _TEMPORARY:
        if pattern.search(sentence):
            return now + delta
    return None


def _classify(text: str) -> str:
    lowered = text.lower()
    if re.search(r"\b(?:always|never|whenever|from now on|going forward)\b", lowered):
        return CATEGORY_INSTRUCTION
    if re.search(r"\b(?:prefer|like|love|enjoy|hate|dislike|favou?rite)s?\b", lowered):
        return CATEGORY_PREFERENCE
    if re.search(r"\b(?:project|working on|building|developing|deadline|milestone|decided|repo|codebase)\b", lowered):
        return CATEGORY_PROJECT
    return CATEGORY_FACT


class MemoryExtractor:
    """Rule-based extraction from one user message."""

    def extract(self, text: str, *, now: datetime | None = None) -> ExtractionResult:
        now = now or datetime.now(timezone.utc)
        result = ExtractionResult()
        seen: set[str] = set()
        for raw in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
            sentence = raw.strip()
            if len(sentence) < 4 or _SENSITIVE.search(sentence):
                continue
            retract = self._retraction(sentence)
            if retract:
                result.retract_keys.append(retract)
                continue
            candidate = self._explicit(sentence, now) or self._slots(sentence, now) or self._soft(sentence, now)
            if candidate and normalize(candidate.content) not in seen:
                seen.add(normalize(candidate.content))
                result.candidates.append(candidate)
        return result

    # ---- retraction ("I no longer like X") -------------------------------------
    @staticmethod
    def _retraction(sentence: str) -> str | None:
        m = re.search(
            r"\bi (?:no longer|don'?t|do not|stopped|quit)\s+(?:(?:really\s+)?(?:like|love|enjoy|prefer)(?:ing)?)\s+(.+?)"
            r"(?:\s+anymore|\s+any more)?$",
            sentence,
            re.I,
        )
        if m and (re.search(r"\bno longer\b|anymore|any more|stopped|quit", sentence, re.I)):
            obj = _tidy(m.group(1), 100)
            if obj and not _JUNK_OBJECT.match(obj):
                return f"attitude.{normalize(obj)}"
        return None

    # ---- explicit "remember that ..." ------------------------------------------------
    def _explicit(self, sentence: str, now: datetime) -> MemoryCandidate | None:
        m = re.match(
            r"^(?:(?:please|ok(?:ay)?|alfred)[,\s]+)*(?:remember|keep in mind)(?:\s+that)?[,:\s]+(.+)$", sentence, re.I
        )
        if not m or "?" in sentence:
            return None
        body = _tidy(m.group(1), 400)
        if len(body) < 3:
            return None
        slot = self._slots(body, now)
        if slot:  # "remember my name is X" -> same slot, but flagged explicit
            slot.source, slot.importance = "explicit", max(slot.importance, 4)
            return slot
        return MemoryCandidate(
            third_person(body), _classify(body), None, 4, "explicit", _expiry(sentence, now)
        )

    # ---- stable personal facts with a "slot" (new value replaces old) -----------------
    def _slots(self, sentence: str, now: datetime) -> MemoryCandidate | None:
        if sentence.endswith("?") or _QUESTION_START.match(sentence):
            return None
        if m := re.search(r"\b(?i:my name is|call me|i go by)\s+([A-Za-z][\w'’-]*(?:\s+[A-Z][\w'’-]*)?)", sentence):
            return MemoryCandidate(f"The user's name is {_tidy(m.group(1)).title()}.", CATEGORY_FACT, "user.name", 5)
        if m := re.search(r"\b(?:my (?:date of birth|birthday|birth ?date|dob) is|i was born (?:on|in))\s+(.+)$", sentence, re.I):
            raw = _tidy(m.group(1), 60)
            parsed = parse_date(raw)
            shown = f"{raw} ({parsed.isoformat()})" if parsed and parsed.isoformat() != raw else raw
            return MemoryCandidate(f"The user's date of birth is {shown}.", CATEGORY_FACT, "user.birthday", 5)
        if m := re.search(r"\bi (?:live|reside|am living|currently live) in\s+(.+)$", sentence, re.I):
            return MemoryCandidate(f"The user lives in {_tidy(m.group(1), 80)}.", CATEGORY_FACT, "user.location", 4)
        if m := re.search(r"\bi work (as|at|for)\s+(.+)$", sentence, re.I):
            return MemoryCandidate(
                f"The user works {m.group(1).lower()} {_tidy(m.group(2), 100)}.", CATEGORY_FACT, "user.work", 4
            )
        if m := re.search(r"\bmy favou?rite ([\w ]{2,30}?) (?:is|are)\s+(.+)$", sentence, re.I):
            thing = _tidy(m.group(1), 30).lower()
            return MemoryCandidate(
                f"The user's favorite {thing} is {_tidy(m.group(2), 80)}.", CATEGORY_PREFERENCE,
                f"favorite.{normalize(thing)}", 3,
            )
        return None

    # ---- softer signals: opinions, instructions, projects, decisions --------------------
    def _soft(self, sentence: str, now: datetime) -> MemoryCandidate | None:
        if sentence.endswith("?") or _QUESTION_START.match(sentence):
            return None
        if m := re.match(r"^(?:please\s+)?((?:always|never|from now on|going forward|whenever)\b.+)$", sentence, re.I):
            return MemoryCandidate(f"Standing instruction from the user: {_tidy(m.group(1), 300)}.", CATEGORY_INSTRUCTION, None, 4)
        if m := re.search(r"\bwe (?:have |'ve )?(?:decided|agreed)\s+(?:to|on|that)\s+(.+)$", sentence, re.I):
            return MemoryCandidate(f"Decision: {_tidy(m.group(1), 300)}.", CATEGORY_PROJECT, None, 4)
        if m := re.search(
            r"\bi(?:'m| am)\s+(?:currently\s+|now\s+)?(working on|building|developing|writing|creating)\s+(.+)$",
            sentence, re.I,
        ):
            return MemoryCandidate(
                f"The user is {m.group(1).lower()} {_tidy(m.group(2), 200)}.", CATEGORY_PROJECT, None, 3,
                expires_at=_expiry(sentence, now),
            )
        if m := re.search(r"\bi (?:really |absolutely |truly )?(like|love|enjoy|prefer|hate|dislike)\s+(.+)$", sentence, re.I):
            verb, obj = m.group(1).lower(), _tidy(m.group(2), 100)
            if len(obj) < 3 or _JUNK_OBJECT.match(obj) or "," in obj and len(obj) > 60:
                return None
            return MemoryCandidate(
                f"The user {verb}s {obj}.", CATEGORY_PREFERENCE, f"attitude.{normalize(obj)}", 2,
                expires_at=_expiry(sentence, now),
            )
        return None


_LLM_PROMPT = (
    "You extract long-term memories from the user's message in a chat with an assistant. "
    "Return ONLY a JSON array (possibly empty). Each item: "
    '{"content": "third-person sentence, e.g. The user prefers dark mode.", '
    '"category": "preference|fact|instruction|project", "key": "optional slot like user.location or null", '
    '"importance": 1-5}. Keep only durable, useful information the user stated about themselves, '
    "their preferences, standing instructions or projects. Skip questions, small talk, one-off requests, "
    "and anything secret (passwords, keys, card numbers)."
)


class LLMMemoryExtractor:
    """Optional model-based extraction, run after the reply is produced."""

    def __init__(self, llm: LLMProvider):
        self._llm = llm

    async def extract(self, user_text: str) -> ExtractionResult:
        result = ExtractionResult()
        if len(user_text.strip()) < 12 or _SENSITIVE.search(user_text):
            return result
        try:
            generated = await self._llm.generate(
                [Message(role=Role.USER, content=user_text)], system_instruction=_LLM_PROMPT
            )
        except LLMProviderError as exc:
            logger.warning("LLM memory extraction failed: %s", exc)
            return result
        raw = re.sub(r"^```(?:json)?|```$", "", (generated.text or "").strip(), flags=re.M).strip()
        try:
            items = json.loads(raw)
        except ValueError:
            return result
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict) or not isinstance(item.get("content"), str):
                continue
            content = _tidy(item["content"], 400)
            if not content or _SENSITIVE.search(content):
                continue
            category = item.get("category") if item.get("category") in ("preference", "fact", "instruction", "project") else "fact"
            importance = item.get("importance") if isinstance(item.get("importance"), int) and 1 <= item["importance"] <= 5 else 3
            key = item.get("key") if isinstance(item.get("key"), str) and item["key"].strip() else None
            result.candidates.append(MemoryCandidate(content, category, key, importance, "extracted"))
        return result
