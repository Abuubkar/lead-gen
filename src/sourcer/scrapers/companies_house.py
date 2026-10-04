"""Companies House, the UK register of companies, through its public data API.

The one Source that answers the question a UK sales team has to ask before it
emails anyone: is this a company, and of what kind. Under PECR a limited company,
plc or LLP is a corporate subscriber and can be emailed without prior consent,
while sole traders and most partnerships count as individuals and cannot. Sole
traders are not on this register at all, which is itself the answer for a
business that cannot be found here. See compliance.py.

It is also the best Source for the tech mode: SIC codes say what a company
does far more precisely than any directory category.

Free, under the Open Government Licence v3.0, and Companies House states it
imposes "no rules or requirements on how the information on the public register
is used". Reusers remain responsible for data protection law, which is why this
adapter takes company facts and not the names of directors.

Two limits worth knowing. It needs a free API key, from an account on the
Companies House developer hub, which a person has to create; without one the
Source reports itself as not configured. And the address it returns is the
registered office, which is often an accountant's rather than where the business
trades, so the location filter can miss a local business registered elsewhere.

Rate limit: 600 requests in five minutes across every endpoint.
"""

import base64
import json
from urllib.parse import urlencode

from sourcer.config import CURRENT_YEAR, companies_house_key
from sourcer.scrapers.catalog import source_key
from sourcer.scrapers.client import NotConfigured

NAME = "companies_house"
LABEL = "Companies House"
ENABLED_BY_DEFAULT = True
TIER = "http"
COUNTRIES = ("GB",)

ENDPOINT = "https://api.company-information.service.gov.uk/advanced-search/companies"
PAGE_SIZE = 100


def _auth_header(key):
    """HTTP Basic with the key as the username and an empty password.

    Companies House documents this as `curl -u my_api_key:`; the password is
    ignored and left blank.
    """
    token = base64.b64encode(f"{key}:".encode()).decode()
    return {"Authorization": f"Basic {token}", "Accept": "application/json"}


def _years_since(date_of_creation):
    """Whole years since incorporation, from an ISO date string."""
    try:
        return CURRENT_YEAR - int(str(date_of_creation)[:4])
    except (TypeError, ValueError):
        return None


def _record(item, market):
    name = (item.get("company_name") or "").strip()
    if not name:
        return None

    office = item.get("registered_office_address") or {}
    street = ", ".join(
        line for line in (office.get("address_line_1"), office.get("address_line_2")) if line
    )
    created = item.get("date_of_creation")
    return {
        "name": name,
        # The registered office, which may be an accountant's address rather
        # than where the business trades.
        "street": street or None,
        "city": office.get("locality") or market["city"],
        "state": market["region"],
        "country": market["country"],
        "postal_code": office.get("postal_code"),
        # SIC codes go into categories with a prefix, so the tech rubric can
        # tell them from directory categories.
        "categories": [f"sic:{code}" for code in item.get("sic_codes") or []],
        "company_number": item.get("company_number"),
        "company_type": item.get("company_type"),
        "founded_year": int(str(created)[:4]) if created else None,
        "years_in_business": _years_since(created),
    }


def discover(fetcher, trade_key, market, page_limit=1):
    """Active companies in a trade's SIC codes registered in a market."""
    sic_codes = source_key(trade_key, NAME)
    if not sic_codes:
        return

    key = companies_house_key()
    if not key:
        raise NotConfigured(LABEL, "set COMPANIES_HOUSE_API_KEY")

    headers = _auth_header(key)
    for page in range(page_limit):
        query = urlencode(
            {
                "sic_codes": ",".join(sic_codes),
                "location": market["city"],
                "company_status": "active",
                "size": PAGE_SIZE,
                "start_index": page * PAGE_SIZE,
            }
        )
        response = fetcher.get(
            f"{ENDPOINT}?{query}",
            obey_robots=False,  # A public API endpoint, not a crawlable site.
            tier=TIER,
            headers=headers,
        )
        body = response.body
        payload = json.loads(body.decode("utf-8", "ignore") if isinstance(body, bytes) else body)

        items = payload.get("items") or []
        for item in items:
            record = _record(item, market)
            if record:
                yield record

        if len(items) < PAGE_SIZE:
            break
