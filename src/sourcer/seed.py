"""The dataset that ships with the repository.

A reviewer who clones this should see a ranked shortlist in the first ten
seconds, without waiting for a scrape, without a browser stack installed, and
without any source having to answer. So real Search Runs are captured to a JSON
file that is committed, and loaded into a fresh database on first boot.

JSON rather than a prebuilt database file, for two reasons. It survives a schema
change, where a committed database would silently disagree with the code. And a
reviewer can read it.
"""

import json
import time

from sourcer import runner, store
from sourcer.db import connect, init_db, transaction
from sourcer.paths import seed_dir

SEED_FILE = "dataset.json"
WAIT_LIMIT_SECONDS = 1800


def seed_path():
    return seed_dir() / SEED_FILE


# --------------------------------------------------------------------------- #
# Building the seed: real runs, captured
# --------------------------------------------------------------------------- #


def seed_runs(markets, trade_keys, pages=2):
    """Run live searches across markets and trades, and collect the results."""
    captured = []
    for market in markets:
        city, _, state = market.partition(",")
        for trade_key in trade_keys:
            run_id = runner.start(trade_key, city.strip(), state.strip(), page_limit=pages)
            print(f"  running {trade_key} in {city.strip()}, {state.strip()} (run {run_id})")
            captured.append(_wait_for(run_id))
    return [run for run in captured if run]


def _wait_for(run_id):
    deadline = time.monotonic() + WAIT_LIMIT_SECONDS
    while time.monotonic() < deadline:
        connection = connect()
        try:
            run = store.get_run(connection, run_id)
            if run["run_status"] in ("done", "failed", "cancelled"):
                return _capture(connection, run)
        finally:
            connection.close()
        time.sleep(4)
    return None


def _capture(connection, run):
    businesses = []
    for business in store.list_businesses(connection, run["id"]):
        detail = store.get_business_detail(connection, business["id"])
        businesses.append(
            {
                "business": {
                    key: value
                    for key, value in detail.items()
                    if key
                    not in (
                        "id",
                        "run_id",
                        "review",
                        "contacts",
                        "signals_by_group",
                        "key_rule",
                        "review_state",
                        "review_notes",
                    )
                },
                "contacts": [
                    {
                        key: value
                        for key, value in contact.items()
                        if key not in ("id", "business_id")
                    }
                    for contact in detail["contacts"]
                ],
                "signals": [
                    {
                        key: value
                        for key, value in signal.items()
                        if key not in ("id", "business_id")
                    }
                    for group in detail["signals_by_group"].values()
                    for signal in group
                ],
            }
        )
    return {
        "run": {key: value for key, value in run.items() if key != "id"},
        "businesses": businesses,
    }


def export_seed(runs):
    directory = seed_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / SEED_FILE
    path.write_text(json.dumps({"runs": runs}, indent=1, sort_keys=True))
    return path


# --------------------------------------------------------------------------- #
# Loading the seed
# --------------------------------------------------------------------------- #

RUN_COLUMNS = (
    "trade",
    "city",
    "state",
    "run_status",
    "progress_note",
    "started_at",
    "finished_at",
    "discovered_count",
    "enriched_count",
    "scored_count",
    "source_outcomes",
    "error",
    "created_at",
)


def load_seed(force=False):
    """Load the shipped dataset, unless the database already has runs."""
    path = seed_path()
    if not path.is_file():
        return 0

    connection = init_db()
    try:
        existing = connection.execute("SELECT COUNT(*) FROM search_run").fetchone()[0]
        if existing and not force:
            return 0
        if existing and force:
            connection.execute("DELETE FROM search_run")

        payload = json.loads(path.read_text())
        loaded = 0
        for captured in payload.get("runs", []):
            with transaction(connection):
                _insert_run(connection, captured)
            loaded += 1
        return loaded
    finally:
        connection.close()


def _insert_run(connection, captured):
    run = captured["run"]
    values = [run.get(column) for column in RUN_COLUMNS]
    values[RUN_COLUMNS.index("source_outcomes")] = json.dumps(run.get("source_outcomes") or {})
    placeholders = ", ".join("?" for _ in RUN_COLUMNS)
    run_id = connection.execute(
        f"INSERT INTO search_run ({', '.join(RUN_COLUMNS)}) VALUES ({placeholders})",
        tuple(values),
    ).lastrowid

    for entry in captured["businesses"]:
        business = dict(entry["business"])
        for column in ("categories", "sources"):
            business[column] = json.dumps(business.get(column) or [])
        business["run_id"] = run_id
        columns = list(business)
        business_id = connection.execute(
            f"INSERT INTO business ({', '.join(columns)})"
            f" VALUES ({', '.join('?' for _ in columns)})",
            tuple(business[column] for column in columns),
        ).lastrowid

        for contact in entry["contacts"]:
            columns = list(contact)
            connection.execute(
                f"INSERT INTO contact (business_id, {', '.join(columns)})"
                f" VALUES (?, {', '.join('?' for _ in columns)})",
                (business_id, *(contact[column] for column in columns)),
            )
        for signal in entry["signals"]:
            columns = list(signal)
            connection.execute(
                f"INSERT INTO signal (business_id, {', '.join(columns)})"
                f" VALUES (?, {', '.join('?' for _ in columns)})",
                (business_id, *(signal[column] for column in columns)),
            )
