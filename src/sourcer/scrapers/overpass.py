"""OpenStreetMap, through the Overpass API.

The one Source that covers all three countries. No key, and the data is under
the Open Database Licence, which allows commercial use with attribution: the
interface credits OpenStreetMap contributors and links the licence.

Coverage is strong for storefronts and thin for home services. A business found
only here carries little: OpenStreetMap recorded a website for one in fifty-seven
of the businesses it alone found in a real run, so its silence on a website is
not taken as evidence of none (see scoring.SOURCES_REPORTING_WEBSITE).

Which server answers is configuration, not code; see config.overpass_url. The
public instance asks commercial users to use a paid or self-hosted one.
"""

import json
from urllib.parse import urlencode

from sourcer.config import overpass_url
from sourcer.scrapers.catalog import source_key

NAME = "overpass"
LABEL = "OpenStreetMap"
ENABLED_BY_DEFAULT = True
TIER = "http"
COUNTRIES = ("GB", "PK", "US")

# One request per Search Run, with a generous server-side timeout, rather than
# several narrower queries against a shared volunteer service. The client waits
# a little longer than the server is allowed to take, so a slow answer is not
# cut off just before it arrives.
QUERY_TIMEOUT_SECONDS = 90
CLIENT_TIMEOUT_SECONDS = QUERY_TIMEOUT_SECONDS + 30


def _query(tags, market):
    """One Overpass QL query for every tag of the trade, by distance.

    Searching a radius around the market's centre rather than an administrative
    boundary by name is what makes this work outside England: Pakistani
    boundaries are named in Urdu, so a name match on "Lahore" found nothing, and
    "Newport" and "Portland" are each two places within one country.
    """
    around = f"around:{int(market['radius_km'] * 1000)},{market['lat']},{market['lon']}"
    clauses = "".join(f'nwr({around})["{key}"="{value}"];' for key, value in tags)
    return f"[out:json][timeout:{QUERY_TIMEOUT_SECONDS}];({clauses});out tags center;"


def _street_of(tags):
    number = tags.get("addr:housenumber", "").strip()
    street = tags.get("addr:street", "").strip()
    return f"{number} {street}".strip() or None


def _record(element, market):
    tags = element.get("tags") or {}
    # Prefer the English name where one is tagged: in Pakistan the plain name
    # tag is usually Urdu, which a rep writing in English cannot search for.
    name = (tags.get("name:en") or tags.get("name") or "").strip()
    if not name:
        return None

    return {
        "name": name,
        "website_url": tags.get("website") or tags.get("contact:website"),
        "phone_display": tags.get("phone") or tags.get("contact:phone"),
        "street": _street_of(tags),
        "city": tags.get("addr:city") or market["city"],
        "state": tags.get("addr:state") or market["region"],
        "country": market["country"],
        "postal_code": tags.get("addr:postcode"),
        "categories": [
            value
            for value in (
                tags.get("craft"),
                tags.get("shop"),
                tags.get("amenity"),
                tags.get("office"),
                tags.get("leisure"),
                tags.get("tourism"),
            )
            if value
        ],
        # A brand or operator tag marks a chain rather than an independent.
        "is_franchise": 1 if (tags.get("brand") or tags.get("operator")) else None,
    }


def discover(fetcher, trade_key, market, page_limit=1):
    """Businesses of a trade near a market. One request, so page_limit is unused."""
    tags = source_key(trade_key, NAME)
    if not tags:
        return

    response = fetcher.get(
        f"{overpass_url()}?{urlencode({'data': _query(tags, market)})}",
        obey_robots=False,  # A public API endpoint, not a crawlable site.
        tier=TIER,
        timeout=CLIENT_TIMEOUT_SECONDS,
    )
    body = (
        response.body.decode("utf-8", "ignore")
        if isinstance(response.body, bytes)
        else str(response.body)
    )
    for element in json.loads(body).get("elements", []):
        record = _record(element, market)
        if record:
            yield record
