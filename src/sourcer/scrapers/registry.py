"""Discovery Sources, each behind the same small interface.

A Source takes a Fetcher, a trade key and a place, and yields Business records.
It knows nothing about the database, the Score, or the other Sources. Adding one
is a new module and a line in the registry.

Each declares whether it is enabled by default.
"""

from sourcer.scrapers import overpass, yellowpages

# BBB is not registered because it does not work. Every request from both the
# development network and the Render host was refused at Cloudflare's edge, so
# it returned nothing in any run. Its terms also license content for personal,
# non-commercial use only, which rules out a sales team's prospect list even if
# it were reachable. The adapter is kept in bbb.py for reference; see ADR 0001.
# from sourcer.scrapers import bbb

# Order matters. The first Source to report a field wins, because merging fills
# blanks and never overwrites, so the richest reachable Source goes first.
REGISTRY = (yellowpages, overpass)

ALL_NAMES = tuple(source.NAME for source in REGISTRY)
DEFAULT_NAMES = tuple(source.NAME for source in REGISTRY if source.ENABLED_BY_DEFAULT)


def selected(names=None):
    """The Sources to run, defaulting to the ones enabled by default."""
    wanted = tuple(names) if names else DEFAULT_NAMES
    return tuple(source for source in REGISTRY if source.NAME in wanted)
