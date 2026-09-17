"""Every read and write of application data.

No module outside this one writes SQL against the five tables. Callers pass a
connection and get plain dictionaries back, with JSON columns already decoded,
so nothing downstream handles raw rows, raw JSON text, or a timestamp it has to
format itself.

Merge policy lives in merge.py, not here. The store persists a Score and the
Signals behind it but never computes or adjusts either. See ADR 0002.
"""

import json

from sourcer.db import now
from sourcer.identity import DEDUP_RULES, dedup_keys, key_rule_of, resolve_dedup_key
from sourcer.merge import plan_merge

# Columns holding a JSON document as text.
JSON_COLUMNS = ("categories", "sources", "source_outcomes")

# Everything a Source or Enrichment may supply about a Business. The dedup key
# columns are derived, never passed in, so they are absent here.
BUSINESS_FIELDS = (
    "name",
    "website_url",
    "phone_display",
    "street",
    "city",
    "state",
    "postal_code",
    "categories",
    "years_in_business",
    "founded_year",
    "owner_name",
    "employee_estimate",
    "public_rating",
    "public_review_count",
    "location_count",
    "is_franchise",
    "outreach_angle",
)

TERMINAL_RUN_STATUSES = ("done", "failed", "cancelled")


def _decode(value):
    return json.loads(value) if value else None


def _row(row):
    """A database row as a plain dictionary, with its JSON columns decoded."""
    if row is None:
        return None
    record = dict(row)
    for column in JSON_COLUMNS:
        if column in record:
            record[column] = _decode(record[column])
    return record


def _rows(rows):
    return [_row(row) for row in rows]


# --------------------------------------------------------------------------- #
# Search Run
# --------------------------------------------------------------------------- #


def create_run(connection, trade, city, state):
    """Record a Searcher's request. Starts pending; nothing has run yet."""
    cursor = connection.execute(
        "INSERT INTO search_run (trade, city, state, run_status, created_at)"
        " VALUES (?, ?, ?, 'pending', ?)",
        (trade, city, state, now()),
    )
    return cursor.lastrowid


def _timestamp_column_for(run_status):
    """Which time column a status transition stamps, if any."""
    if run_status == "running":
        return "started_at"
    return "finished_at" if run_status in TERMINAL_RUN_STATUSES else None


def set_run_status(connection, run_id, run_status, error=None):
    """Move a Search Run through its lifecycle, stamping the matching time.

    Entering `running` sets the start time; reaching any terminal status sets
    the finish time, so neither has to be remembered by a caller.
    """
    assignments = ["run_status = ?", "error = ?"]
    params = [run_status, error]

    stamped = _timestamp_column_for(run_status)
    if stamped:
        assignments.append(f"{stamped} = ?")
        params.append(now())

    connection.execute(
        f"UPDATE search_run SET {', '.join(assignments)} WHERE id = ?", (*params, run_id)
    )


def set_progress_note(connection, run_id, note):
    """The single line shown while a Search Run is still working."""
    connection.execute("UPDATE search_run SET progress_note = ? WHERE id = ?", (note, run_id))


def bump_run_counts(connection, run_id, discovered=0, enriched=0, scored=0):
    """Add to the running counts in SQL rather than in Python.

    Read-modify-write here would lose updates, because the worker thread
    reports progress while the web layer is reading the same row.
    """
    connection.execute(
        "UPDATE search_run SET discovered_count = discovered_count + ?,"
        " enriched_count = enriched_count + ?, scored_count = scored_count + ? WHERE id = ?",
        (discovered, enriched, scored, run_id),
    )


def record_source_outcome(connection, run_id, source, outcome):
    """Merge one Source's outcome into the run, leaving the others untouched.

    Merged by SQLite rather than read-modify-write in Python, so two Sources
    reporting at the same moment cannot clobber each other. An empty column
    must read as a Source problem, never as an absence of Businesses, which is
    why a blocked Source records itself here.
    """
    connection.execute(
        "UPDATE search_run SET source_outcomes ="
        " json_set(source_outcomes, '$.\"' || ? || '\"', json(?)) WHERE id = ?",
        (source, json.dumps(outcome), run_id),
    )


def get_run(connection, run_id):
    return _row(connection.execute("SELECT * FROM search_run WHERE id = ?", (run_id,)).fetchone())


def list_runs(connection, limit=20):
    return _rows(
        connection.execute(
            "SELECT * FROM search_run ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()
    )


# --------------------------------------------------------------------------- #
# Business
# --------------------------------------------------------------------------- #


def _encoded_values(record):
    """Only the known Business fields, with JSON columns encoded."""
    values = {}
    for field in BUSINESS_FIELDS:
        if field not in record:
            continue
        value = record[field]
        values[field] = json.dumps(value) if field in JSON_COLUMNS and value is not None else value
    return values


def _find_existing(connection, run_id, keys, dedup_key):
    """A Business in this run matching any of the candidate keys.

    Matching on all three, not only the one that won, is what lets a Source
    that supplied just a phone merge with one that supplied just a domain.
    """
    clauses = ["dedup_key = ?"]
    params = [dedup_key]
    for column in DEDUP_RULES:
        if keys.get(column):
            clauses.append(f"{column} = ?")
            params.append(keys[column])
    row = connection.execute(
        f"SELECT * FROM business WHERE run_id = ? AND ({' OR '.join(clauses)}) ORDER BY id LIMIT 1",
        (run_id, *params),
    ).fetchone()
    return _row(row)


def _apply_updates(connection, business_id, updates):
    """Write a planned set of column updates, or nothing if there are none."""
    if not updates:
        return False
    assignments = ", ".join(f"{column} = ?" for column in updates)
    connection.execute(
        f"UPDATE business SET {assignments}, updated_at = ? WHERE id = ?",
        (*updates.values(), now(), business_id),
    )
    return True


def upsert_business(connection, run_id, record, source):
    """Store a scraped record, merging it into a matching Business if one exists.

    Returns the Business id and whether it was newly inserted. What a merge
    changes is decided by merge.plan_merge, not here.
    """
    keys = dedup_keys(record)
    dedup_key, _ = resolve_dedup_key(record, keys)
    values = _encoded_values(record)

    existing = _find_existing(connection, run_id, keys, dedup_key)
    if existing:
        _apply_updates(connection, existing["id"], plan_merge(existing, values, keys, source))
        return existing["id"], False

    timestamp = now()
    columns = {
        **values,
        **{column: keys.get(column) for column in DEDUP_RULES},
        "run_id": run_id,
        "dedup_key": dedup_key,
        "sources": json.dumps([source] if source else []),
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    placeholders = ", ".join("?" for _ in columns)
    cursor = connection.execute(
        f"INSERT INTO business ({', '.join(columns)}) VALUES ({placeholders})",
        tuple(columns.values()),
    )
    return cursor.lastrowid, True


def fill_business(connection, business_id, values, source):
    """Add what Enrichment learned, without overwriting what Discovery found."""
    existing = get_business_fields(connection, business_id)
    if existing is None:
        return False
    return _apply_updates(
        connection, business_id, plan_merge(existing, _encoded_values(values), {}, source)
    )


def list_businesses_to_enrich(connection, run_id):
    """Businesses in a run that Enrichment has not yet attempted."""
    return _rows(
        connection.execute(
            "SELECT * FROM business WHERE run_id = ? AND enrichment_status = 'pending'"
            " ORDER BY id",
            (run_id,),
        ).fetchall()
    )


def set_business_score(connection, business_id, score, confidence):
    """Persist a computed Score. This module never computes one."""
    connection.execute(
        "UPDATE business SET score = ?, confidence = ?, updated_at = ? WHERE id = ?",
        (score, confidence, now(), business_id),
    )


def set_enrichment_status(connection, business_id, status):
    connection.execute(
        "UPDATE business SET enrichment_status = ?, updated_at = ? WHERE id = ?",
        (status, now(), business_id),
    )


def get_business_fields(connection, business_id):
    """Just the Business row. get_business_detail assembles the whole aggregate."""
    business = _row(
        connection.execute("SELECT * FROM business WHERE id = ?", (business_id,)).fetchone()
    )
    if business is not None:
        business["key_rule"] = key_rule_of(business)
    return business


# --------------------------------------------------------------------------- #
# Contact
# --------------------------------------------------------------------------- #


def add_contact(connection, business_id, contact):
    cursor = connection.execute(
        "INSERT INTO contact (business_id, name, role, email, phone, source, source_url,"
        " confidence, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            business_id,
            contact.get("name"),
            contact.get("role"),
            contact.get("email"),
            contact.get("phone"),
            contact.get("source"),
            contact.get("source_url"),
            contact.get("confidence"),
            now(),
        ),
    )
    return cursor.lastrowid


def list_contacts(connection, business_id):
    return _rows(
        connection.execute(
            "SELECT * FROM contact WHERE business_id = ? ORDER BY id", (business_id,)
        ).fetchall()
    )


# --------------------------------------------------------------------------- #
# Signal
# --------------------------------------------------------------------------- #


def replace_signals(connection, business_id, signals):
    """Write the full set of Signals for a Business.

    Replaces, as the name says: any Signal absent from this set is deleted
    first, because a Signal dropped from the rubric would otherwise linger and
    skew a Confidence that is meant to be computable from these rows alone.
    The rest are upserted on the Business and name pair, so a second scoring
    pass updates rather than accumulating duplicates. A Signal that could not be
    observed is stored with zero points and marked unresolved.
    """
    timestamp = now()
    names = [signal["name"] for signal in signals]
    placeholders = ", ".join("?" for _ in names)
    connection.execute(
        "DELETE FROM signal WHERE business_id = ?"
        + (f" AND name NOT IN ({placeholders})" if names else ""),
        (business_id, *names),
    )
    for signal in signals:
        resolved = 1 if signal.get("resolved") else 0
        connection.execute(
            "INSERT INTO signal (business_id, name, group_name, raw_value, points, max_points,"
            " resolved, source, source_url, observed_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (business_id, name) DO UPDATE SET"
            " group_name = excluded.group_name, raw_value = excluded.raw_value,"
            " points = excluded.points, max_points = excluded.max_points,"
            " resolved = excluded.resolved, source = excluded.source,"
            " source_url = excluded.source_url, observed_at = excluded.observed_at",
            (
                business_id,
                signal["name"],
                signal["group_name"],
                signal.get("raw_value"),
                signal.get("points") or 0,
                signal["max_points"],
                resolved,
                signal.get("source"),
                signal.get("source_url"),
                timestamp,
            ),
        )
    return len(signals)


def list_signals(connection, business_id):
    return _rows(
        connection.execute(
            "SELECT * FROM signal WHERE business_id = ? ORDER BY group_name, name", (business_id,)
        ).fetchall()
    )


# --------------------------------------------------------------------------- #
# Review State
# --------------------------------------------------------------------------- #


def get_review(connection, dedup_key):
    return _row(
        connection.execute("SELECT * FROM review WHERE dedup_key = ?", (dedup_key,)).fetchone()
    )


def set_review(connection, dedup_key, state=None, notes=None):
    """Record what the Searcher decided, keyed on identity rather than on a row.

    Keyed on dedup_key so a Searcher's judgement outlives any particular Search
    Run. Only the arguments supplied are written, so setting a note does not
    clear a state.
    """
    timestamp = now()
    # Two statements on purpose. A single upsert cannot both default the state
    # on insert and leave an existing state alone on update: whatever it
    # supplies as the inserted value is the value the update would adopt. So
    # ensure the row exists, letting the column default apply, then write only
    # the arguments actually supplied.
    connection.execute(
        "INSERT INTO review (dedup_key, updated_at) VALUES (?, ?)"
        " ON CONFLICT (dedup_key) DO NOTHING",
        (dedup_key, timestamp),
    )
    connection.execute(
        "UPDATE review SET state = COALESCE(?, state), notes = COALESCE(?, notes),"
        " updated_at = ? WHERE dedup_key = ?",
        (state, notes, timestamp, dedup_key),
    )


# --------------------------------------------------------------------------- #
# Reads for the interface
# --------------------------------------------------------------------------- #


def list_businesses(connection, run_id):
    """The Businesses of a Search Run, best first.

    Unscored rows sort after scored ones rather than mixing in, so the top of
    the table is always worth reading. Each row carries the Searcher's own
    Review State, joined on identity, and the rule that produced its key, so a
    weak identity is visible.
    """
    businesses = _rows(
        connection.execute(
            "SELECT business.*, review.state AS review_state, review.notes AS review_notes"
            " FROM business LEFT JOIN review ON review.dedup_key = business.dedup_key"
            " WHERE business.run_id = ?"
            " ORDER BY business.score IS NULL, business.score DESC,"
            " business.confidence DESC, business.name",
            (run_id,),
        ).fetchall()
    )
    for business in businesses:
        business["key_rule"] = key_rule_of(business)
    return businesses


def get_business_detail(connection, business_id):
    """One Business with everything needed to audit its Score."""
    business = get_business_fields(connection, business_id)
    if business is None:
        return None

    grouped = {}
    for signal in list_signals(connection, business_id):
        grouped.setdefault(signal["group_name"], []).append(signal)

    business["review"] = get_review(connection, business["dedup_key"])
    business["contacts"] = list_contacts(connection, business_id)
    business["signals_by_group"] = grouped
    return business
