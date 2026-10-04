"""Discovery Sources, each behind the same small interface.

A Source takes a Fetcher, a trade key and a market, and yields Business records.
It knows nothing about the database, the Score, or the other Sources. Adding one
is a new module and a line in the registry.

Each declares whether it is enabled by default and which countries it covers,
as ISO 3166-1 codes. A Search Run only asks the Sources that cover its country.
"""

from sourcer.scrapers import (
    companies_house,
    cqc,
    fsa,
    npi,
    overpass,
    techhub,
    us_registers,
    yellowpages,
    yellowpagespk,
)
from sourcer.scrapers.catalog import source_key

# BBB is not registered because it does not work. Every request from both the
# development network and the Render host was refused at Cloudflare's edge, so
# it returned nothing in any run. Its terms also license content for personal,
# non-commercial use only, which rules out a sales team's prospect list even if
# it were reachable. The adapter is kept in bbb.py for reference; see ADR 0001.
# from sourcer.scrapers import bbb

# Order matters. Merging fills blanks and never overwrites, so the first Source
# to report a field owns it.
#
# Companies House goes last on purpose. Its address is the registered office,
# often an accountant's, so leading with it would give a rep the accountant's
# address instead of the shop's. Last, it only fills what the others never carry:
# company number, company type, SIC codes and the date of incorporation.
#
# Within that, Sources that carry a phone or a website lead, so their contact
# details win over a register that has none.
REGISTRY = (
    yellowpages,
    npi,
    us_registers,
    cqc,
    fsa,
    techhub,
    yellowpagespk,
    overpass,
    companies_house,
)

ALL_NAMES = tuple(source.NAME for source in REGISTRY)
DEFAULT_NAMES = tuple(source.NAME for source in REGISTRY if source.ENABLED_BY_DEFAULT)


COUNTRY_NAMES = {"GB": "UK", "PK": "Pakistan", "US": "US"}


def covers(source, country):
    return country in getattr(source, "COUNTRIES", ())


def skip_reason(source, trade, market):
    """Why a Source will not search this trade in this market, or None if it will.

    The market is the one place a rep chooses where to search; a Source only
    narrows it. Three things can rule a Source out: the market's country, a
    narrower limit of its own (a register for one city, a key it needs), and a
    trade it has no term for. A Source with its own check answers the last two
    itself.
    """
    if not covers(source, market["country"]):
        countries = [COUNTRY_NAMES.get(code, code) for code in source.COUNTRIES]
        return f"{' and '.join(countries)} only"
    own = getattr(source, "skip_reason", None)
    if own is not None:
        return own(trade, market)
    if not source_key(trade, source.NAME):
        return "not set up for this trade"
    return None


def planned(trade, market):
    """Every Source, each with why it will not run here, or None if it will."""
    return [(source, skip_reason(source, trade, market)) for source in REGISTRY]


def for_country(country):
    """Every Source that can search a country, in registry order."""
    return tuple(source for source in REGISTRY if covers(source, country))


def selected(names=None, country=None):
    """The Sources to run: the named ones, or the defaults, that cover a country."""
    wanted = tuple(names) if names else DEFAULT_NAMES
    return tuple(
        source
        for source in REGISTRY
        if source.NAME in wanted and (country is None or covers(source, country))
    )
