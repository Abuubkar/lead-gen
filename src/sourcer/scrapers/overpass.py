"""OpenStreetMap, through the Overpass API.

The floor beneath the other Sources. No anti-bot, no key, no terms that forbid
this use, and it answered every probe during research. Coverage is strong for
storefront trades and thin for home services, and it carries no age, owner or
Reputation data at all, so a Business found only here scores on little.

It exists so that a Search Run always returns something, even when a richer
Source refuses us.
"""

import json

from sourcer.scrapers.catalog import source_key

NAME = "overpass"
LABEL = "OpenStreetMap"
ENABLED_BY_DEFAULT = True
TIER = "http"

ENDPOINT = "https://overpass-api.de/api/interpreter"

# Overpass is a shared free service. One request per Search Run, and a generous
# server-side timeout rather than several narrower queries.
QUERY_TIMEOUT_SECONDS = 50


def _query(tags, city, state):
    """One Overpass QL query covering every tag pair for the trade.

    Scoped by administrative boundary rather than a bounding box, so "Austin"
    means the city and not a rectangle over central Texas.
    """
    clauses = "".join(f'nwr(area.searched)["{key}"="{value}"];' for key, value in tags)
    return f"""[out:json][timeout:{QUERY_TIMEOUT_SECONDS}];
area["name"="{city}"]["boundary"="administrative"]->.searched;
({clauses});
out tags center;"""


def _street_of(tags):
    number = tags.get("addr:housenumber", "").strip()
    street = tags.get("addr:street", "").strip()
    return f"{number} {street}".strip() or None


def _record(element, state):
    tags = element.get("tags") or {}
    name = (tags.get("name") or "").strip()
    if not name:
        return None

    return {
        "name": name,
        "website_url": tags.get("website") or tags.get("contact:website"),
        "phone_display": tags.get("phone") or tags.get("contact:phone"),
        "street": _street_of(tags),
        "city": tags.get("addr:city"),
        "state": tags.get("addr:state") or state,
        "postal_code": tags.get("addr:postcode"),
        "categories": [
            value
            for value in (
                tags.get("craft"),
                tags.get("shop"),
                tags.get("amenity"),
                tags.get("office"),
            )
            if value
        ],
        # A brand or a franchise tag is a chain marker, which counts against
        # acquirability at step 6.
        "is_franchise": 1 if (tags.get("brand") or tags.get("operator")) else None,
    }


def discover(fetcher, trade_key, city, state, page_limit=1):
    """Businesses of a trade in a city. One request, so page_limit is ignored."""
    tags = source_key(trade_key, NAME)
    if not tags:
        return

    response = fetcher.get(
        f"{ENDPOINT}?data={_query(tags, city, state).replace(chr(10), ' ')}",
        obey_robots=False,  # A public API endpoint, not a crawlable site.
        tier=TIER,
    )
    body = (
        response.body.decode("utf-8", "ignore")
        if isinstance(response.body, bytes)
        else str(response.body)
    )
    for element in json.loads(body).get("elements", []):
        record = _record(element, state)
        if record:
            yield record
