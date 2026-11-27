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

    # ---- Storage and files (SQLite: notes, reminders, documents) ----
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

    # ---- Database (PostgreSQL: persistent memory) ----------------------
    @property
    def database_url(self) -> str | None:
        """DATABASE_URL, or one assembled from POSTGRES_* variables; None = memory disabled."""
        url = (os.getenv("DATABASE_URL") or "").strip()
        if url:
            return url
        name, user = os.getenv("POSTGRES_DB"), os.getenv("POSTGRES_USER")
        if not (name and user):
            return None
        from urllib.parse import quote

        password = quote(os.getenv("POSTGRES_PASSWORD", ""), safe="")
        host, port = os.getenv("POSTGRES_HOST", "localhost"), os.getenv("POSTGRES_PORT", "5432")
        auth = f"{quote(user, safe='')}:{password}" if password else quote(user, safe="")
        return f"postgresql://{auth}@{host}:{port}/{name}"

    @property
    def db_pool_min(self) -> int:
        return _env_int("DB_POOL_MIN", 1)

    @property
    def db_pool_max(self) -> int:
        return max(self.db_pool_min, _env_int("DB_POOL_MAX", 5))

    @property
    def db_connect_timeout(self) -> int:
        return _env_int("DB_CONNECT_TIMEOUT", 5)

    @property
    def db_auto_migrate(self) -> bool:
        return _env_bool("DB_AUTO_MIGRATE", True)

    # ---- Memory (Phase 4) -----------------------------------------------
    @property
    def memory_enabled(self) -> bool:
        return _env_bool("MEMORY_ENABLED", True) and self.database_url is not None

    @property
    def max_context_messages(self) -> int:
        """Most recent messages sent to the model each turn (short-term memory window)."""
        return _env_int("MAX_CONTEXT_MESSAGES", 20)

    @property
    def max_context_chars(self) -> int:
        return _env_int("MAX_CONTEXT_CHARS", 12000, minimum=500)

    @property
    def memory_max_retrieved(self) -> int:
        return _env_int("MEMORY_MAX_RETRIEVED", 5)

    @property
    def memory_min_score(self) -> float:
        raw = os.getenv("MEMORY_MIN_SCORE", "0.15")
        try:
            return float(raw)
        except ValueError as exc:
            raise ConfigurationError(f"MEMORY_MIN_SCORE must be a number, got {raw!r}") from exc

    @property
    def memory_archive_after_days(self) -> int:
        """Unused, low-importance memories older than this are archived at startup."""
        return _env_int("MEMORY_ARCHIVE_AFTER_DAYS", 180)

    @property
    def memory_llm_extraction(self) -> bool:
        """Also ask the LLM to extract memories after each turn (costs one extra call)."""
        return _env_bool("MEMORY_LLM_EXTRACTION", False)

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
