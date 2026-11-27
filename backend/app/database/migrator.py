"""
Forward-only SQL migrations.

Migration files live in `app/database/migrations/` as `NNN_description.sql`.
Each file runs inside one transaction and is recorded in `schema_migrations`;
applied files are never re-run. A Postgres advisory lock stops two processes
migrating at once.

    python -m app.database.migrator            # apply pending migrations
    python -m app.database.migrator --status   # list applied / pending
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

from app.database.postgres import DatabaseUnavailable, PostgresManager

logger = logging.getLogger("alfred.db.migrate")

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_NAME = re.compile(r"^(\d{3,})_[a-z0-9_]+\.sql$")
_LOCK_ID = 7_4_0_0_1  # arbitrary, fixed advisory-lock key for ALFRED migrations


def discover(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    files = sorted(p for p in directory.glob("*.sql") if _NAME.match(p.name))
    versions = [_NAME.match(p.name).group(1) for p in files]  # type: ignore[union-attr]
    if len(set(versions)) != len(versions):
        raise ValueError("Duplicate migration version numbers found.")
    return files


def applied_versions(db: PostgresManager) -> set[str]:
    with db.connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version TEXT PRIMARY KEY, name TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        return {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}


def migrate(db: PostgresManager, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations in order. Returns the file names applied."""
    applied_now: list[str] = []
    with db.connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK_ID,))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version TEXT PRIMARY KEY, name TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        done = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}
        for path in discover(directory):
            version = _NAME.match(path.name).group(1)  # type: ignore[union-attr]
            if version in done:
                continue
            logger.info("Applying migration %s", path.name)
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (version, name) VALUES (%s, %s)", (version, path.name))
            applied_now.append(path.name)
    return applied_now


def ensure_schema(db: PostgresManager) -> None:
    """Apply pending migrations once per process (cheap no-op afterwards)."""
    if not db.schema_ready:
        migrate(db)
        db.schema_ready = True


def main(argv: list[str] | None = None) -> int:
    from app.config.settings import get_settings

    parser = argparse.ArgumentParser(description="ALFRED PostgreSQL migrations")
    parser.add_argument("--status", action="store_true", help="show applied and pending migrations")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    settings = get_settings()
    db = PostgresManager(
        settings.database_url,
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
        connect_timeout=settings.db_connect_timeout,
    )
    try:
        if args.status:
            done = applied_versions(db)
            for path in discover():
                state = "applied" if _NAME.match(path.name).group(1) in done else "pending"  # type: ignore[union-attr]
                print(f"{state:8} {path.name}")
            return 0
        applied = migrate(db)
        print("Applied: " + ", ".join(applied) if applied else "Database is up to date.")
        return 0
    except DatabaseUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
