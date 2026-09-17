"""SQLite access.

Plain SQL through the standard library, no ORM. The schema is one readable file
applied on every open, so there is no migration tool and no state where the code
and the database disagree.
"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from sourcer.paths import db_path

SCHEMA_FILE = Path(__file__).with_name("schema.sql")

TABLES = ("search_run", "business", "contact", "signal", "review")


def now():
    """Timestamps are ISO-8601 UTC text. SQLite has no date type, and text sorts."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def connect(path=None):
    """Open a connection with the settings this application depends on.

    Write-ahead logging lets the background worker thread write while a web
    request reads. The busy timeout stops the two from colliding outright.
    Foreign keys are off by default in SQLite and must be enabled per
    connection, or the cascade rules in the schema are decoration.
    """
    target = Path(path) if path else db_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(target, timeout=30.0, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA synchronous = NORMAL")
    return connection


def apply_schema(connection):
    """Create anything missing. Safe to call on an existing database."""
    connection.executescript(SCHEMA_FILE.read_text())
    return connection


def init_db(path=None):
    """Open the database and bring it up to the committed schema."""
    return apply_schema(connect(path))


def table_names(connection):
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        " ORDER BY name"
    ).fetchall()
    return [row["name"] for row in rows]


def index_names(connection):
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' AND name LIKE 'idx_%' ORDER BY name"
    ).fetchall()
    return [row["name"] for row in rows]
