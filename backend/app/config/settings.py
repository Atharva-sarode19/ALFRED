"""
Central application configuration.

All configuration is sourced from environment variables (optionally loaded
from a `.env` file). Nothing in this module ever hard-codes a secret or a
model name -- callers must set the corresponding environment variable.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

try:
    # Optional: only used if python-dotenv is installed. Phase 1 does not
    # hard-require it -- if it's missing we just rely on real env vars.
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - exercised when dotenv isn't installed
    pass


class ConfigurationError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


# Browser origins allowed to call the API.
ALLOWED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer, got {raw!r}") from exc
    if value < minimum:
        raise ConfigurationError(f"{name} must be >= {minimum}")
    return value


class Settings:
    """
    Typed accessor over environment configuration.

    Values are read lazily via properties so that tests can monkeypatch
    `os.environ` and get fresh values without re-importing the module.
    """

    # ---- Gemini / LLM -----------------------------------------------
    @property
    def gemini_api_key(self) -> str | None:
        return os.getenv("GEMINI_API_KEY") or None

    @property
    def gemini_model(self) -> str:
        model = os.getenv("GEMINI_MODEL")
        if not model:
            raise ConfigurationError(
                "GEMINI_MODEL is not set. Configure it in your .env file "
                "(see .env.example) -- ALFRED never hard-codes a model name."
            )
        return model

    # ---- Agent behaviour ----------------------------------------------
    @property
    def max_agent_iterations(self) -> int:
        raw = os.getenv("MAX_AGENT_ITERATIONS", "8")
        try:
            value = int(raw)
        except ValueError as exc:
            raise ConfigurationError(
                f"MAX_AGENT_ITERATIONS must be an integer, got {raw!r}"
            ) from exc
        if value < 1:
            raise ConfigurationError("MAX_AGENT_ITERATIONS must be >= 1")
        return value

    @property
    def require_medium_confirmation(self) -> bool:
        """MEDIUM-permission actions (e.g. create a note) ask first. HIGH always asks."""
        return _env_bool("REQUIRE_MEDIUM_CONFIRMATION", True)

    @property
    def default_timezone(self) -> str:
        return os.getenv("DEFAULT_TIMEZONE", "UTC")

    # ---- Storage and files (Phase 3: SQLite; PostgreSQL arrives in Phase 4) ----
    @property
    def data_dir(self) -> Path:
        return Path(os.getenv("ALFRED_DATA_DIR", "./data"))

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "alfred.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def max_upload_bytes(self) -> int:
        return _env_int("MAX_UPLOAD_MB", 20) * 1024 * 1024

    # ---- Web search -------------------------------------------------------
    @property
    def search_max_results(self) -> int:
        return _env_int("SEARCH_MAX_RESULTS", 5)

    # ---- Speech-to-text -------------------------------------------------
    @property
    def whisper_model_size(self) -> str:
        return os.getenv("WHISPER_MODEL_SIZE", "base")

    @property
    def whisper_compute_type(self) -> str:
        # "int8" is a good CPU-friendly default; use "float16" on GPU.
        return os.getenv("WHISPER_COMPUTE_TYPE", "int8")

    @property
    def whisper_language(self) -> str | None:
        # ISO-639-1 code (e.g. "en", "ja"). Empty/unset = auto-detect.
        value = os.getenv("WHISPER_LANGUAGE", "en")
        return value or None

    @property
    def whisper_initial_prompt(self) -> str | None:
        value = os.getenv(
            "WHISPER_INITIAL_PROMPT",
            "The user's name is Atharva. This is a conversation with an AI assistant called ALFRED.",
        )
        return value or None

    # ---- Text-to-speech ---------------------------------------------------
    @property
    def tts_voice(self) -> str:
        return os.getenv("TTS_VOICE", "en-US-GuyNeural")

    @property
    def elevenlabs_api_key(self) -> str:
        return os.getenv("ELEVENLABS_API_KEY", "")

    @property
    def elevenlabs_voice_id(self) -> str:
        return os.getenv("ELEVENLABS_VOICE_ID", "")

    # ---- Database -------------------------------------------------------
    @property
    def database_url(self) -> str:
        # Reserved for Phase 4 (PostgreSQL); the Phase 3 SQLite store ignores it.
        return os.getenv("DATABASE_URL", "sqlite:///./alfred_dev.db")

    # ---- Logging ----------------------------------------------------
    @property
    def log_level(self) -> str:
        return os.getenv("LOG_LEVEL", "INFO").upper()

    # ---- App metadata -------------------------------------------------
    @property
    def app_name(self) -> str:
        return "ALFRED"

    @property
    def environment(self) -> str:
        return os.getenv("ENVIRONMENT", "development")

    def require_gemini_api_key(self) -> str:
        """Raise a clear, actionable error if no Gemini key is configured."""
        if not self.gemini_api_key:
            raise ConfigurationError(
                "GEMINI_API_KEY is not set. Add it to your .env file "
                "(see .env.example). ALFRED never accepts credentials from "
                "the frontend or hard-coded source."
            )
        return self.gemini_api_key


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (safe to call frequently)."""
    return Settings()
