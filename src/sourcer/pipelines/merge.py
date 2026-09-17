"""What to write when a second Source reports a Business we already have.

Policy only: given the stored row and an incoming record, decide which columns
change. No SQL and no connection, so the rules can be read, argued with and
rewritten without touching the store.

Separated from the store because it changes for a different reason. The store's
functions change when the schema does; these rules change when we learn
something about how Sources disagree, which is what step 7 is for.
"""

import json

from sourcer.pipelines.dedup import DEDUP_RULES

# Encoded JSON for an empty list or object. A column defaulting to '[]' holds no
# information, so it must count as blank or a later Source could never fill it.
EMPTY_JSON = ("[]", "{}")


def is_blank(value):
    """Whether a column holds no information yet.

    Covers the three shapes the same emptiness arrives in: a NULL, a string that
    is empty or whitespace or an encoded empty container, and a decoded empty
    list or dict.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip() or value.strip() in EMPTY_JSON
    if isinstance(value, list | dict):
        return not value
    return False


def plan_merge(existing, incoming, keys, source):
    """The columns to write, merging an incoming record into a stored Business.

    Two rules. A populated field is never overwritten, so a thin Source cannot
    degrade a rich one. Contributing Sources are unioned, because provenance has
    to survive a merge.

    A key the stored row lacks is adopted, so the next Source matching on that
    key finds this row rather than creating a second one.
    """
    updates = {
        column: value
        for column, value in incoming.items()
        if not is_blank(value) and is_blank(existing.get(column))
    }

    for column in DEDUP_RULES:
        if keys.get(column) and is_blank(existing.get(column)):
            updates[column] = keys[column]

    sources = list(existing.get("sources") or [])
    if source and source not in sources:
        updates["sources"] = json.dumps([*sources, source])

    return updates
