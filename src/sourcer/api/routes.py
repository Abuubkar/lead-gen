"""HTTP handlers: server-rendered HTML, with HTMX for the live parts.

One process, one language, no build step. HTMX comes from a CDN, so there is no
bundler, no node_modules and nothing to compile before a reviewer can run this.

Every route is thin. It reads the repository, hands dictionaries to a template,
and returns HTML. The JSON endpoints return the same data for anyone who would
rather script against it than click. Filtering lives in filters.py and CSV in
export.py, so all three surfaces agree by construction.
"""

from pathlib import Path

from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.routing import Mount, Route

from sourcer.api.export import filename_for, to_csv
from sourcer.api.filters import (
    DEFAULT_MIN_CONFIDENCE,
    FILTERS,
    PROVISIONAL_BELOW,
    REVIEW_STATES,
    apply_filters,
    band_of,
    shown_score,
)
from sourcer.db import repository as store
from sourcer.db.database import connect
from sourcer.pipelines import scoring
from sourcer.scrapers import catalog as trades
from sourcer.scrapers import registry as sources
from sourcer.workers import runner

HERE = Path(__file__).parent
templates = Jinja2Templates(directory=str(HERE / "templates"))


templates.env.filters["band"] = band_of
templates.env.filters["shown_score"] = shown_score


def _run_context(connection, run_id, params):
    run = store.get_run(connection, run_id)
    if run is None:
        return None
    everything = store.list_businesses(connection, run_id)
    businesses, active = apply_filters(everything, params or {})
    return {
        "run": run,
        "businesses": businesses,
        "breakdown": store.group_breakdown(connection, run_id),
        "groups": list(scoring.GROUP_LABELS),
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
            "markets": trades.markets(),
            "recent": recent,
            "sources": sources.REGISTRY,
            "default_sources": sources.DEFAULT_NAMES,
            "group_totals": scoring.group_totals(),
            "group_labels": scoring.GROUP_LABELS,
        },
    )


async def start_run(request):
    form = await request.form()
    trade = (form.get("trade") or "").strip()
    # One field, because a city and a state are only meaningful together: the
    # pair is what a Source turns into a path. Older callers may still send the
    # two separately.
    market = (form.get("market") or "").strip()
    if market:
        city, _, state = market.partition(",")
    else:
        city, state = form.get("city") or "", form.get("state") or ""
    city, state = city.strip(), state.strip().upper()
    # These used to fall back to a default in silence, which searched something
    # the Searcher did not ask for and returned nothing much.
    if not trades.is_trade(trade):
        return HTMLResponse("<h1>Not a trade we have a mapping for</h1>", status_code=400)
    if not trades.is_market(city, state):
        return HTMLResponse("<h1>Not a market we cover</h1>", status_code=400)
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


async def export_csv(request):
    """The filtered view, not the whole table. What is on screen is what exports."""
    run_id = int(request.path_params["run_id"])
    connection = connect()
    try:
        run = store.get_run(connection, run_id)
        businesses, _ = apply_filters(
            store.list_businesses(connection, run_id), dict(request.query_params)
        )
    finally:
        connection.close()

    if run is None:
        return HTMLResponse("", status_code=404)

    body = to_csv(businesses)
    return StreamingResponse(
        iter([body]),
        media_type="text/csv",
        headers={"content-disposition": f'attachment; filename="{filename_for(run)}"'},
    )


async def api_run(request):
    run_id = int(request.path_params["run_id"])
    connection = connect()
    try:
        run = store.get_run(connection, run_id)
        if run is None:
            return JSONResponse({"error": "no such run"}, status_code=404)
        businesses, active = apply_filters(
            store.list_businesses(connection, run_id), dict(request.query_params)
        )
    finally:
        connection.close()

    return JSONResponse(
        {
            "run": run,
            "filters": active,
            "count": len(businesses),
            "businesses": businesses,
        }
    )


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
    return JSONResponse(
        {
            "total_points": scoring.TOTAL_POINTS,
            "groups": [
                {"name": name, "label": scoring.GROUP_LABELS[name], "points": points}
                for name, points in scoring.group_totals().items()
            ],
            "signals": [
                {
                    "name": name,
                    "group": group,
                    "max_points": max_points,
                    "reads": list(reads),
                }
                for name, group, max_points, _, reads in scoring.SIGNALS
            ],
        }
    )


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
