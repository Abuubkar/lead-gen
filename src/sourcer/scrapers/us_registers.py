"""US city and state business registers, published as open data.

Some US governments publish the businesses they license, through the Socrata
open data API, and three of them cover markets in the catalog. Each is a list
of businesses that are actually trading, filed under an industry code, which
no directory can promise:

  Seattle      Active Business License Tax Certificates (cos-data.seattle.gov,
               wnbq-64tb). Public Domain. NAICS 2022 codes, the business phone,
               ownership type, and the date the Seattle licence started.
  Texas        Active Sales Tax Permit Holders (data.texas.gov, jrea-zgmq),
               from the Comptroller. Public Domain. Every outlet in the state
               that sells taxable goods or services, with NAICS 2017 codes and
               the date of its first sale. No phone. Covers the six Texas
               markets, but only trades that collect sales tax: shops,
               restaurants, salons, landscapers, cleaners, and software.
  New Orleans  Active Occupational Licenses (data.nola.gov, iqay-p646). CC0.
               A business type in words, the phone, the owner, and the date
               the business started.

A licence or permit date is the latest a business can have started, so it is
kept as the founding year: it can make a business look younger than it is,
never older.

No key is needed. Socrata throttles anonymous callers more tightly than ones
with an app token, which this light use does not reach.
"""

import json
from urllib.parse import urlencode

from sourcer.config import CURRENT_YEAR, EARLIEST_PLAUSIBLE_YEAR
from sourcer.scrapers.catalog import source_key

NAME = "us_registers"
LABEL = "City & state registers"
ENABLED_BY_DEFAULT = True
TIER = "http"
COUNTRIES = ("US",)
# What it adds to a Business, as the search page shows it.
GIVES = "licence date, usually a phone"

HEADERS = {"Accept": "application/json"}
PAGE_SIZE = 100

TEXAS_MARKETS = ("Austin", "Dallas", "El Paso", "Fort Worth", "Houston", "San Antonio")


def _quoted(values):
    """A SoQL list of string literals, with quotes doubled as SoQL escapes them."""
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


def _year(value):
    """The year from a register's date, whichever of its formats it uses."""
    try:
        year = int(str(value)[:4])
    except (TypeError, ValueError):
        return None
    return year if EARLIEST_PLAUSIBLE_YEAR <= year <= CURRENT_YEAR else None


def _clean(value):
    value = (value or "").strip()
    return value or None


def _seattle(row, market):
    return {
        "name": _clean(row.get("trade_name")) or _clean(row.get("business_legal_name")),
        "street": _clean(row.get("street_address")),
        "city": (row.get("city") or market["city"]).title(),
        "postal_code": _clean(row.get("zip")),
        "phone_display": _clean(row.get("business_phone")),
        "founded_year": _year(row.get("license_start_date")),
        "categories": [
            entry
            for entry in (f"naics:{row.get('naics_code') or ''}", row.get("naics_description"))
            if entry and entry != "naics:"
        ],
    }


def _texas(row, market):
    return {
        "name": _clean(row.get("outlet_name")) or _clean(row.get("taxpayer_name")),
        "street": _clean(row.get("outlet_address")),
        "city": (row.get("outlet_city") or market["city"]).title(),
        "postal_code": _clean(row.get("outlet_zip_code")),
        "founded_year": _year(row.get("outlet_first_sales_date")),
        "categories": [f"naics:{row['outlet_naics_code']}"] if row.get("outlet_naics_code") else [],
    }


def _new_orleans(row, market):
    return {
        "name": _clean(row.get("businessname")),
        "street": _clean(row.get("businessaddress")),
        "city": (row.get("city") or market["city"]).title(),
        "postal_code": (_clean(row.get("zip")) or "")[:5] or None,
        "phone_display": _clean(row.get("businessphone")),
        "owner_name": _clean(row.get("ownername")),
        "founded_year": _year(row.get("businessstartdate")),
        "categories": [row["businesstype"]] if row.get("businesstype") else [],
    }


# Each register: which markets it covers, which catalog term it filters on, the
# SoQL filter, and how a row becomes a record.
REGISTERS = (
    {
        "label": "Seattle",
        "url": "https://cos-data.seattle.gov/resource/wnbq-64tb.json",
        "covers": lambda market: market["city"] == "Seattle" and market["region"] == "WA",
        "term": "naics",
        "where": lambda codes, market: (
            f"naics_code in ({_quoted(codes)}) AND upper(city) = '{market['city'].upper()}'"
        ),
        "record": _seattle,
    },
    {
        "label": "Texas",
        "url": "https://data.texas.gov/resource/jrea-zgmq.json",
        "covers": lambda market: market["region"] == "TX" and market["city"] in TEXAS_MARKETS,
        "term": "naics",
        "where": lambda codes, market: (
            f"outlet_naics_code in ({_quoted(codes)}) AND outlet_city = '{market['city'].upper()}'"
        ),
        "record": _texas,
    },
    {
        "label": "New Orleans",
        "url": "https://data.nola.gov/resource/iqay-p646.json",
        "covers": lambda market: market["city"] == "New Orleans" and market["region"] == "LA",
        "term": "nola",
        "where": lambda types, market: (
            f"businesstype in ({_quoted(types)}) AND upper(city) = '{market['city'].upper()}'"
        ),
        "record": _new_orleans,
    },
)


def registers_for(market):
    return [register for register in REGISTERS if register["covers"](market)]


def skip_reason(trade_key, market):
    registers = registers_for(market)
    if not registers:
        return "Seattle, Texas and New Orleans only"
    if not any(source_key(trade_key, register["term"]) for register in registers):
        return "not set up for this trade"
    return None


def discover(fetcher, trade_key, market, page_limit=1):
    """Licensed businesses of a trade, from whichever register covers the market."""
    for register in registers_for(market):
        terms = source_key(trade_key, register["term"])
        if not terms:
            continue
        where = register["where"](terms, market)
        for page in range(page_limit):
            query = urlencode(
                {
                    "$where": where,
                    "$order": ":id",
                    "$limit": PAGE_SIZE,
                    "$offset": page * PAGE_SIZE,
                }
            )
            response = fetcher.get(
                f"{register['url']}?{query}",
                obey_robots=False,  # A public API endpoint, not a crawlable site.
                tier=TIER,
                headers=HEADERS,
            )
            body = response.body
            rows = json.loads(body.decode("utf-8", "ignore") if isinstance(body, bytes) else body)

            for row in rows:
                record = register["record"](row, market)
                if record.get("name"):
                    record.update(state=market["region"], country="US")
                    yield record

            if len(rows) < PAGE_SIZE:
                break
