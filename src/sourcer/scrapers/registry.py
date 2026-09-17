"""Discovery Sources, each behind the same small interface.

A Source takes a Fetcher, a trade key and a place, and yields Business records.
It knows nothing about the database, the Score, or the other Sources. Adding one
is a new module and a line in the registry.

Each declares whether it is enabled by default. BBB is not: see ADR 0001.
"""

from sourcer.scrapers import bbb, overpass, yellowpages

# Order matters. The first Source to report a field wins, because merging fills
# blanks and never overwrites, so the richest reachable Source goes first.
REGISTRY = (yellowpages, bbb, overpass)

ALL_NAMES = tuple(source.NAME for source in REGISTRY)
DEFAULT_NAMES = tuple(source.NAME for source in REGISTRY if source.ENABLED_BY_DEFAULT)


def selected(names=None):
    """The Sources to run, defaulting to the ones enabled by default."""
    wanted = tuple(names) if names else DEFAULT_NAMES
    return tuple(source for source in REGISTRY if source.NAME in wanted)
