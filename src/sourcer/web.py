"""The web application: server-rendered HTML, with HTMX for the live parts.

One process, one language, no build step. HTMX comes from a CDN, so there is no
bundler, no node_modules and nothing to compile before a reviewer can run this.

Every route is thin. It reads the store, hands dictionaries to a template, and
returns HTML. The JSON endpoint returns the same data for anyone who would
rather script against it than click.
"""

import csv
import io
from pathlib import Path

from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.applications import Starlette
from starlette.routing import Mount, Route

from sourcer import runner, scoring, sources, store, trades
from sourcer.db import connect, init_db
from sourcer.seed import load_seed

HERE = Path(__file__).parent
templates = Jinja2Templates(directory=str(HERE / "templates"))

# Score bands. Defined once here rather than as a comparison repeated in every
# template, because a Business mid-run has no Score yet and comparing None
# against a number raises.
BAND_THRESHOLDS = ((75, "high"), (50, "mid"))


def band_of(score):
    if score is None:
        return "none"
    for threshold, name in BAND_THRESHOLDS:
        if score >= threshold:
            return name
    return "low"


def shown_score(score):
    return "—" if score is None else str(round(score))


templates.env.filters["band"] = band_of
templates.env.filters["shown_score"] = shown_score

# Filters a Searcher can apply to the results table. Kept here because the
# interface is what decides which ones are worth having.
FILTERS = {
    "min_score": ("Minimum score", lambda b, v: (b["score"] or 0) >= float(v)),
    # A Business not yet scored has no Confidence to judge, so it passes. Without
    # this, the default floor hides every row while a run is still working and
    # the streaming table stays empty until scoring finishes.
    "min_confidence": (
        "Minimum confidence",
        lambda b, v: b["confidence"] is None or b["confidence"] >= float(v),
    ),
    "min_years": ("Minimum years trading", lambda b, v: (b["years_in_business"] or 0) >= int(v)),
    "no_website": ("No website only", lambda b, v: not b["website_url"]),
    "owner_known": ("Owner known only", lambda b, v: bool(b["owner_name"])),
    "state": ("Review state", lambda b, v: (b["review_state"] or "new") == v),
}

REVIEW_STATES = ("new", "contacted", "passed")

# A Business scored on under a third of the rubric is a lead to investigate, not
# one to act on, and it should not head the table. Missing data still costs no
# points, so instead of penalising the Score we hide the thinnest rows by
# default and say so, with one click to see them.
DEFAULT_MIN_CONFIDENCE = "0.35"
PROVISIONAL_BELOW = 0.35

EXPORT_COLUMNS = (
    "score", "confidence", "name", "owner_name", "phone_display", "website_url",
    "street", "city", "state", "postal_code", "years_in_business", "founded_year",
    "public_rating", "public_review_count", "categories", "sources", "review_state",
    "review_notes", "key_rule",
)


def _apply_filters(businesses, params):
    """Narrow the list to what the Searcher asked for, ignoring blank fields.

    With no filters at all, a confidence floor is applied so the first thing a
    Searcher reads is trustworthy. It appears in the filter box like any other,
    and clearing it shows everything.
    """
    params = dict(params or {})
    if not any((params.get(key) or "").strip() for key in FILTERS):
        params["min_confidence"] = DEFAULT_MIN_CONFIDENCE

    active = {}
    for key, (_, predicate) in FILTERS.items():
        value = (params.get(key) or "").strip()
        if not value:
            continue
        active[key] = value
        businesses = [b for b in businesses if _safely(predicate, b, value)]
    return businesses, active


def _safely(predicate, business, value):
    try:
        return predicate(business, value)
    except (TypeError, ValueError):
        return True


def _run_context(connection, run_id, params):
    run = store.get_run(connection, run_id)
    if run is None:
        return None
    everything = store.list_businesses(connection, run_id)
    businesses, active = _apply_filters(everything, params or {})
    return {
        "run": run,
        "businesses": businesses,
        "total_count": len(everything),
        "hidden_count": len(everything) - len(businesses),
        "provisional_below": PROVISIONAL_BELOW,
        "active_filters": active,
        "filters": FILTERS,
        "review_states": REVIEW_STATES,
        "group_labels": scoring.GROUP_LABELS,
        "group_totals": scoring.group_totals(),
        "default_min_confidence": DEFAULT_MIN_CONFIDENCE,
        "source_labels": {source.NAME: source.LABEL for source in sources.REGISTRY},
    }


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #


async def home(request):
    connection = connect()
    try:
        recent = store.list_runs(connection, limit=10)
    finally:
        connection.close()

    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "trades": trades.choices(),
            "recent": recent,
            "sources": sources.REGISTRY,
            "default_sources": sources.DEFAULT_NAMES,
            "group_totals": scoring.group_totals(),
            "group_labels": scoring.GROUP_LABELS,
        },
    )


async def start_run(request):
    form = await request.form()
    trade = form.get("trade") or "plumbing"
    city = (form.get("city") or "").strip() or "Austin"
    state = (form.get("state") or "").strip() or "TX"
    chosen = form.getlist("sources") or list(sources.DEFAULT_NAMES)
    pages = int(form.get("pages") or 2)

    run_id = runner.start(trade, city, state, source_names=chosen, page_limit=pages)
    return RedirectResponse(url=f"/runs/{run_id}", status_code=303)


async def view_run(request):
    run_id = int(request.path_params["run_id"])
    connection = connect()
    try:
        context = _run_context(connection, run_id, dict(request.query_params))
    finally:
        connection.close()

    if context is None:
        return HTMLResponse("<h1>No such run</h1>", status_code=404)
    return templates.TemplateResponse(request, "run.html", context)


async def run_rows(request):
    """The live fragment. HTMX swaps this in while the run is working."""
    run_id = int(request.path_params["run_id"])
    connection = connect()
    try:
        context = _run_context(connection, run_id, dict(request.query_params))
    finally:
        connection.close()

    if context is None:
        return HTMLResponse("", status_code=404)
    return templates.TemplateResponse(request, "_rows.html", context)


async def view_business(request):
    business_id = int(request.path_params["business_id"])
    connection = connect()
    try:
        business = store.get_business_detail(connection, business_id)
    finally:
        connection.close()

    if business is None:
        return HTMLResponse("", status_code=404)
    return templates.TemplateResponse(
        request,
        "_detail.html",
        {
            "business": business,
            "group_labels": scoring.GROUP_LABELS,
            "group_totals": scoring.group_totals(),
            "review_states": REVIEW_STATES,
            "provisional_below": PROVISIONAL_BELOW,
        },
    )


async def set_review(request):
    business_id = int(request.path_params["business_id"])
    form = await request.form()
    connection = connect()
    try:
        business = store.get_business_fields(connection, business_id)
        if business is None:
            return HTMLResponse("", status_code=404)
        store.set_review(
            connection,
            business["dedup_key"],
            state=(form.get("state") or None),
            notes=(form.get("notes") or None),
        )
        business = store.get_business_detail(connection, business_id)
    finally:
        connection.close()

    return templates.TemplateResponse(
        request,
        "_detail.html",
        {
            "business": business,
            "group_labels": scoring.GROUP_LABELS,
            "group_totals": scoring.group_totals(),
            "review_states": REVIEW_STATES,
            "provisional_below": PROVISIONAL_BELOW,
        },
    )


async def cancel_run(request):
    run_id = int(request.path_params["run_id"])
    runner.cancel(run_id)
    return RedirectResponse(url=f"/runs/{run_id}", status_code=303)


# --------------------------------------------------------------------------- #
# Export and API
# --------------------------------------------------------------------------- #


def _export_row(business):
    row = {}
    for column in EXPORT_COLUMNS:
        value = business.get(column)
        row[column] = ", ".join(map(str, value)) if isinstance(value, list) else value
    return row


async def export_csv(request):
    """The filtered view, not the whole table. What is on screen is what exports."""
    run_id = int(request.path_params["run_id"])
    connection = connect()
    try:
        run = store.get_run(connection, run_id)
        businesses, _ = _apply_filters(
            store.list_businesses(connection, run_id), dict(request.query_params)
        )
    finally:
        connection.close()

    if run is None:
        return HTMLResponse("", status_code=404)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for business in businesses:
        writer.writerow(_export_row(business))
    buffer.seek(0)

    filename = f"sourcer-{run['trade']}-{run['city']}-{run_id}.csv".replace(" ", "-").lower()
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"content-disposition": f'attachment; filename="{filename}"'},
    )


async def api_run(request):
    run_id = int(request.path_params["run_id"])
    connection = connect()
    try:
        run = store.get_run(connection, run_id)
        if run is None:
            return JSONResponse({"error": "no such run"}, status_code=404)
        businesses, active = _apply_filters(
            store.list_businesses(connection, run_id), dict(request.query_params)
        )
    finally:
        connection.close()

    return JSONResponse({
        "run": run,
        "filters": active,
        "count": len(businesses),
        "businesses": businesses,
    })


async def api_business(request):
    business_id = int(request.path_params["business_id"])
    connection = connect()
    try:
        business = store.get_business_detail(connection, business_id)
    finally:
        connection.close()

    if business is None:
        return JSONResponse({"error": "no such business"}, status_code=404)
    return JSONResponse(business)


async def api_rubric(request):
    """The rubric itself, so a reader can check the weights without the code."""
    return JSONResponse({
        "total_points": scoring.TOTAL_POINTS,
        "groups": [
            {"name": name, "label": scoring.GROUP_LABELS[name], "points": points}
            for name, points in scoring.group_totals().items()
        ],
        "signals": [
            {"name": name, "group": group, "max_points": max_points}
            for name, group, max_points, _ in scoring.SIGNALS
        ],
    })


async def healthz(request):
    return JSONResponse({"status": "ok"})


routes = [
    Route("/", home),
    Route("/runs", start_run, methods=["POST"]),
    Route("/runs/{run_id:int}", view_run),
    Route("/runs/{run_id:int}/rows", run_rows),
    Route("/runs/{run_id:int}/cancel", cancel_run, methods=["POST"]),
    Route("/runs/{run_id:int}/export.csv", export_csv),
    Route("/businesses/{business_id:int}", view_business),
    Route("/businesses/{business_id:int}/review", set_review, methods=["POST"]),
    Route("/api/runs/{run_id:int}", api_run),
    Route("/api/businesses/{business_id:int}", api_business),
    Route("/api/rubric", api_rubric),
    Route("/healthz", healthz),
    Mount("/static", StaticFiles(directory=str(HERE / "static")), name="static"),
]


def build():
    init_db().close()
    try:
        load_seed()
    except Exception:
        # A malformed or absent seed must never stop the application booting.
        pass
    return Starlette(routes=routes)


app = build()
