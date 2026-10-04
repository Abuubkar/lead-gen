"""PSEB's Tech Hub, the Pakistan Software Export Board's directory of IT companies.

PSEB, under the Ministry of IT and Telecommunication, runs Tech Destination as
the shop window for Pakistan's IT industry, and its Tech Hub lists the companies
registered with it: the name, the city, the head count, the years trading as
the company states them, its areas of work, and a link to its website. For the
tech mode that is the list a rep wants, and it is the only Pakistani source here
that names companies by trade rather than by map tag.

The site's robots.txt disallows nothing and it publishes no terms of use. The
listings arrive through the page's own search form, which this adapter posts to
like a browser would.

One limit shapes the adapter. The form returns only the first page of results
for a place, about twenty companies; its "load more" call drops the place
filter. So a city is asked for by name and then by each of its administrative
towns, each of which returns its own first page. The towns are those
Wikipedia lists for each city, matched to how Tech Hub spells them; a town whose
name belongs to more than one city (Iqbal Town, Gulberg Town) is left out, since
asking for it would bring in companies from the wrong one.
"""

import json
import re

from scrapling import Selector

from sourcer.config import CURRENT_YEAR
from sourcer.scrapers.catalog import source_key

NAME = "techhub"
LABEL = "PSEB Tech Hub"
ENABLED_BY_DEFAULT = True
TIER = "http"
COUNTRIES = ("PK",)
# What it adds to a Business, as the search page shows it.
GIVES = "website, staff, years trading"

ENDPOINT = "https://techdestination.com/wp-admin/admin-ajax.php"
REFERER = "https://techdestination.com/tech-hub-portal/"
HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": REFERER,
}

TOWNS = {
    "Karachi": (
        "Baldia Town",
        "Bin Qaism Town",
        "Gadap Town",
        "Gulshan Town",
        "Jamshed Town",
        "Kemari Town",
        "Korangi Town",
        "Landhi Town",
        "Liaquatabad Town",
        "Lyari Town",
        "North Nazimabad Town",
        "Orangi Town",
        "Saddar Town",
        "Shah Faisal Town",
        "Site Town",
    ),
    "Lahore": (
        "Aziz Bhatti Town",
        "Data Gunj Bukhsh Town",
        "Nishter Town",
        "Ravi Town",
        "Samanabad Town",
        "Shalamar Town",
        "Wahgah Town",
    ),
    "Faisalabad": ("Jinnah Town", "Lyallpur Town", "Madina Town"),
    "Multan": ("Bosan Town", "Mumtazabad Town", "Shah Rukn E Alam Town", "Sher Shah Town"),
    "Quetta": ("Chilton Town", "Zarghoon Town"),
}

YEARS = re.compile(r"(\d+)\s*Yrs?")


def _text(card, selector):
    found = card.css(selector)
    return re.sub(r"\s+", " ", found[0].get_all_text()).strip() if found else ""


def _number(text):
    match = re.search(r"\d+", text or "")
    return int(match.group()) if match else None


def _record(card, market):
    name = _text(card, ".name")
    if not name:
        return None
    links = [a.attrib.get("href", "") for a in card.css(".View-Profile a")]
    website = next((link for link in links if link.startswith("http")), None)
    years = YEARS.search(_text(card, ".experience"))
    years = int(years.group(1)) if years else None
    # The site's own class name, misspelt.
    items = card.css(".ecperties-overflow div")
    expertise = [re.sub(r"\s+", " ", item.get_all_text()).strip() for item in items]
    return {
        "name": name,
        "city": market["city"],
        "state": market["region"],
        "country": "PK",
        "website_url": website,
        "employee_estimate": _number(_text(card, ".staff-holder")),
        "years_in_business": years,
        "founded_year": CURRENT_YEAR - years if years else None,
        "categories": ["pseb:it", *[item for item in expertise if item]],
    }


def skip_reason(trade_key, market):
    return None if source_key(trade_key, NAME) else "IT companies only"


def discover(fetcher, trade_key, market, page_limit=1):
    """IT companies registered with PSEB in the market's city and its towns."""
    if not source_key(trade_key, NAME):
        return

    places = (market["city"], *TOWNS.get(market["city"], ()))
    for place in places:
        response = fetcher.post(
            ENDPOINT,
            data={"action": "search_company_on_change", "search": "", "locations[]": place},
            headers=HEADERS,
        )
        body = response.body
        payload = (body.decode("utf-8", "ignore") if isinstance(body, bytes) else str(body)).strip()
        if not payload.startswith("{"):
            continue
        html = json.loads(payload).get("html") or ""
        for card in Selector(html).css(".tech-api-profile"):
            record = _record(card, market)
            if record:
                yield record
