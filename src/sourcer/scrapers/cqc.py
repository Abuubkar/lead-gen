"""The Care Quality Commission's care directory: every regulated service in England.

Every dentist and GP practice in England has to register with the CQC, and the
CQC publishes the full list as a CSV each week, with the phone number and, where
the practice gave one, its website. That makes it the one UK register here that
says how to reach a business.

Published under the Open Government Licence v3.0. The CQC asks that anyone using
its data acknowledge it, which the page footer does.

The CQC also has an API, but it now requires a subscription key; the directory
file needs none and holds the same practices. The file is about 18 MB and its
name changes each week, so the adapter reads the CQC's data page for the
current link, downloads it at most once a week, and keeps it in the data
directory.

England only: Wales, Scotland and Northern Ireland have their own regulators.
The file has no coordinates, so a practice is placed by the town at the end of
its address, which is its postal town.
"""

import csv
import io
import re
import time

from sourcer.config import data_dir
from sourcer.scrapers.catalog import source_key

NAME = "cqc"
LABEL = "Care Quality Commission"
ENABLED_BY_DEFAULT = True
TIER = "http"
COUNTRIES = ("GB",)
# What it adds to a Business, as the search page shows it.
GIVES = "phone, website for about half"

DATA_PAGE = "https://www.cqc.org.uk/about-us/transparency/using-cqc-data"
DIRECTORY_LINK = re.compile(
    r'href="(https://www\.cqc\.org\.uk/system/files/[^"]+_CQC_directory\.csv)"'
)
REFRESH_SECONDS = 7 * 24 * 3600
DOWNLOAD_TIMEOUT_SECONDS = 180

# The file opens with four lines of preamble before the header row.
PREAMBLE_LINES = 4
WEBSITE_COLUMN = "Service's website (if available)"


def _cache_path():
    folder = data_dir() / "cache"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "cqc_directory.csv"


def _text(response):
    body = response.body
    return body.decode("utf-8-sig", "ignore") if isinstance(body, bytes) else str(body)


def _directory(fetcher):
    """This week's directory, from the cache or freshly downloaded."""
    path = _cache_path()
    if path.exists() and time.time() - path.stat().st_mtime < REFRESH_SECONDS:
        return path.read_text(encoding="utf-8")

    page = _text(fetcher.get(DATA_PAGE, tier=TIER))
    match = DIRECTORY_LINK.search(page)
    if not match:
        raise ValueError("no directory link on the CQC data page")
    text = _text(fetcher.get(match.group(1), tier=TIER, timeout=DOWNLOAD_TIMEOUT_SECONDS))
    path.write_text(text, encoding="utf-8")
    return text


def _town(address):
    parts = [part.strip() for part in (address or "").split(",") if part.strip()]
    return parts[-1] if parts else ""


def _street(address):
    parts = [part.strip() for part in (address or "").split(",") if part.strip()]
    return ", ".join(parts[:-1]) or None


def _phone(number):
    """UK numbers lose their leading zero in the file; put it back."""
    digits = re.sub(r"\D", "", number or "")
    if not digits:
        return None
    return digits if digits.startswith("0") else f"0{digits}"


def _record(row, market):
    return {
        "name": row["Name"].strip(),
        "street": _street(row.get("Address")),
        "city": market["city"],
        "state": market["region"],
        "country": "GB",
        "postal_code": (row.get("Postcode") or "").strip() or None,
        "phone_display": _phone(row.get("Phone number")),
        "website_url": (row.get(WEBSITE_COLUMN) or "").strip() or None,
        "categories": [t.strip() for t in (row.get("Service types") or "").split("|") if t.strip()],
    }


def skip_reason(trade_key, market):
    if market["region"] != "England":
        return "England only"
    if not source_key(trade_key, NAME):
        return "dentists and GPs only"
    return None


def discover(fetcher, trade_key, market, page_limit=1):
    """Registered practices of a trade whose postal town is the market's city."""
    service_types = source_key(trade_key, NAME)
    if not service_types or market["region"] != "England":
        return

    lines = _directory(fetcher).splitlines()[PREAMBLE_LINES:]
    city = market["city"].lower()
    for row in csv.DictReader(io.StringIO("\n".join(lines))):
        if _town(row.get("Address")).lower() != city:
            continue
        offered = {t.strip() for t in (row.get("Service types") or "").split("|")}
        if offered.intersection(service_types) and row.get("Name"):
            yield _record(row, market)
