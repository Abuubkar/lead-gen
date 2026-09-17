"""Query filters, and the presentation helpers the templates need.

Defined once and applied by the page, the CSV export and the JSON API, so
"export what is on screen" is true by construction rather than by discipline.
"""

REVIEW_STATES = ("new", "contacted", "passed")

# A Business scored on under a third of the rubric is a lead to investigate, not
# one to act on, and it should not head the table. Missing data still costs no
# points, so instead of penalising the Score we hide the thinnest rows by
# default and say so, with one click to see them.
DEFAULT_MIN_CONFIDENCE = "0.35"
PROVISIONAL_BELOW = 0.35

# Each filter is a label and a predicate over one Business row.
FILTERS = {
    "min_score": ("Minimum score", lambda b, v: (b["score"] or 0) >= float(v)),
    # A Business not yet scored has no Confidence to judge, so it passes.
    # Without this, the default floor hides every row while a run is still
    # working and the streaming table stays empty until scoring finishes.
    "min_confidence": (
        "Minimum confidence",
        lambda b, v: b["confidence"] is None or b["confidence"] >= float(v),
    ),
    "min_years": ("Minimum years trading", lambda b, v: (b["years_in_business"] or 0) >= int(v)),
    "no_website": ("No website only", lambda b, v: not b["website_url"]),
    "owner_known": ("Owner known only", lambda b, v: bool(b["owner_name"])),
    "state": ("Review state", lambda b, v: (b["review_state"] or "new") == v),
}


def _safely(predicate, business, value):
    """A malformed filter value narrows nothing rather than failing the request."""
    try:
        return predicate(business, value)
    except (TypeError, ValueError):
        return True


def apply_filters(businesses, params):
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
