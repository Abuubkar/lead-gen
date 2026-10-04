"""Marshall Yellow Pages Pakistan (yellowpagespk.com), through its WordPress API.

A free directory where Pakistani businesses list themselves, by category and
city. It is small, about 2,200 listings, most in Lahore, Karachi and Islamabad,
and since businesses write their own listings the quality varies. It is here
because it is the one general Pakistani directory found that permits this use.

The others were checked and left out on their own terms. FindPK's terms say
"You may not scrape, copy or republish the directories in bulk". BusinessList.pk
forbids access "through any automated means (including, without limitation,
through the use of scripts or webcrawlers)". The "Yellow Pages of Pakistan"
dataset on opendata.com.pk carries a public domain licence, but it is a 2020
copy of FindPK made by an individual, who could not relicense FindPK's data.

yellowpagespk.com's robots.txt disallows only its admin pages, its disclaimer
places no condition on use, and it serves its listings through the standard
WordPress REST API. A listing's phone and website live in its free text, so
they are read from there.
"""

import json
import re
from urllib.parse import urlencode, urlsplit

from scrapling import Selector

from sourcer.scrapers.catalog import source_key

NAME = "yellowpagespk"
LABEL = "Yellow Pages Pakistan"
ENABLED_BY_DEFAULT = True
TIER = "http"
COUNTRIES = ("PK",)
# Where it searches, and for what, as the search page shows it.
COVERAGE = "Pakistan"

API = "https://yellowpagespk.com/wp-json/wp/v2"
HEADERS = {"Accept": "application/json"}
PAGE_SIZE = 100

# Pakistani numbers as listings write them: mobiles (03xx), landlines with an
# area code (042, 021, 051 ...), with or without +92, dashes and spaces.
PHONE = re.compile(r"(?:\+92[\s-]?|0)(?:3\d{2}|[1-9]\d{1,2})[\s-]?\d{3}[\s-]?\d{4,5}")
# Links in a listing that are not the business's own site.
NOT_A_WEBSITE = (
    "yellowpagespk.com",
    "goo.gl",
    "google.",
    "facebook.",
    "fb.",
    "instagram.",
    "wa.me",
    "whatsapp.",
    "youtube.",
    "linkedin.",
    "twitter.",
    "x.com",
    "tiktok.",
    "pinterest.",
)


def _json(fetcher, path, params):
    response = fetcher.get(
        f"{API}/{path}?{urlencode(params, doseq=True)}",
        obey_robots=True,
        tier=TIER,
        headers=HEADERS,
    )
    body = response.body
    return json.loads(body.decode("utf-8", "ignore") if isinstance(body, bytes) else body)


def _ids(fetcher, taxonomy, slugs):
    terms = _json(fetcher, taxonomy, {"slug": list(slugs), "per_page": 100, "_fields": "id"})
    return [term["id"] for term in terms]


def _website(html):
    for anchor in Selector(html).css("a"):
        href = (anchor.attrib.get("href") or "").strip()
        host = urlsplit(href).netloc.lower()
        if href.startswith("http") and host and not any(bad in host for bad in NOT_A_WEBSITE):
            return href
    return None


def _record(listing, market):
    name = Selector(f"<p>{listing['title']['rendered']}</p>").css("p")[0].get_all_text().strip()
    if not name:
        return None
    html = (listing.get("content") or {}).get("rendered") or ""
    text = Selector(f"<div>{html}</div>").css("div")[0].get_all_text(separator=" ")
    phone = PHONE.search(text)
    return {
        "name": name,
        "city": market["city"],
        "state": market["region"],
        "country": "PK",
        "website_url": _website(html) if html else None,
        "phone_display": phone.group().strip() if phone else None,
    }


def discover(fetcher, trade_key, market, page_limit=1):
    """Self-listed businesses of a trade in the market's city."""
    slugs = source_key(trade_key, NAME)
    if not slugs:
        return
    places = _ids(fetcher, "location", [market["city"].lower().replace(" ", "-")])
    categories = _ids(fetcher, "listing-category", slugs)
    if not places or not categories:
        return

    for page in range(1, page_limit + 1):
        listings = _json(
            fetcher,
            "listing",
            {
                "location": places,
                "listing-category": categories,
                "per_page": PAGE_SIZE,
                "page": page,
                "_fields": "id,title,content,link",
            },
        )
        if not isinstance(listings, list):
            break
        for listing in listings:
            record = _record(listing, market)
            if record:
                yield record
        if len(listings) < PAGE_SIZE:
            break
