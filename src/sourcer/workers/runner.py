"""Orchestrating a Search Run: discover, enrich, score.

Runs in a background thread so the request that starts it returns immediately
and rows appear in the table as they land. That streaming is the best moment in
the tool: a Searcher watches the shortlist assemble instead of staring at a
spinner for four minutes.

No broker and no worker process: one container, minute-long jobs. But at most
MAX_RUNNING Search Runs work at once, and the rest wait their turn in order.
Each one holds connections and pages in memory, and a small instance that runs
out restarts, losing every run in progress.

Source precedence needs no code of its own. Sources run in registry order,
richest first, and merging only ever fills blanks, so the best available answer
for a field is the one that survives.
"""

import threading

from sourcer.db import repository as store
from sourcer.db.database import connect, init_db
from sourcer.extractors.website import enrich
from sourcer.pipelines import scoring
from sourcer.scrapers import catalog
from sourcer.scrapers import registry as sources
from sourcer.scrapers.client import Blocked, Disallowed, Fetcher, NotConfigured, Unreachable
from sourcer.services import llm

# Per-host politeness during one run. Slower than strictly necessary for a
# single page, because the alternative is being refused for the whole run.
DISCOVERY_DELAY_SECONDS = 10.0
ENRICHMENT_DELAY_SECONDS = 1.5

_cancelled = set()
_cancel_lock = threading.Lock()

# How many Search Runs may work at once. A run is mostly waiting on the network,
# so more would not finish sooner; they would only share the same small machine.
MAX_RUNNING = 3
# How often a waiting run looks again, and refreshes its place in the queue.
WAIT_CHECK_SECONDS = 3.0

_turns = threading.Condition()
_waiting = []  # run ids, oldest first
_running = set()


def _queue_note(place):
    note = f"Waiting to start: {MAX_RUNNING} searches are already running."
    if place == 1:
        return f"{note} 1 search is ahead of yours."
    if place > 1:
        return f"{note} {place} searches are ahead of yours."
    return note


def _take_turn(connection, run_id):
    """Wait until fewer than MAX_RUNNING runs are working and this one is next.

    First come, first served. Returns False if the run was cancelled while it
    waited.
    """
    with _turns:
        _waiting.append(run_id)
    try:
        last_note = None
        while True:
            with _turns:
                if is_cancelled(run_id):
                    return False
                if len(_running) < MAX_RUNNING and _waiting[0] == run_id:
                    _running.add(run_id)
                    return True
                note = _queue_note(_waiting.index(run_id))
            if note != last_note:
                store.set_progress_note(connection, run_id, note)
                last_note = note
            with _turns:
                _turns.wait(timeout=WAIT_CHECK_SECONDS)
    finally:
        with _turns:
            _waiting.remove(run_id)
            _turns.notify_all()


def _end_turn(run_id):
    with _turns:
        _running.discard(run_id)
        _turns.notify_all()


def cancel(run_id):
    with _cancel_lock:
        _cancelled.add(run_id)


def is_cancelled(run_id):
    with _cancel_lock:
        return run_id in _cancelled


def _clear_cancel(run_id):
    with _cancel_lock:
        _cancelled.discard(run_id)


def start(trade, market, source_names=None, page_limit=3):
    """Record the request, then work it in the background. Returns the run id.

    market is a catalogue market: city, region, country and coordinates. The
    mode follows from the trade, since every trade belongs to exactly one.

    Applies the schema first. Starting a run is an entry point into the
    database, reachable from the command line as well as the web app, and
    application is idempotent, so doing it here removes a class of "forgot to
    initialise" rather than relying on some earlier caller.
    """
    mode = catalog.trade_mode(trade) or scoring.DEFAULT_MODE
    connection = init_db()
    try:
        run_id = store.create_run(
            connection, trade, market["city"], market["region"], market["country"], mode
        )
    finally:
        connection.close()

    thread = threading.Thread(
        target=_work,
        args=(run_id, trade, market, mode, source_names, page_limit),
        name=f"search-run-{run_id}",
        daemon=True,
    )
    thread.start()
    return run_id


def _work(run_id, trade, market, mode, source_names, page_limit):
    """The whole run. Never raises: a failure is recorded, not thrown away."""
    connection = connect()
    try:
        if not _take_turn(connection, run_id):
            store.set_progress_note(connection, run_id, "cancelled")
            store.set_run_status(connection, run_id, "cancelled")
            return
        store.set_run_status(connection, run_id, "running")
        _discover_all(connection, run_id, trade, market, source_names, page_limit)
        if not is_cancelled(run_id):
            _enrich_all(connection, run_id, mode)
        if not is_cancelled(run_id):
            _score_all(connection, run_id, mode)

        # The live counts move as the run works; settle them on what the
        # businesses actually are once it stops.
        store.recount(connection, run_id)
        if is_cancelled(run_id):
            store.set_progress_note(connection, run_id, "cancelled")
            store.set_run_status(connection, run_id, "cancelled")
        else:
            store.set_progress_note(connection, run_id, "finished")
            store.set_run_status(connection, run_id, "done")
    except Exception as error:
        store.set_run_status(connection, run_id, "failed", error=f"{type(error).__name__}: {error}")
    finally:
        # Whatever happened, including cancellation or an exception, this run's
        # bookkeeping goes with it, and its turn passes to the next in line.
        _end_turn(run_id)
        _clear_cancel(run_id)
        _forget_run(run_id)
        connection.close()


def rescore(run_id, refetch=True):
    """Bring a finished Search Run up to the current rubric and site reader.

    The Signals a run stored belong to whatever rubric scored it, so a change
    to the rubric leaves old runs showing groups that no longer exist. This
    re-reads each site with the current reader and scores everything again by
    the same path a live run takes, so there is no second scoring route to drift.

    refetch=False rescores from stored columns alone. It is fast, but facts read
    from a site and never given a column (copyright year, platform, HTTPS,
    booking) come back unresolved, so most site Signals go quiet.
    """
    connection = init_db()
    try:
        run = store.get_run(connection, run_id)
        if run is None:
            return None
        mode = run.get("mode") or scoring.DEFAULT_MODE
        store.reset_for_rescore(connection, run_id, refetch)
        _forget_run(run_id)
        if refetch:
            _enrich_all(connection, run_id, mode)
        _score_all(connection, run_id, mode)
        store.recount(connection, run_id)
        store.set_progress_note(connection, run_id, "rescored")
        return run_id
    finally:
        _forget_run(run_id)
        connection.close()


def _discover_all(connection, run_id, trade, market, source_names, page_limit):
    # Only the Sources that can search this trade in this market, the same ones
    # the search page listed. One that cannot would report "0 found", which
    # reads as an empty market rather than a Source with nothing to say.
    chosen = [
        source
        for source in sources.selected(source_names, market["country"])
        if sources.skip_reason(source, trade, market) is None
    ]
    with Fetcher(delay_seconds=DISCOVERY_DELAY_SECONDS) as fetcher:
        for source in chosen:
            if is_cancelled(run_id):
                return
            _discover_one(connection, run_id, fetcher, source, trade, market, page_limit)


def _discover_one(connection, run_id, fetcher, source, trade, market, page_limit):
    """One Source. A refusal is recorded against the run, never retried."""
    # A Source that is slow on first use says so, so a long wait is not
    # mistaken for a hung search.
    wait = getattr(source, "WAIT_NOTE", "")
    looking = f"Looking for businesses in {source.LABEL}"
    store.set_progress_note(connection, run_id, f"{looking}. {wait}".strip())
    found = 0
    try:
        for record in source.discover(fetcher, trade, market, page_limit=page_limit):
            if is_cancelled(run_id):
                break
            store.upsert_business(connection, run_id, record, source.NAME)
            found += 1
            store.bump_run_counts(connection, run_id, discovered=1)
            store.set_progress_note(connection, run_id, f"{looking}: {found} so far")
    except NotConfigured as error:
        # Zero results from a Source that was never set up says nothing about
        # the market, so it must not read as an empty one.
        store.record_source_outcome(
            connection,
            run_id,
            source.NAME,
            {"status": "not_configured", "found": found, "reason": error.needs},
        )
        return
    except Unreachable as error:
        # Caught before Blocked, which it subclasses: a server that did not
        # answer is not refusing us, and saying so sends a rep the wrong way.
        store.record_source_outcome(
            connection,
            run_id,
            source.NAME,
            {"status": "unreachable", "found": found, "reason": error.reason},
        )
        return
    except Blocked as error:
        # The distinction matters to a rep: an empty column here means the
        # site refused us, not that the market is empty.
        store.record_source_outcome(
            connection,
            run_id,
            source.NAME,
            {"status": "blocked", "found": found, "reason": error.reason},
        )
        return
    except Disallowed as error:
        store.record_source_outcome(
            connection,
            run_id,
            source.NAME,
            {"status": "disallowed", "found": found, "reason": str(error)},
        )
        return
    except Exception as error:
        store.record_source_outcome(
            connection,
            run_id,
            source.NAME,
            {"status": "error", "found": found, "reason": f"{type(error).__name__}: {error}"},
        )
        return

    store.record_source_outcome(connection, run_id, source.NAME, {"status": "ok", "found": found})


# Findings that become Contacts. owner_name is deliberately NOT here: it is
# both a Contact and a column on the Business, because the results table shows
# it and the rubric scores it.
CONTACT_FIELDS = ("owner_role", "emails", "phones")
# Findings with no column of their own, held for scoring only.
UNSTORED_FIELDS = (
    "ownership_language",
    "succession_language",
    "franchise_language",
    "has_booking",
    "site_builder",
    "https",
    "copyright_year",
    "mentions_ai",
    "has_careers",
    "pages_read",
    "evidence_url",
    "site_text",
    "_model_keys",
    "_website_keys",
)


def _record_contacts(connection, business_id, found, evidence_url):
    """Turn what the site said about people into Contacts."""
    emails = found.get("emails") or []
    phones = found.get("phones") or []
    owner = found.get("owner_name")

    if owner:
        store.add_contact(
            connection,
            business_id,
            {
                "name": owner,
                "role": found.get("owner_role"),
                "email": emails[0] if emails else None,
                "phone": phones[0] if phones else None,
                "source": "website",
                "source_url": evidence_url,
                "confidence": 0.7,
            },
        )
        emails, phones = emails[1:], phones[1:]

    for email in emails[:2]:
        store.add_contact(
            connection,
            business_id,
            {
                "email": email,
                "source": "website",
                "source_url": evidence_url,
                "confidence": 0.5,
            },
        )


def _enrich_all(connection, run_id, mode):
    pending = store.list_businesses_to_enrich(connection, run_id)
    total = len(pending)
    with Fetcher(delay_seconds=ENRICHMENT_DELAY_SECONDS) as fetcher:
        for index, business in enumerate(pending, start=1):
            if is_cancelled(run_id):
                return
            store.set_progress_note(connection, run_id, f"Reading websites: {index} of {total}")

            found, outcome = enrich(fetcher, business.get("website_url"))

            # The model fills gaps the rules left, and never overrides them.
            # Absent a key it does nothing at all.
            model_keys = []
            if found.get("site_text") and llm.available():
                note = f"Reading websites: {index} of {total}, with the model"
                store.set_progress_note(connection, run_id, note)
                inferred = llm.read_site(business["name"], found.pop("site_text"))
                for key, value in inferred.items():
                    if key not in found:
                        found[key] = value
                        model_keys.append(key)
            found.pop("site_text", None)

            # Which facts came from where. A Signal built on a model's guess
            # must say so, because a guess is weaker evidence than a page we
            # read, and the Score is meant to be auditable.
            if found:
                found["_model_keys"] = tuple(model_keys)
                found["_website_keys"] = tuple(
                    key for key in found if not key.startswith("_") and key not in model_keys
                )

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
                _record_contacts(connection, business["id"], found, found.get("evidence_url"))
                # Held for scoring, which needs the site-derived facts that have
                # no column of their own.
                _remember(run_id, business["id"], found)

            store.set_enrichment_status(connection, business["id"], outcome)
            # "Sites read" means sites read. A business with no website passes
            # through here too and is skipped; counting it reported 200 sites
            # read on a run where not one had a website to read.
            if outcome == "ok":
                store.bump_run_counts(connection, run_id, enriched=1)
            # Scored here rather than in a later pass. The table streams while
            # the run works, and a row with no Score yet reads as a Business
            # worth nothing rather than one not yet judged.
            business_now = store.get_business_fields(connection, business["id"])
            _score_one(connection, run_id, business_now, mode)


# Facts a website gave us that the schema has no column for, such as the
# copyright year or whether the page offers online booking. Kept for the life of
# one run and dropped with it: they feed Signals, and the Signal rows are what
# persist them.
#
# Keyed by run, not by Business, so a cancelled or failed run cannot orphan its
# entries for the lifetime of the process.
_findings = {}
_findings_lock = threading.Lock()

# Which Businesses of a run already carry a Score, so neither the Enrichment
# step nor the pass after it scores one twice and counts it twice.
_scored = {}
_scored_lock = threading.Lock()


def _remember(run_id, business_id, found):
    with _findings_lock:
        _findings.setdefault(run_id, {})[business_id] = found


def _recall(run_id, business_id):
    with _findings_lock:
        return _findings.get(run_id, {}).get(business_id, {})


def _forget_run(run_id):
    with _findings_lock:
        _findings.pop(run_id, None)
    with _scored_lock:
        _scored.pop(run_id, None)


def _score_one(connection, run_id, business, mode):
    """Signals and Score for one Business. Skips a Business already scored.

    Enrichment scores each Business it reads, and the pass that follows catches
    the rest, so the guard is what stops a Business being counted twice.
    """
    if business is None:
        return
    with _scored_lock:
        already = _scored.setdefault(run_id, set())
        if business["id"] in already:
            return
        already.add(business["id"])

    context = {
        **business,
        **_recall(run_id, business["id"]),
    }
    signals, computed_score, confidence = scoring.assess(context, mode)
    store.replace_signals(connection, business["id"], signals)
    store.set_business_score(connection, business["id"], computed_score, confidence)
    # Counted only when a Score came out. A business with no evidence in its
    # core group is assessed but left unscored, and counting it claimed scores
    # for businesses that have none.
    if computed_score is not None:
        store.bump_run_counts(connection, run_id, scored=1)


def _score_all(connection, run_id, mode):
    """Everything Enrichment did not already score: the Businesses with no site."""
    businesses = store.list_businesses(connection, run_id)
    total = len(businesses)
    for index, business in enumerate(businesses, start=1):
        if is_cancelled(run_id):
            return
        store.set_progress_note(connection, run_id, f"Scoring: {index} of {total}")
        _score_one(connection, run_id, business, mode)
