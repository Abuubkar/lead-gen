"""YellowPages, through its category directory pages.

The primary Source: it carries name, phone, address, website, Reputation and
sometimes years in business, which is the single most useful Signal a Searcher
can get from a listing.

Its robots policy permits these paths, but the refusals are intermittent and
not tier-specific: during testing the HTTP client was refused for ten minutes
while a headless browser was served normally, and the reverse an hour later.
So it declares the cheap tier and relies on the fetcher to try the other one.

Paid listings are dropped: an advertisement is not a discovery, and they
duplicate the organic rows.
"""

import json
import re

from sourcer.trades import source_key

NAME = "yellowpages"
LABEL = "YellowPages"
ENABLED_BY_DEFAULT = True
TIER = "http"

BASE = "https://www.yellowpages.com"

# Ratings arrive as words in a class attribute rather than a number.
RATING_WORDS = {
    "one": 1.0,
    "two": 2.0,
    "three": 3.0,
    "four": 4.0,
    "five": 5.0,
}


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")


def category_url(trade_key, city, state, page=1):
    """A category path, which carries no query string on the first page."""
    category = source_key(trade_key, NAME)
    if not category:
        return None
    path = f"{BASE}/{_slug(city)}-{_slug(state)}/{category}"
    return path if page <= 1 else f"{path}?page={page}"


def _text(card, selector):
    node = card.css(selector)
    return node[0].get_all_text(strip=True) if node else None


def _website_of(card):
    """The real destination behind the listing's website link.

    The visible href often points back into YellowPages for click tracking, and
    the true URL sits in the analytics payload beside it.
    """
    href = card.css("a.track-visit-website::attr(href)").get()
    payload = card.css("a.track-visit-website::attr(data-analytics)").get()
    candidates = [href]
    if payload:
        try:
            candidates.append(json.loads(payload).get("dku"))
        except (ValueError, AttributeError):
            pass
    for candidate in candidates:
        if candidate and "yellowpages.com" not in candidate:
            return candidate
    return None


def _rating_of(card):
    classes = card.css(".result-rating::attr(class)").get() or ""
    words = classes.lower().split()
    value = next((RATING_WORDS[word] for word in words if word in RATING_WORDS), None)
    if value is not None and "half" in words:
        value += 0.5
    return value


def _years_of(card):
    raw = _text(card, ".years-in-business")
    match = re.search(r"(\d+)", raw or "")
    return int(match.group(1)) if match else None


def _reviews_of(card):
    raw = _text(card, ".count")
    match = re.search(r"(\d+)", raw or "")
    return int(match.group(1)) if match else None


def _is_paid(card):
    return bool(card.css(".ad-pill")) or bool(card.css(".paid-listing"))


def _record(card, city, state):
    name = card.css("a.business-name span::text").get() or _text(card, "a.business-name")
    name = (name or "").strip()
    if not name:
        return None

    address = _text(card, ".street-address") or _text(card, ".adr")
    return {
        "name": name,
        "website_url": _website_of(card),
        "phone_display": _text(card, ".phones") or _text(card, ".phone"),
        "street": address,
        "city": _text(card, ".locality") or city,
        "state": state,
        "categories": [text.strip() for text in card.css(".categories a::text").getall()],
        "years_in_business": _years_of(card),
        "public_rating": _rating_of(card),
        "public_review_count": _reviews_of(card),
    }


def discover(fetcher, trade_key, city, state, page_limit=3):
    """Organic listings across the first few category pages.

    The referer chains from the previous page, because a real visitor reaches
    page two from page one and the default Google referer on every request is a
    known tell.
    """
    previous_url = None
    for page in range(1, page_limit + 1):
        url = category_url(trade_key, city, state, page)
        if not url:
            return

        response = fetcher.get(url, referer=previous_url, tier=TIER)
        cards = [card for card in response.css(".result") if not _is_paid(card)]
        if not cards:
            return

        for card in cards:
            record = _record(card, city, state)
            if record:
                yield record
        previous_url = url
