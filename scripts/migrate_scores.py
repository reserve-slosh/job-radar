"""One-shot migration: adds score_future, score_salary, score_chance columns to the jobs table.

Usage:
    uv run python scripts/migrate_scores.py
    uv run python scripts/migrate_scores.py --db /path/to/job_radar.db
    uv run python scripts/migrate_scores.py --dry-run

Idempotent: columns that already exist are skipped.
"""

import argparse
import logging
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_NEW_COLUMNS = [
    ("score_future", "INTEGER"),
    ("score_salary", "INTEGER"),
    ("score_chance", "INTEGER"),
    ("status_changed_at", "TEXT"),
]


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def migrate(db_path: str, dry_run: bool = False) -> None:
    if not Path(db_path).exists():
        logger.error("Database not found: %s", db_path)
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    try:
        existing = _existing_columns(conn, "jobs")
        to_add = [(col, col_type) for col, col_type in _NEW_COLUMNS if col not in existing]

        if not to_add:
            logger.info("All columns already exist — nothing to do.")
            return

        for col, col_type in to_add:
            sql = f"ALTER TABLE jobs ADD COLUMN {col} {col_type}"
            if dry_run:
                logger.info("[dry-run] Would execute: %s", sql)
            else:
                conn.execute(sql)
                logger.info("Added column: %s %s", col, col_type)

        if not dry_run:
            conn.commit()
            logger.info("Migration complete.")
    except Exception as e:
        conn.rollback()
        logger.error("Migration failed: %s", e)
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Add score_future/salary/chance columns to jobs table")
    parser.add_argument(
        "--db",
        default=os.environ.get("DB_PATH", "job_radar.db"),
        help="Path to the SQLite database (default: $DB_PATH or job_radar.db)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print SQL statements without executing them",
    )
    args = parser.parse_args()
    migrate(args.db, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
