"""Orchestrating a Search Run: discover, enrich, score.

Runs in a background thread so the request that starts it returns immediately
and rows appear in the table as they land. That streaming is the best moment in
the tool: a Searcher watches the shortlist assemble instead of staring at a
spinner for four minutes.

No queue and no worker process. One container, one Searcher, minute-long jobs.
A broker would add an operational dependency that buys nothing at this scale.

Source precedence needs no code of its own. Sources run in registry order,
richest first, and merging only ever fills blanks, so the best available answer
for a field is the one that survives.
"""

import threading

from sourcer import llm, scoring, sources, store
from sourcer.db import connect
from sourcer.enrich import enrich
from sourcer.fetch import Blocked, Disallowed, Fetcher

# Per-host politeness during one run. Slower than strictly necessary for a
# single page, because the alternative is being refused for the whole run.
DISCOVERY_DELAY_SECONDS = 10.0
ENRICHMENT_DELAY_SECONDS = 1.5

_cancelled = set()
_cancel_lock = threading.Lock()


def cancel(run_id):
    with _cancel_lock:
        _cancelled.add(run_id)


def is_cancelled(run_id):
    with _cancel_lock:
        return run_id in _cancelled


def _clear_cancel(run_id):
    with _cancel_lock:
        _cancelled.discard(run_id)


def start(trade, city, state, source_names=None, page_limit=3):
    """Record the request, then work it in the background. Returns the run id."""
    connection = connect()
    try:
        run_id = store.create_run(connection, trade, city, state)
    finally:
        connection.close()

    thread = threading.Thread(
        target=_work,
        args=(run_id, trade, city, state, source_names, page_limit),
        name=f"search-run-{run_id}",
        daemon=True,
    )
    thread.start()
    return run_id


def _work(run_id, trade, city, state, source_names, page_limit):
    """The whole run. Never raises: a failure is recorded, not thrown away."""
    connection = connect()
    try:
        store.set_run_status(connection, run_id, "running")
        _discover_all(connection, run_id, trade, city, state, source_names, page_limit)
        if not is_cancelled(run_id):
            _enrich_all(connection, run_id)
        if not is_cancelled(run_id):
            _score_all(connection, run_id)

        if is_cancelled(run_id):
            store.set_progress_note(connection, run_id, "cancelled")
            store.set_run_status(connection, run_id, "cancelled")
        else:
            store.set_progress_note(connection, run_id, "finished")
            store.set_run_status(connection, run_id, "done")
    except Exception as error:
        store.set_run_status(connection, run_id, "failed", error=f"{type(error).__name__}: {error}")
    finally:
        _clear_cancel(run_id)
        connection.close()


def _discover_all(connection, run_id, trade, city, state, source_names, page_limit):
    chosen = sources.selected(source_names)
    with Fetcher(delay_seconds=DISCOVERY_DELAY_SECONDS) as fetcher:
        for source in chosen:
            if is_cancelled(run_id):
                return
            _discover_one(connection, run_id, fetcher, source, trade, city, state, page_limit)


def _discover_one(connection, run_id, fetcher, source, trade, city, state, page_limit):
    """One Source. A refusal is recorded against the run, never retried."""
    store.set_progress_note(connection, run_id, f"searching {source.LABEL}")
    found = 0
    try:
        for record in source.discover(fetcher, trade, city, state, page_limit=page_limit):
            if is_cancelled(run_id):
                break
            store.upsert_business(connection, run_id, record, source.NAME)
            found += 1
            store.bump_run_counts(connection, run_id, discovered=1)
            store.set_progress_note(
                connection, run_id, f"searching {source.LABEL}, {found} found"
            )
    except Blocked as error:
        # The distinction matters to a Searcher: an empty column here means the
        # site refused us, not that the market is empty.
        store.record_source_outcome(
            connection, run_id, source.NAME,
            {"status": "blocked", "found": found, "reason": error.reason},
        )
        return
    except Disallowed as error:
        store.record_source_outcome(
            connection, run_id, source.NAME,
            {"status": "disallowed", "found": found, "reason": str(error)},
        )
        return
    except Exception as error:
        store.record_source_outcome(
            connection, run_id, source.NAME,
            {"status": "error", "found": found, "reason": f"{type(error).__name__}: {error}"},
        )
        return

    store.record_source_outcome(
        connection, run_id, source.NAME, {"status": "ok", "found": found}
    )


CONTACT_FIELDS = ("owner_name", "owner_role", "emails", "phones")
# Findings with no column of their own, held for scoring only.
UNSTORED_FIELDS = ("ownership_language", "succession_language", "franchise_language",
                   "has_booking", "site_builder", "https", "copyright_year",
                   "pages_read", "evidence_url", "site_text")


def _record_contacts(connection, business_id, found, evidence_url):
    """Turn what the site said about people into Contacts."""
    emails = found.get("emails") or []
    phones = found.get("phones") or []
    owner = found.get("owner_name")

    if owner:
        store.add_contact(connection, business_id, {
            "name": owner,
            "role": found.get("owner_role"),
            "email": emails[0] if emails else None,
            "phone": phones[0] if phones else None,
            "source": "website",
            "source_url": evidence_url,
            "confidence": 0.7,
        })
        emails, phones = emails[1:], phones[1:]

    for email in emails[:2]:
        store.add_contact(connection, business_id, {
            "email": email, "source": "website", "source_url": evidence_url, "confidence": 0.5,
        })


def _enrich_all(connection, run_id):
    pending = store.list_businesses_to_enrich(connection, run_id)
    total = len(pending)
    with Fetcher(delay_seconds=ENRICHMENT_DELAY_SECONDS) as fetcher:
        for index, business in enumerate(pending, start=1):
            if is_cancelled(run_id):
                return
            store.set_progress_note(connection, run_id, f"reading websites {index}/{total}")

            found, outcome = enrich(fetcher, business.get("website_url"))

            # The model fills gaps the rules left, and never overrides them.
            # Absent a key it does nothing at all.
            if found.get("site_text") and llm.available():
                store.set_progress_note(connection, run_id, f"reading websites {index}/{total}, AI")
                inferred = llm.read_site(business["name"], found.pop("site_text"))
                for key, value in inferred.items():
                    found.setdefault(key, value)
            found.pop("site_text", None)

            if found:
                store.fill_business(
                    connection,
                    business["id"],
                    {
                        key: value
                        for key, value in found.items()
                        if key not in CONTACT_FIELDS and key not in UNSTORED_FIELDS
                    },
                    "website",
                )
                _record_contacts(
                    connection, business["id"], found, found.get("evidence_url")
                )
                # Held for scoring, which needs the site-derived facts that have
                # no column of their own.
                _remember(business["id"], found)

            store.set_enrichment_status(connection, business["id"], outcome)
            store.bump_run_counts(connection, run_id, enriched=1)


# Facts a website gave us that the schema has no column for, such as the
# copyright year or whether the page offers online booking. Kept for the life of
# the run: they feed Signals, and the Signal rows are what persist them.
_findings = {}
_findings_lock = threading.Lock()


def _remember(business_id, found):
    with _findings_lock:
        _findings[business_id] = found


def _recall(business_id):
    with _findings_lock:
        return _findings.get(business_id, {})


def _forget(business_ids):
    with _findings_lock:
        for business_id in business_ids:
            _findings.pop(business_id, None)


def _score_all(connection, run_id):
    businesses = store.list_businesses(connection, run_id)
    total = len(businesses)
    for index, business in enumerate(businesses, start=1):
        if is_cancelled(run_id):
            return
        store.set_progress_note(connection, run_id, f"scoring {index}/{total}")

        context = {
            **business,
            **_recall(business["id"]),
            "sources_include_bbb": "bbb" in (business.get("sources") or []),
        }
        signals, computed_score, confidence = scoring.assess(context)
        store.replace_signals(connection, business["id"], signals)
        store.set_business_score(connection, business["id"], computed_score, confidence)
        store.bump_run_counts(connection, run_id, scored=1)

    _forget([business["id"] for business in businesses])
