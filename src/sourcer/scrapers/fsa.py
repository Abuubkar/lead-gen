"""The Food Standards Agency's food hygiene rating register, through its API.

Every food business in the UK that a local authority has inspected: restaurants,
cafes, takeaways, pubs, hotels and food retailers. It is the most complete free
list of them there is, and it is published for reuse.

The data is under the Open Government Licence v3.0. The register's terms place
no restriction on using it for marketing; their restrictions are about the
ratings themselves. Displaying an invalid or out-of-date rating "may constitute
a criminal offence", the FSA logo may not be used, and nothing may suggest the
FSA endorses a business. So this adapter does not keep the rating at all: it
says nothing about whether a business needs a website, and storing it would
only create the risk of showing a stale one.

What the register gives is a business's existence, type and location. What it
does not give is any way to contact it. The API has a Phone field, but it was
empty for all 500 Norwich businesses sampled, and there is no website or email
field. A business found only here therefore needs its contact details from
another Source, which is what merging with OpenStreetMap and reading the site
are for.

UK only. Requires no key, but does require the x-api-version header: without
it the API answers 404, "The API 'Establishments' doesn't exist".
"""

import json
from urllib.parse import urlencode

from sourcer.scrapers.catalog import source_key

NAME = "fsa"
LABEL = "Food Standards Agency"
ENABLED_BY_DEFAULT = True
TIER = "http"
COUNTRIES = ("GB",)
# Where it searches, and for what, as the search page shows it.
COVERAGE = "UK · food businesses"

ENDPOINT = "https://api.ratings.food.gov.uk/Establishments"
HEADERS = {"x-api-version": "2", "Accept": "application/json"}

PAGE_SIZE = 200
KM_PER_MILE = 1.609344


def _street_of(establishment, city):
    """The address lines that are not the town, joined.

    The register spreads an address over four lines with no fixed meaning: the
    first is as often a building name as a street, and the town tends to land
    on whichever line comes last. Dropping the line that is just the town name
    keeps the street without guessing which line holds it.
    """
    lines = [(establishment.get(f"AddressLine{index}") or "").strip() for index in range(1, 5)]
    kept = [line for line in lines if line and line.lower() != (city or "").lower()]
    return ", ".join(kept) or None


def _record(establishment, market):
    name = (establishment.get("BusinessName") or "").strip()
    if not name:
        return None
    return {
        "name": name,
        "street": _street_of(establishment, market["city"]),
        "city": market["city"],
        "state": market["region"],
        "country": market["country"],
        "postal_code": (establishment.get("PostCode") or "").strip() or None,
        "categories": [establishment.get("BusinessType")]
        if establishment.get("BusinessType")
        else [],
    }


def discover(fetcher, trade_key, market, page_limit=1):
    """Food businesses of a trade within a radius of the market's centre."""
    type_ids = source_key(trade_key, NAME)
    if not type_ids:
        return

    miles = round(market["radius_km"] / KM_PER_MILE, 1)
    for type_id in type_ids:
        for page in range(1, page_limit + 1):
            query = urlencode(
                {
                    "businessTypeId": type_id,
                    "latitude": market["lat"],
                    "longitude": market["lon"],
                    "maxDistanceLimit": miles,
                    "pageNumber": page,
                    "pageSize": PAGE_SIZE,
                }
            )
            response = fetcher.get(
                f"{ENDPOINT}?{query}",
                obey_robots=False,  # A public API endpoint, not a crawlable site.
                tier=TIER,
                headers=HEADERS,
            )
            body = response.body
            payload = json.loads(
                body.decode("utf-8", "ignore") if isinstance(body, bytes) else body
            )

            for establishment in payload.get("establishments", []):
                record = _record(establishment, market)
                if record:
                    yield record

            if page >= (payload.get("meta") or {}).get("totalPages", 1):
                break
