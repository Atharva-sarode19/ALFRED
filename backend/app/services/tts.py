"""
Text-to-speech abstraction. Same pattern as STT: the agent/API layer only
ever talks to `TTSProvider`, never to a specific vendor SDK.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class TTSError(RuntimeError):
    """Raised when speech synthesis fails."""


@dataclass
class SynthesisResult:
    audio_bytes: bytes
    media_type: str  # e.g. "audio/mpeg"


class TTSProvider(ABC):
    """Abstract text-to-speech engine."""

    async def list_voices(self) -> list[dict[str, Any]]:
        """Return provider voice metadata when the provider supports listing."""
        raise TTSError("Voice listing is not supported by the configured TTS provider.")

    @abstractmethod
    async def synthesize(self, text: str, *, voice: str | None = None) -> SynthesisResult:
        """Convert `text` to speech audio bytes."""
        raise NotImplementedError
