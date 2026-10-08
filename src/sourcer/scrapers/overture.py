"""Overture Maps places: about 72 million businesses and places worldwide.

Overture Maps Foundation merges place data from Meta, Microsoft, Foursquare,
AllThePlaces and others into one open dataset, released monthly. For the
markets here it is the richest Source by far: in Norwich it lists 14,169 places,
87% of them with a website and a phone; it has 56 law firms where OpenStreetMap
has 16. It covers all three countries.

Each record carries its own licence, all of which allow commercial use: CDLA
Permissive 2.0 (Meta, Microsoft and others), Apache 2.0 (Foursquare) and CC0
(AllThePlaces). The footer credits Overture and Foursquare as those require.

The data is published as Parquet files on Amazon S3, not behind an API, so there
is no key, no rate limit and no volunteer server to go down. DuckDB reads only
the parts of the files whose bounding boxes fall near a market. The first search
in a market downloads every place around it and keeps them in the data
directory, so later searches there, for any trade, read from disk. Downloads run
one at a time with DuckDB held to a fixed memory budget, which keeps the app
inside a small instance's memory.

Overture rates how sure it is that each place exists, from 0 to 1. Places rated
below 0.5, which it thinks more likely gone than there, are left out.
"""

import json
import math
import re
import threading

import duckdb

from sourcer.config import data_dir
from sourcer.scrapers.catalog import source_key

NAME = "overture"
LABEL = "Overture Maps"
ENABLED_BY_DEFAULT = True
TIER = "http"
COUNTRIES = ("GB", "PK", "US")
# What it adds to a Business, as the search page shows it.
GIVES = "website and phone for most businesses"
# Said while it works, because the first search in a market is slow.
WAIT_NOTE = "The first search in a city downloads its map data, which takes about a minute."

CATALOG = "https://stac.overturemaps.org/catalog.json"
PLACES = "s3://overturemaps-us-west-2/release/{release}/theme=places/type=place/*"
PAGE_SIZE = 100
MIN_CONFIDENCE = 0.5
KM_PER_DEGREE = 111.0

# DuckDB's share of memory, and its threads. A small instance has 512 MB in all.
MEMORY_LIMIT = "256MB"
THREADS = 2

# One download at a time, through one connection. Reusing the connection keeps
# the files' metadata cached, which made later markets five times faster.
_lock = threading.Lock()
_connection = None


def _duckdb():
    global _connection
    if _connection is None:
        connection = duckdb.connect()
        connection.execute("INSTALL httpfs; LOAD httpfs; SET s3_region = 'us-west-2'")
        connection.execute(f"SET memory_limit = '{MEMORY_LIMIT}'; SET threads = {THREADS}")
        _connection = connection
    return _connection


def _latest_release(fetcher):
    """The current release. Old ones are removed after about sixty days."""
    response = fetcher.get(CATALOG, obey_robots=False, tier=TIER)
    body = response.body
    return json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)["latest"]


def _box(market):
    """The square around a market's circle, in degrees."""
    lat_span = market["radius_km"] / KM_PER_DEGREE
    lon_span = market["radius_km"] / (KM_PER_DEGREE * math.cos(math.radians(market["lat"])))
    return (
        market["lon"] - lon_span,
        market["lon"] + lon_span,
        market["lat"] - lat_span,
        market["lat"] + lat_span,
    )


def _cache_path(release, market):
    slug = re.sub(r"[^a-z0-9]+", "-", market["key"].lower()).strip("-")
    folder = data_dir() / "cache" / "overture" / release
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{slug}.parquet"


def _places(fetcher, market):
    """Every place around a market, downloaded once per release and kept."""
    release = _latest_release(fetcher)
    path = _cache_path(release, market)
    with _lock:
        if not path.exists():
            west, east, south, north = _box(market)
            partial = path.with_suffix(".partial")
            _duckdb().execute(
                f"""
                COPY (
                    SELECT id, names.primary AS name, taxonomy.hierarchy AS hierarchy,
                           taxonomy.primary AS category, websites, phones, addresses,
                           confidence, (bbox.xmin + bbox.xmax) / 2 AS lon,
                           (bbox.ymin + bbox.ymax) / 2 AS lat
                    FROM read_parquet('{PLACES.format(release=release)}')
                    WHERE bbox.xmin BETWEEN {west} AND {east}
                      AND bbox.ymin BETWEEN {south} AND {north}
                ) TO '{partial}' (FORMAT parquet)
                """
            )
            # Renamed only once complete, so a failed download is retried
            # rather than read as a market with few places.
            partial.rename(path)
    return path


def _km_between(lat1, lon1, lat2, lon2):
    """Great-circle distance, so the market is a circle like the other Sources'."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((phi2 - phi1) / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def _record(row, market):
    name, category, websites, phones, addresses = row[:5]
    address = (addresses or [{}])[0] or {}
    return {
        "name": name.strip(),
        "website_url": (websites or [None])[0],
        "phone_display": (phones or [None])[0],
        "street": address.get("freeform") or None,
        # The market's own name: Overture's locality is often a suburb, and in
        # Pakistan it is written in Urdu.
        "city": market["city"],
        "state": market["region"],
        "country": market["country"],
        "postal_code": address.get("postcode") or None,
        "categories": [f"overture:{category}"] if category else [],
    }


def discover(fetcher, trade_key, market, page_limit=1):
    """The places of a trade within the market's radius, most certain first."""
    categories = source_key(trade_key, NAME)
    if not categories:
        return

    path = _places(fetcher, market)
    wanted = "[" + ", ".join(f"'{category}'" for category in categories) + "]"
    with _lock:
        rows = (
            _duckdb()
            .execute(
                f"""
                SELECT name, category, websites, phones, addresses, lat, lon
                FROM read_parquet('{path}')
                WHERE list_has_any(hierarchy, {wanted})
                  AND confidence >= {MIN_CONFIDENCE}
                  AND name IS NOT NULL
                ORDER BY confidence DESC
                """
            )
            .fetchall()
        )

    limit = PAGE_SIZE * page_limit
    for row in rows:
        lat, lon = row[5], row[6]
        if _km_between(market["lat"], market["lon"], lat, lon) > market["radius_km"]:
            continue
        yield _record(row, market)
        limit -= 1
        if limit == 0:
            return
