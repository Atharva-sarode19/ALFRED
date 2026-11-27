import pytest
from fastapi.testclient import TestClient

import app.api.voice as voice_module
from app.main import app
from app.services.stt import STTError, STTProvider, TranscriptionResult
from app.services.tts import SynthesisResult, TTSError, TTSProvider


class FakeSTTProvider(STTProvider):
    def __init__(self, result: TranscriptionResult | None = None, error: Exception | None = None):
        self._result = result
        self._error = error

    async def transcribe(self, audio_bytes: bytes, *, filename_hint: str = "audio.webm"):
        if self._error:
            raise self._error
        return self._result


class FakeTTSProvider(TTSProvider):
    def __init__(self, result: SynthesisResult | None = None, error: Exception | None = None):
        self._result = result
        self._error = error

    async def synthesize(self, text: str, *, voice: str | None = None):
        if self._error:
            raise self._error
        return self._result


@pytest.fixture
def client():
    return TestClient(app)


def test_transcribe_success(client, monkeypatch):
    fake = FakeSTTProvider(result=TranscriptionResult(text="hello alfred", language="en"))
    app.dependency_overrides[voice_module.get_stt_provider] = lambda: fake

    response = client.post(
        "/api/voice/transcribe",
        files={"audio": ("clip.wav", b"fake-audio-bytes", "audio/wav")},
    )

    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["text"] == "hello alfred"


def test_transcribe_no_speech_detected(client):
    fake = FakeSTTProvider(error=STTError("No speech was detected in the audio."))
    app.dependency_overrides[voice_module.get_stt_provider] = lambda: fake

    response = client.post(
        "/api/voice/transcribe",
        files={"audio": ("clip.wav", b"silence", "audio/wav")},
    )

    app.dependency_overrides.clear()
    assert response.status_code == 422


def test_synthesize_success(client):
    fake = FakeTTSProvider(result=SynthesisResult(audio_bytes=b"\x00\x01\x02", media_type="audio/mpeg"))
    app.dependency_overrides[voice_module.get_tts_provider] = lambda: fake

    response = client.post("/api/voice/synthesize", json={"text": "Good evening."})

    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == b"\x00\x01\x02"


def test_synthesize_rejects_empty_text(client):
    # Pydantic's min_length=1 rejects this before it ever reaches a provider.
    response = client.post("/api/voice/synthesize", json={"text": ""})
    assert response.status_code == 422


def test_synthesize_surfaces_provider_failure(client):
    fake = FakeTTSProvider(error=TTSError("Speech synthesis produced no audio."))
    app.dependency_overrides[voice_module.get_tts_provider] = lambda: fake

    response = client.post("/api/voice/synthesize", json={"text": "Good evening."})

    app.dependency_overrides.clear()
    assert response.status_code == 422
