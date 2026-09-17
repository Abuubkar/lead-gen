"""SQLite access.

Plain SQL through the standard library, no ORM. The schema is one readable file
applied on every open, so there is no migration step to forget and no state
where the code and the database disagree.
"""

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sourcer.paths import db_path

SCHEMA_FILE = Path(__file__).with_name("schema.sql")


def now():
    """Timestamps are ISO-8601 UTC text. SQLite has no date type, and text sorts."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def connect(path=None):
    """Open a connection with the settings this application depends on.

    Write-ahead logging lets the background worker thread write while a web
    request reads, and the busy timeout stops the two colliding outright.
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


def init_db(path=None):
    """Open the database and create anything the committed schema is missing.

    Safe to call on an existing database: every statement in the schema file is
    idempotent. Called on every open, so `sourcer init-db` is a convenience for
    inspecting the result, not a setup step the application depends on.
    """
    connection = connect(path)
    connection.executescript(SCHEMA_FILE.read_text())
    return connection


@contextmanager
def transaction(connection):
    """Wrap a unit of work so it lands whole or not at all.

    Connections run in autocommit mode, which suits single statements and is
    wrong for a Business and its Signals, which must appear together or not at
    all. SQLite has no nested transactions, so this does not nest.
    """
    connection.execute("BEGIN")
    try:
        yield connection
    except Exception:
        connection.execute("ROLLBACK")
        raise
    connection.execute("COMMIT")


# What counts as SQLite's own business rather than our schema, per object kind.
# Tables: sqlite_sequence is AUTOINCREMENT bookkeeping. Indexes: only the
# statistics tables are internal, because sqlite_autoindex_* entries ARE our
# UNIQUE constraints, and those are the dedup and re-scoring guarantees.
_INTERNAL_PREFIX = {"table": "sqlite_", "index": "sqlite_stat"}


def object_names(connection, kind):
    """Names of every table or index belonging to our schema."""
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = ? AND name NOT LIKE ? ORDER BY name",
        (kind, _INTERNAL_PREFIX[kind] + "%"),
    ).fetchall()
    return [row["name"] for row in rows]


def describe(path=None):
    """What the database contains, for the CLI and for eyeballing a deployment."""
    connection = init_db(path)
    try:
        return {
            "path": str(path or db_path()),
            "tables": object_names(connection, "table"),
            "indexes": object_names(connection, "index"),
        }
    finally:
        connection.close()
