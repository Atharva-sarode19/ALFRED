"""ElevenLabs implementation of the provider-agnostic TTS interface."""

from __future__ import annotations

import logging
from typing import Any

from elevenlabs.client import AsyncElevenLabs

from app.config.settings import Settings, get_settings
from app.services.tts import SynthesisResult, TTSError, TTSProvider

logger = logging.getLogger("alfred.tts.elevenlabs")


class ElevenLabsTTSProvider(TTSProvider):
    """TTS provider backed by ElevenLabs' asynchronous Python SDK."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._client: AsyncElevenLabs | None = None

    def _get_client(self) -> AsyncElevenLabs:
        if self._client is None:
            api_key = self._settings.elevenlabs_api_key
            if not api_key:
                raise TTSError(
                    "ELEVENLABS_API_KEY is not set. Add it to backend/.env."
                )
            self._client = AsyncElevenLabs(api_key=api_key)
        return self._client

    async def list_voices(self) -> list[dict[str, Any]]:
        client = self._get_client()
        try:
            response = await client.voices.search(page_size=100)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Could not retrieve ElevenLabs voices")
            raise TTSError(f"Could not retrieve ElevenLabs voices: {exc}") from exc

        return [
            {
                "voice_id": voice.voice_id,
                "name": voice.name,
                "category": getattr(voice, "category", None),
                "labels": getattr(voice, "labels", None),
            }
            for voice in response.voices
        ]

    async def synthesize(self, text: str, *, voice: str | None = None) -> SynthesisResult:
        if not text or not text.strip():
            raise TTSError("No text was provided to synthesize.")

        voice_id = voice or self._settings.elevenlabs_voice_id
        if not voice_id:
            raise TTSError(
                "ELEVENLABS_VOICE_ID is not set. Add your ElevenLabs voice ID to backend/.env."
            )

        client = self._get_client()
        try:
            chunks: list[bytes] = []
            async for chunk in client.text_to_speech.convert(
                text=text,
                voice_id=voice_id,
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128",
            ):
                if chunk:
                    chunks.append(chunk)
            audio_bytes = b"".join(chunks)
        except Exception as exc:  # noqa: BLE001
            logger.exception("ElevenLabs speech synthesis failed")
            raise TTSError(f"ElevenLabs synthesis failed: {exc}") from exc

        if not audio_bytes:
            raise TTSError("ElevenLabs synthesis produced no audio.")

        return SynthesisResult(audio_bytes=audio_bytes, media_type="audio/mpeg")
