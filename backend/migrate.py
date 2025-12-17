"""
Simple SQLite migration runner for this repo (no Alembic).

Convention:
  backend/migrations/*.sql

Each migration is identified by its filename stem
(e.g. 20251215_01_add_v2_and_statsbomb.sql -> 20251215_01_add_v2_and_statsbomb).
Applied migrations are recorded in the schema_migrations table (id TEXT PRIMARY KEY).

Usage:
  python3 -m backend.migrate

Environment:
  DATABASE_PATH can override the DB location (defaults to data/app.db).
"""

import os
import sqlite3
from pathlib import Path


def _db_path():
    # Match backend/db.py behavior (but avoid importing to keep this file standalone)
    return Path(os.getenv("DATABASE_PATH", "data/app.db"))


def _migrations_dir():
    # backend/migrate.py -> backend/migrations
    return Path(__file__).resolve().parent / "migrations"


def _ensure_parent_dir(db_path):
    db_path.parent.mkdir(parents=True, exist_ok=True)


def _connect(db_path):
    _ensure_parent_dir(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _ensure_schema_migrations(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          id TEXT PRIMARY KEY,
          applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )


def _list_sql_files(migrations_dir):
    if not migrations_dir.exists():
        return []
    return sorted(p for p in migrations_dir.iterdir() if p.is_file() and p.suffix.lower() == ".sql")


def _applied_ids(conn):
    _ensure_schema_migrations(conn)
    rows = conn.execute("SELECT id FROM schema_migrations").fetchall()
    return {r["id"] for r in rows}


def apply_migrations():
    db_path = _db_path()
    migrations_dir = _migrations_dir()

    sql_files = list(_list_sql_files(migrations_dir))
    if not sql_files:
        print(f"No migrations found in {migrations_dir}")
        return

    with _connect(db_path) as conn:
        applied = _applied_ids(conn)

        for path in sql_files:
            migration_id = path.stem
            if migration_id in applied:
                print(f"SKIP  {migration_id}")
                continue

            sql_text = path.read_text(encoding="utf-8")

            try:
                conn.executescript(sql_text)
                conn.execute(
                    "INSERT OR IGNORE INTO schema_migrations (id) VALUES (?)",
                    (migration_id,),
                )
                conn.commit()
                print(f"APPLY {migration_id}")
            except Exception:
                conn.rollback()
                print(f"FAIL  {migration_id}")
                raise


if __name__ == "__main__":
    apply_migrations()
