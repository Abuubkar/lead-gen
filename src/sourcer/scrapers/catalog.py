"""What a Searcher picks from: the trades, and the markets.

Both are curated catalogues rather than free text. Three Sources use three
different taxonomies for a trade, so free text would mean guessing a mapping
at request time and half-working. A dozen trades that always work beat a
thousand that sometimes do, and a market that is chosen cannot be a city and
a state that do not belong together.

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


# The markets a Searcher can pick, as (city, state) pairs. Curated for the same
# reason the trades are: a pair that is chosen cannot be a pair that does not
# exist, so "Phoenix, TX" stops being reachable. Add a line to add a market.
MARKETS = (
    ("Albuquerque", "NM"),
    ("Atlanta", "GA"),
    ("Austin", "TX"),
    ("Baltimore", "MD"),
    ("Birmingham", "AL"),
    ("Boise", "ID"),
    ("Boston", "MA"),
    ("Charlotte", "NC"),
    ("Chicago", "IL"),
    ("Cincinnati", "OH"),
    ("Cleveland", "OH"),
    ("Colorado Springs", "CO"),
    ("Columbus", "OH"),
    ("Dallas", "TX"),
    ("Denver", "CO"),
    ("Des Moines", "IA"),
    ("Detroit", "MI"),
    ("El Paso", "TX"),
    ("Fort Worth", "TX"),
    ("Fresno", "CA"),
    ("Grand Rapids", "MI"),
    ("Greenville", "SC"),
    ("Houston", "TX"),
    ("Indianapolis", "IN"),
    ("Jacksonville", "FL"),
    ("Kansas City", "MO"),
    ("Knoxville", "TN"),
    ("Las Vegas", "NV"),
    ("Little Rock", "AR"),
    ("Louisville", "KY"),
    ("Memphis", "TN"),
    ("Miami", "FL"),
    ("Milwaukee", "WI"),
    ("Minneapolis", "MN"),
    ("Nashville", "TN"),
    ("New Orleans", "LA"),
    ("Oklahoma City", "OK"),
    ("Omaha", "NE"),
    ("Orlando", "FL"),
    ("Philadelphia", "PA"),
    ("Phoenix", "AZ"),
    ("Pittsburgh", "PA"),
    ("Portland", "OR"),
    ("Raleigh", "NC"),
    ("Richmond", "VA"),
    ("Sacramento", "CA"),
    ("Salt Lake City", "UT"),
    ("San Antonio", "TX"),
    ("San Diego", "CA"),
    ("Seattle", "WA"),
    ("Spokane", "WA"),
    ("St. Louis", "MO"),
    ("Tampa", "FL"),
    ("Tucson", "AZ"),
    ("Tulsa", "OK"),
    ("Wichita", "KS"),
)


def markets():
    """Every market, as (city, state), for a dropdown."""
    return list(MARKETS)


def is_market(city, state):
    """Whether a submitted market is one we cover."""
    return (city, (state or "").upper()) in MARKETS


def is_trade(key):
    """Whether a submitted trade is one the Sources can be asked for."""
    return key in TRADES


def source_key(trade_key, source):
    """How a given Source names a trade, or None if that Source has no term."""
    entry = TRADES.get(trade_key)
    return entry.get(source) if entry else None
