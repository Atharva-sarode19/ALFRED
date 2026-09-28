"""
`edge-tts` implementation of `TTSProvider`.

Uses Microsoft Edge's neural text-to-speech voices via the `edge-tts`
package -- no API key required, good voice quality. This is the only file
that should import `edge_tts`; swapping in a different provider later
(e.g. ElevenLabs, a hosted Gemini TTS model) means adding a new class here
and pointing `get_tts_provider()` at it, nothing else changes.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config.settings import Settings, get_settings
from app.services.tts import SynthesisResult, TTSError, TTSProvider

logger = logging.getLogger("alfred.tts.edge")


class EdgeTTSProvider(TTSProvider):
    """TTSProvider backed by Microsoft Edge's neural voices (`edge-tts`)."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()

    async def list_voices(self) -> list[dict[str, Any]]:
        try:
            import edge_tts
        except ImportError as exc:  # pragma: no cover
            raise TTSError("edge-tts is not installed. Run `pip install edge-tts`.") from exc
        try:
            return await edge_tts.list_voices()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Could not retrieve Edge TTS voices")
            raise TTSError(f"Could not retrieve Edge TTS voices: {exc}") from exc

    async def synthesize(self, text: str, *, voice: str | None = None) -> SynthesisResult:
        if not text or not text.strip():
            raise TTSError("No text was provided to synthesize.")

        try:
            import edge_tts
        except ImportError as exc:  # pragma: no cover
            raise TTSError("edge-tts is not installed. Run `pip install edge-tts`.") from exc

        selected_voice = voice or self._settings.tts_voice

        chunks: list[bytes] = []
        try:
            communicator = edge_tts.Communicate(text, selected_voice)
            async for chunk in communicator.stream():
                if chunk.get("type") == "audio":
                    chunks.append(chunk["data"])
        except Exception as exc:  # noqa: BLE001
            logger.exception("edge-tts synthesis failed")
            raise TTSError(f"Speech synthesis failed: {exc}") from exc

        audio_bytes = b"".join(chunks)
        if not audio_bytes:
            raise TTSError("Speech synthesis produced no audio.")

        return SynthesisResult(audio_bytes=audio_bytes, media_type="audio/mpeg")
