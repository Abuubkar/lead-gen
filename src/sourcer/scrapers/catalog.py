"""What a Searcher picks from: the trades, and the states.

The trades are a curated catalogue rather than free text. Three Sources use
three different taxonomies, so free text would mean guessing a mapping at
request time and half-working. A dozen trades that always work beat a thousand
that sometimes do.

Chosen for what search funds actually buy: fragmented, owner-operated, local
demand, unglamorous.
"""

TRADES = {
    "plumbing": {
        "label": "Plumbing",
        "yellowpages": "plumbers",
        "bbb": "plumber",
        "overpass": (("craft", "plumber"), ("shop", "plumber")),
    },
    "hvac": {
        "label": "HVAC",
        "yellowpages": "air-conditioning-contractors-systems",
        "bbb": "air-conditioning-contractor",
        "overpass": (("craft", "hvac"), ("shop", "hvac")),
    },
    "electrical": {
        "label": "Electrical",
        "yellowpages": "electricians",
        "bbb": "electrician",
        "overpass": (("craft", "electrician"),),
    },
    "roofing": {
        "label": "Roofing",
        "yellowpages": "roofing-contractors",
        "bbb": "roofing-contractor",
        "overpass": (("craft", "roofer"),),
    },
    "landscaping": {
        "label": "Landscaping",
        "yellowpages": "landscaping-lawn-services",
        "bbb": "landscape-contractor",
        "overpass": (("craft", "gardener"), ("shop", "garden_centre")),
    },
    "auto-repair": {
        "label": "Auto repair",
        "yellowpages": "auto-repair-service",
        "bbb": "auto-repair",
        "overpass": (("shop", "car_repair"),),
    },
    "pest-control": {
        "label": "Pest control",
        "yellowpages": "pest-control-services",
        "bbb": "pest-control-services",
        "overpass": (("craft", "pest_control"),),
    },
    "commercial-cleaning": {
        "label": "Commercial cleaning",
        "yellowpages": "janitorial-service",
        "bbb": "janitorial-service",
        "overpass": (("shop", "laundry"), ("craft", "cleaning")),
    },
    "dental": {
        "label": "Dental practices",
        "yellowpages": "dentists",
        "bbb": "dentist",
        "overpass": (("amenity", "dentist"),),
    },
    "veterinary": {
        "label": "Veterinary clinics",
        "yellowpages": "veterinarians",
        "bbb": "veterinarian",
        "overpass": (("amenity", "veterinary"),),
    },
    "accounting": {
        "label": "Accounting",
        "yellowpages": "accountants-certified-public",
        "bbb": "certified-public-accountant",
        "overpass": (("office", "accountant"),),
    },
    "machine-shop": {
        "label": "Machine shops",
        "yellowpages": "machine-shops",
        "bbb": "machine-shop",
        "overpass": (("craft", "metal_construction"), ("shop", "hardware")),
    },
}


def choices():
    """Key and label for every trade, for a dropdown."""
    return [(key, entry["label"]) for key, entry in sorted(TRADES.items())]


# The fifty states and DC, as the codes that go into a Source's path. A closed
# set, unlike the city, which every Source slugs the same way and so may be
# anywhere. Codes rather than names, because the field is 96px of code, and
# sorted by code, because that is what the dropdown shows.
US_STATES = tuple(
    "AK AL AR AZ CA CO CT DC DE FL GA HI IA ID IL IN KS KY LA MA MD ME MI "
    "MN MO MS MT NC ND NE NH NJ NM NV NY OH OK OR PA RI SC SD TN TX UT VA "
    "VT WA WI WV WY".split()
)


def states():
    """Every state code, for a dropdown."""
    return list(US_STATES)


def is_state(code):
    """Whether a submitted state is one we can build a URL for."""
    return (code or "").strip().upper() in US_STATES


def is_trade(key):
    """Whether a submitted trade is one the Sources can be asked for."""
    return key in TRADES


def source_key(trade_key, source):
    """How a given Source names a trade, or None if that Source has no term."""
    entry = TRADES.get(trade_key)
    return entry.get(source) if entry else None
