"""The NPI Registry, the US federal list of health care providers, through its API.

Every dental practice and clinic that bills a US health plan needs a National
Provider Identifier, so the registry lists nearly all of them, with the practice
address and phone, and for an organisation the name and title of the person
authorised to act for it, usually the owner.

CMS publishes it because the data is disclosable under the Freedom of
Information Act, as set out in its NPPES Data Dissemination notice (72 FR 30011).
The API page states no condition on use. It needs no key.

Only organisations are asked for (NPI-2), not individual practitioners: a rep
sells a website to a practice, not to each dentist in it. The enumeration date
is not kept as a founding date, because NPIs only began in 2007 and a practice
older than that would look new.

One API call returns at most 200 results and can skip at most 1,000, so a
market yields up to 1,200 per taxonomy.
"""

import json
from urllib.parse import urlencode

from sourcer.scrapers.catalog import source_key

NAME = "npi"
LABEL = "NPI Registry"
ENABLED_BY_DEFAULT = True
TIER = "http"
COUNTRIES = ("US",)
# What it adds to a Business, as the search page shows it.
GIVES = "phone, the owner or practice official"

ENDPOINT = "https://npiregistry.cms.hhs.gov/api/"
HEADERS = {"Accept": "application/json"}
PAGE_SIZE = 200


def _location(result):
    """The practice address; the registry also returns a mailing one."""
    for address in result.get("addresses") or []:
        if address.get("address_purpose") == "LOCATION":
            return address
    return {}


def _trading_name(result):
    """The name on the door: a doing-business-as name if one is filed."""
    for other in result.get("other_names") or []:
        if other.get("type") == "Doing Business As" and other.get("organization_name"):
            return other["organization_name"]
    return (result.get("basic") or {}).get("organization_name")


def _official(basic):
    first = (basic.get("authorized_official_first_name") or "").strip()
    last = (basic.get("authorized_official_last_name") or "").strip()
    name = f"{first} {last}".strip()
    return name.title() if name else None


def _matches(result, wanted):
    """Whether a provider really is in the trade.

    The API matches a taxonomy description loosely, so a search for "Dentist"
    also returns a chiropractor with a dental taxonomy somewhere in its list.
    The primary taxonomy has to start with the term asked for.
    """
    for taxonomy in result.get("taxonomies") or []:
        if taxonomy.get("primary"):
            return (taxonomy.get("desc") or "").startswith(wanted)
    return False


def _record(result, market):
    name = _trading_name(result)
    location = _location(result)
    if not name or not location:
        return None
    basic = result.get("basic") or {}
    postal = (location.get("postal_code") or "").strip()
    return {
        "name": name.strip(),
        "street": (location.get("address_1") or "").strip() or None,
        "city": (location.get("city") or "").title() or market["city"],
        "state": location.get("state") or market["region"],
        "country": "US",
        "postal_code": postal[:5] or None,
        "phone_display": location.get("telephone_number") or None,
        "owner_name": _official(basic),
        "categories": [t.get("desc") for t in result.get("taxonomies") or [] if t.get("desc")],
    }


def skip_reason(trade_key, market):
    return None if source_key(trade_key, NAME) else "dentists and clinics only"


def discover(fetcher, trade_key, market, page_limit=1):
    """Practices of a trade whose practice address is in the market's city."""
    terms = source_key(trade_key, NAME)
    if not terms:
        return

    for term in terms:
        for page in range(page_limit):
            query = urlencode(
                {
                    "version": "2.1",
                    "enumeration_type": "NPI-2",
                    "taxonomy_description": term,
                    "address_purpose": "LOCATION",
                    "city": market["city"],
                    "state": market["region"],
                    "limit": PAGE_SIZE,
                    "skip": page * PAGE_SIZE,
                }
            )
            response = fetcher.get(
                f"{ENDPOINT}?{query}",
                obey_robots=False,  # A public API endpoint, not a crawlable site.
                tier=TIER,
                headers=HEADERS,
            )
            body = response.body
            text = body.decode("utf-8", "ignore") if isinstance(body, bytes) else body
            payload = json.loads(text)
            results = payload.get("results") or []

            for result in results:
                if not _matches(result, term):
                    continue
                record = _record(result, market)
                if record:
                    yield record

            if len(results) < PAGE_SIZE or (page + 1) * PAGE_SIZE > 1000:
                break
