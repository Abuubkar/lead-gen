"""Turning messy Source records into a stable Business identity.

Every Source spells a business differently, so the dedup keys are computed here
and nowhere else. Each normaliser returns None when its input is unusable rather
than guessing, because a wrong key merges two different Businesses, which is
worse than failing to merge two records for the same one.
"""

import re
from urllib.parse import urlsplit

# Dropped before comparing names, so "Clarke Kent Plumbing LLC" and
# "Clarke Kent Plumbing, Inc." resolve to the same key.
COMPANY_SUFFIXES = {
    "llc",
    "l l c",
    "inc",
    "incorporated",
    "co",
    "company",
    "corp",
    "corporation",
    "ltd",
    "limited",
    "llp",
    "lp",
    "pllc",
    "pc",
    "plc",
    "and sons",
    "group",
}
LEADING_ARTICLES = ("the ",)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_HOSTLIKE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


def website_domain(url):
    """The bare host of a website, lowercased and without a leading "www.".

    The most stable identity a small business has: it survives a rename, a
    phone change and a move.
    """
    if not url:
        return None
    candidate = url.strip()
    if not candidate:
        return None
    # urlsplit only finds a host when there is a scheme.
    if "//" not in candidate:
        candidate = "//" + candidate
    host = (urlsplit(candidate).hostname or "").lower().strip(".")
    if not host or not _HOSTLIKE.match(host):
        return None
    if host.startswith("www."):
        host = host[4:]
    return host or None


def phone_digits(phone):
    """Exactly ten digits of a North American number, or nothing.

    Sources render the same number a dozen ways. Anything that is not a
    plausible ten-digit number is discarded rather than half-matched.
    """
    if not phone:
        return None
    digits = re.sub(r"\D", "", str(phone))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def _normalise_words(text):
    """Lowercase, strip punctuation, collapse whitespace."""
    if not text:
        return ""
    return _NON_ALNUM.sub(" ", str(text).lower()).strip()


def normalise_name(name):
    """A company name reduced to its distinctive words."""
    words = _normalise_words(name)
    for article in LEADING_ARTICLES:
        if words.startswith(article):
            words = words[len(article) :]
    parts = words.split()
    while parts and parts[-1] in COMPANY_SUFFIXES:
        parts.pop()
    return " ".join(parts)


def name_street_key(name, street):
    """The weakest of the three keys: a normalised name plus a street.

    Needs both halves. A name alone is not an identity, because a city can hold
    two unrelated businesses called Austin Plumbing.
    """
    cleaned_name = normalise_name(name)
    cleaned_street = _normalise_words(street)
    if not cleaned_name or not cleaned_street:
        return None
    return f"{cleaned_name}|{cleaned_street}"


def dedup_keys(record):
    """The three candidate keys for a record, strongest first.

    Returned whole so a caller can match an existing Business on any of them,
    not only on the one that won.
    """
    return {
        "website_domain": website_domain(record.get("website_url")),
        "phone_digits": phone_digits(record.get("phone_display")),
        "name_street_key": name_street_key(record.get("name"), record.get("street")),
    }


def resolve_dedup_key(record, keys=None):
    """Pick the identity for a record, and say which rule produced it.

    Total by construction: the dedup_key column is NOT NULL, so a Business with
    no website, no phone and no street still needs an identity. The last two
    rules exist for exactly that case, and naming the rule that won means a weak
    identity is visible rather than implied.
    """
    keys = keys if keys is not None else dedup_keys(record)
    for rule in ("website_domain", "phone_digits", "name_street_key"):
        if keys.get(rule):
            return keys[rule], rule

    name = normalise_name(record.get("name"))
    city = _normalise_words(record.get("city"))
    if name and city:
        return f"{name}|{city}", "name_city"
    if name:
        return name, "name"
    # Nothing usable at all. The caller still gets a key, but one that can only
    # ever match itself.
    return "unidentified", "none"
