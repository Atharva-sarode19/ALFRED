"""
Central application configuration.

All configuration is sourced from environment variables (optionally loaded
from a `.env` file). Nothing in this module ever hard-codes a secret or a
model name -- callers must set the corresponding environment variable.
"""

from __future__ import annotations

import os
from functools import lru_cache

try:
    # Optional: only used if python-dotenv is installed. Phase 1 does not
    # hard-require it -- if it's missing we just rely on real env vars.
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - exercised when dotenv isn't installed
    pass


class ConfigurationError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


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

    # ---- Database -------------------------------------------------------
    @property
    def database_url(self) -> str:
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
