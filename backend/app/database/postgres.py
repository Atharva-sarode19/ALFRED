"""
PostgreSQL connection management for Phase 4 (persistent memory).

A single `PostgresManager` owns a psycopg connection pool. Everything else
(repositories, services) borrows connections from it through `connection()` /
`transaction()`. Calls are synchronous; use `await db.run(fn, ...)` from async
code to keep the event loop free (the same convention as `SQLiteStore.run`).

Connection failures never crash the app: the pool opens lazily, `DatabaseUnavailable`
is raised for callers to handle, and `check()` reports health without raising.
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

logger = logging.getLogger("alfred.db")
_RETRY_COOLDOWN_SECONDS = 15.0


class DatabaseUnavailable(RuntimeError):
    """PostgreSQL is not configured or cannot be reached."""


def redact_dsn(dsn: str) -> str:
    """The DSN with any password removed, safe to log."""
    if "://" in dsn:
        parts = urlsplit(dsn)
        if parts.password:
            netloc = f"{parts.username}:***@{parts.hostname}" + (f":{parts.port}" if parts.port else "")
            return urlunsplit(parts._replace(netloc=netloc))
        return dsn
    return re.sub(r"password\s*=\s*\S+", "password=***", dsn)


class PostgresManager:
    def __init__(self, dsn: str | None, *, min_size: int = 1, max_size: int = 5, connect_timeout: int = 5):
        self._dsn = dsn
        self._min_size = min_size
        self._max_size = max_size
        self._connect_timeout = connect_timeout
        self._pool: ConnectionPool | None = None
        self._lock = threading.Lock()
        self._down_until = 0.0
        self.schema_ready = False

    @property
    def configured(self) -> bool:
        return bool(self._dsn)

    # ---- pool lifecycle -------------------------------------------------
    def _get_pool(self) -> ConnectionPool:
        if not self._dsn:
            raise DatabaseUnavailable("DATABASE_URL is not configured; persistent memory is disabled.")
        with self._lock:
            if self._pool is None:
                if time.monotonic() < self._down_until:
                    raise DatabaseUnavailable("PostgreSQL is unreachable (retrying shortly).")
                pool = ConnectionPool(
                    self._dsn,
                    min_size=self._min_size,
                    max_size=self._max_size,
                    timeout=self._connect_timeout,
                    kwargs={"row_factory": dict_row, "connect_timeout": self._connect_timeout},
                    open=False,
                )
                try:
                    pool.open(wait=True, timeout=self._connect_timeout)
                except (PoolTimeout, psycopg.Error) as exc:
                    pool.close()
                    self._down_until = time.monotonic() + _RETRY_COOLDOWN_SECONDS
                    raise DatabaseUnavailable(self._explain(exc)) from exc
                self._pool = pool
            return self._pool

    def _explain(self, exc: Exception) -> str:
        return f"Could not connect to PostgreSQL at {redact_dsn(self._dsn or '')}: {exc}"

    def close(self) -> None:
        with self._lock:
            if self._pool is not None:
                self._pool.close()
                self._pool = None

    # ---- connections ----------------------------------------------------
    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection]:
        """A pooled connection; commits on success, rolls back on error (one transaction)."""
        pool = self._get_pool()
        try:
            with pool.connection() as conn:
                yield conn
        except (PoolTimeout, psycopg.OperationalError) as exc:
            raise DatabaseUnavailable(self._explain(exc)) from exc

    transaction = connection

    async def run(self, fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(fn, *args, **kwargs)

    # ---- health -----------------------------------------------------------
    def check(self) -> dict[str, Any]:
        """Connectivity report; never raises."""
        if not self.configured:
            return {"configured": False, "connected": False, "detail": "DATABASE_URL is not set."}
        try:
            with self.connection() as conn:
                version = conn.execute("SHOW server_version").fetchone()["server_version"]
            return {"configured": True, "connected": True, "server_version": version}
        except DatabaseUnavailable as exc:
            return {"configured": True, "connected": False, "detail": str(exc)}
