"""Better Business Bureau, through category directory pages and profiles.

The richest Source we found. A profile carries the date a business started and
the owner's name by role, which are the two facts a Searcher most wants and
which no competitor surfaces. Disabled by default anyway, for three reasons
recorded in ADR 0001: its robots policy disallows every URL with a query
string, which rules out its search endpoint and the JSON API behind it; its
terms of use license content for personal, non-commercial use and forbid
compiling a competing dataset; and it refused every request from the
development network at the edge, with no challenge to solve.

Discovery therefore goes through the category directory path, which carries no
query string, and profile pages, which the policy allows explicitly.
"""

import json
import re

from sourcer.pipelines.dedup import slug
from sourcer.scrapers.catalog import source_key
from sourcer.scrapers.client import Disallowed

NAME = "bbb"
LABEL = "Better Business Bureau"
ENABLED_BY_DEFAULT = False
TIER = "http"

BASE = "https://www.bbb.org"


def category_url(trade_key, city, state):
    """A directory path with no query string, so robots permits it."""
    category = source_key(trade_key, NAME)
    if not category:
        return None
    return f"{BASE}/us/{slug(state)}/{slug(city)}/category/{category}"


def _structured_listings(response):
    """Businesses from the page's own structured data, when it carries any."""
    for script in response.css("script[type='application/ld+json']::text").getall():
        try:
            document = json.loads(script)
        except ValueError:
            continue
        entity = (document or {}).get("mainEntity") or {}
        for item in entity.get("itemListElement") or []:
            business = item.get("item") or {}
            if business.get("name"):
                yield business


def _record(business, state):
    address = business.get("address") or {}
    phones = business.get("telephone")
    return {
        "name": business["name"].strip(),
        "phone_display": phones[0] if isinstance(phones, list) else phones,
        "street": (address.get("streetAddress") or "").strip() or None,
        "city": address.get("addressLocality"),
        "state": address.get("addressRegion") or state,
        "postal_code": address.get("postalCode"),
        # A query string on a profile URL is disallowed by robots, so it is
        # dropped rather than fetched and silently refused.
        "profile_url": _permitted(business.get("url")),
    }


def _permitted(url):
    """A profile URL robots allows, or nothing."""
    return url if url and "?" not in url else None


def _profile_links(response):
    hrefs = response.css("a::attr(href)").getall()
    seen = []
    for href in hrefs:
        if "/profile/" in (href or "") and "?" not in href:
            url = href if href.startswith("http") else f"{BASE}{href}"
            if url not in seen:
                seen.append(url)
    return seen


OWNER_ROLE = re.compile(
    r"(?:Mr\.|Mrs\.|Ms\.|Dr\.)?\s*([A-Z][\w'-]+(?:\s+[A-Z][\w'-]+){1,2}),\s*"
    r"(President|Owner|Founder|CEO|Principal|Partner|General Manager)",
)
STARTED = re.compile(r"(?:Business Started|Date Started)\s*:?\s*(\d{1,2}/\d{1,2}/(\d{4}))")
YEARS = re.compile(r"(\d+)\s+years? in business", re.IGNORECASE)


def _from_profile(response):
    """The two fields worth the extra request: when it started, and who runs it."""
    text = " ".join(response.get_all_text(separator=" ", strip=True).split())
    found = {}

    started = STARTED.search(text)
    if started:
        found["founded_year"] = int(started.group(2))
    years = YEARS.search(text)
    if years:
        found["years_in_business"] = int(years.group(1))
    owner = OWNER_ROLE.search(text)
    if owner:
        found["owner_name"] = owner.group(1).strip()
        found["owner_role"] = owner.group(2).strip()
    return found


def discover(fetcher, trade_key, city, state, page_limit=1):
    """Listings from one directory page, enriched from each profile.

    Only the first directory page is taken. Later pages need a query string,
    which robots disallows, so paginating here would mean ignoring the policy.
    """
    url = category_url(trade_key, city, state)
    if not url:
        return

    response = fetcher.get(url, tier=TIER)
    listings = list(_structured_listings(response))

    if listings:
        for business in listings:
            record = _record(business, state)
            profile_url = record.pop("profile_url", None)
            if profile_url:
                record.update(_profile_of(fetcher, profile_url))
            yield record
        return

    # No structured data: fall back to the profile links on the page.
    for profile_url in _profile_links(response)[:15]:
        record = _profile_of(fetcher, profile_url, include_name=True)
        if record.get("name"):
            record.setdefault("state", state)
            record.setdefault("city", city)
            yield record


def _profile_of(fetcher, profile_url, include_name=False):
    """Read one profile, tolerating a refusal on that single page."""
    try:
        response = fetcher.get(profile_url, referer=BASE, tier=TIER)
    except Disallowed:
        # A boundary we agreed to respect, not a failure to hide.
        raise
    except Exception:
        # One unreadable profile should not end discovery.
        return {}

    found = _from_profile(response)
    found["source_url"] = profile_url
    if include_name:
        heading = response.css("h1::text").get()
        if heading:
            found["name"] = heading.strip()
    return found
