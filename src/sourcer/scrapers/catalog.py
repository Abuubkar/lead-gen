"""What a rep picks from: a mode, a trade within it, and a market.

All three are curated rather than free text, and every key below was checked
against its source rather than written from memory.

Trades are grouped by mode, because the two halves of BritNova's business look
for different things. web trades are local businesses that might need a website;
tech trades are companies that might need engineers. Each trade carries the term
each Source uses for it:

  yellowpages      a US category path. Only the trades this tool shipped with
                   have one; a guessed path just returns nothing, so newer
                   trades leave it out until one is verified.
  overpass         OpenStreetMap (key, value) tags, each checked on taginfo for
                   real use worldwide.
  companies_house  UK SIC 2007 codes, from Companies House's condensed list
                   (SIC07_CH_condensed_list_en.csv on GOV.UK).
  fsa              Food Standards Agency business type IDs, read from the live
                   BusinessTypes endpoint.
  naics            US NAICS codes, for the Seattle and Texas registers. Seattle
                   files under the 2022 edition and Texas under the 2017 one,
                   which renumbered clothing stores, software publishers and
                   web portals, so a trade lists its code from each. 2022
                   titles were read from Seattle's own naics_description
                   column; 2017 titles from the Census Bureau's code file
                   (2-6 digit_2017_Codes.xlsx).
  nola             New Orleans business types, exactly as its register spells
                   them, read from the live dataset.
  npi              NPI Registry taxonomy descriptions, checked live.
  cqc              CQC service types, from the care directory's own column.
  yellowpagespk    yellowpagespk.com listing-category slugs, from its API.
  techhub          True where PSEB's Tech Hub lists the trade. It has one list
                   of IT companies, so all three tech trades get the same one.

A Source with no term for a trade is simply skipped for it.
"""

DEFAULT_RADIUS_KM = 8.0

COUNTRY_LABELS = {"GB": "United Kingdom", "PK": "Pakistan", "US": "United States"}

TRADES = {
    # ---------------------------------------------------------------- web --
    "solicitors": {
        "mode": "web",
        "label": "Solicitors & law firms",
        "overpass": (("office", "lawyer"),),
        "companies_house": ("69102",),
        "naics": ("541110",),
        "nola": ("Offices of Lawyers",),
        "yellowpagespk": ("law-firms", "legal-service", "legal-advisor"),
    },
    "accounting": {
        "mode": "web",
        "label": "Accountants & bookkeepers",
        "yellowpages": "accountants-certified-public",
        "overpass": (("office", "accountant"),),
        "companies_house": ("69201", "69202", "69203"),
        "naics": ("541211", "541219"),
        "nola": ("Offices of Certified Public Accountants", "Accounting Services, Other"),
        "yellowpagespk": ("account-tax-consultant",),
    },
    "estate-agents": {
        "mode": "web",
        "label": "Estate agents",
        "overpass": (("office", "estate_agent"),),
        "companies_house": ("68310",),
        "naics": ("531210",),
        "nola": ("Real Estate Agents and Brokers",),
        "yellowpagespk": ("property-real-estate-agent", "real-estate"),
    },
    "architects": {
        "mode": "web",
        "label": "Architects",
        "overpass": (("office", "architect"),),
        "companies_house": ("71111",),
        "naics": ("541310",),
        "nola": ("Architectural Services",),
    },
    "insurance": {
        "mode": "web",
        "label": "Insurance brokers",
        "overpass": (("office", "insurance"),),
        "naics": ("524210",),
        "nola": ("Insurance Agencies & Brokerages",),
        "yellowpagespk": ("insurance",),
    },
    "dental": {
        "mode": "web",
        "label": "Dental practices",
        "yellowpages": "dentists",
        "overpass": (("amenity", "dentist"),),
        "companies_house": ("86230",),
        "naics": ("621210",),
        "nola": ("Offices of Dentists",),
        "npi": ("Dentist",),
        "cqc": ("Dentist",),
    },
    "medical": {
        "mode": "web",
        "label": "GP & specialist clinics",
        "overpass": (("amenity", "doctors"),),
        "companies_house": ("86210", "86220"),
        "naics": ("621111",),
        "nola": ("Offices of Physicians(except Mental Health Specialists)",),
        "npi": ("Family Medicine", "Internal Medicine"),
        "cqc": ("Doctors/GPs",),
        "yellowpagespk": ("health-medical", "specialist-medical-doctors"),
    },
    "veterinary": {
        "mode": "web",
        "label": "Veterinary clinics",
        "yellowpages": "veterinarians",
        "overpass": (("amenity", "veterinary"),),
        "companies_house": ("75000",),
        "naics": ("541940",),
        "nola": ("Veterinary Services",),
    },
    "restaurants": {
        "mode": "web",
        "label": "Restaurants & cafes",
        "overpass": (("amenity", "restaurant"), ("amenity", "cafe")),
        "companies_house": ("56101", "56102"),
        "fsa": (1,),
        "naics": ("722511", "722515"),
        "nola": (
            "Full Service Restaurants(table service available)",
            "Snack & Nonalcoholic Beverage Bars",
        ),
        "yellowpagespk": ("restaurant",),
    },
    "takeaways": {
        "mode": "web",
        "label": "Takeaways",
        "overpass": (("amenity", "fast_food"),),
        "companies_house": ("56103",),
        "fsa": (7844,),
        "naics": ("722513",),
        "nola": ("Limited Service Restaurants(no table service available)",),
    },
    "pubs": {
        "mode": "web",
        "label": "Pubs & bars",
        "overpass": (("amenity", "pub"),),
        "fsa": (7843,),
        "naics": ("722410",),
        "nola": ("Drinking Places(Alcoholic Beverages)",),
    },
    "hotels": {
        "mode": "web",
        "label": "Hotels & B&Bs",
        "overpass": (("tourism", "hotel"),),
        "companies_house": ("55100",),
        "fsa": (7842,),
        "naics": ("721110", "721191"),
        "nola": ("Hotels(except Casino Hotels) & Motels", "Bed & Breakfast Inns"),
        "yellowpagespk": ("hotels",),
    },
    "hair-beauty": {
        "mode": "web",
        "label": "Hair & beauty salons",
        "overpass": (("shop", "hairdresser"), ("shop", "beauty")),
        "companies_house": ("96020",),
        "naics": ("812112", "812111"),
        "nola": ("Beauty Salons", "Barber Shops", "Nail Salons"),
        "yellowpagespk": ("beauty-salon", "beauty-spa"),
    },
    "fitness": {
        "mode": "web",
        "label": "Gyms & fitness studios",
        "overpass": (("leisure", "fitness_centre"),),
        "companies_house": ("93130",),
        "naics": ("713940",),
        "nola": ("Fitness & Recreational Sports Centers",),
    },
    "clothing": {
        "mode": "web",
        "label": "Clothing retailers",
        "overpass": (("shop", "clothes"),),
        "companies_house": ("47710",),
        "naics": ("458110", "448110", "448120", "448140", "448150", "448190"),
        "nola": (
            "Clothing Stores, Other",
            "Women's Clothing Stores",
            "Family Clothing Stores",
            "Men's Clothing Stores",
            "Children's & Infants' Clothing Stores",
            "Clothing Accessories Stores",
        ),
        "yellowpagespk": ("fashion-styles",),
    },
    "plumbing": {
        "mode": "web",
        "label": "Plumbing",
        "yellowpages": "plumbers",
        "overpass": (("craft", "plumber"), ("shop", "plumber")),
        "companies_house": ("43220",),
        "naics": ("238220",),
        "nola": ("Plumbing, Heating and Air-Conditioning Contractors",),
    },
    "hvac": {
        "mode": "web",
        "label": "Heating & air conditioning",
        "yellowpages": "air-conditioning-contractors-systems",
        "overpass": (("craft", "hvac"), ("shop", "hvac")),
        # SIC files plumbing and air conditioning under one code.
        "companies_house": ("43220",),
        "naics": ("238220",),
        "nola": ("Plumbing, Heating and Air-Conditioning Contractors",),
    },
    "electrical": {
        "mode": "web",
        "label": "Electricians",
        "yellowpages": "electricians",
        "overpass": (("craft", "electrician"),),
        "companies_house": ("43210",),
        "naics": ("238210",),
        "nola": ("Electrical Contractors",),
    },
    "roofing": {
        "mode": "web",
        "label": "Roofing",
        "yellowpages": "roofing-contractors",
        "overpass": (("craft", "roofer"),),
        "companies_house": ("43910",),
        "naics": ("238160",),
        "nola": ("Roofing, Siding and Sheet Metal Contractors",),
    },
    "landscaping": {
        "mode": "web",
        "label": "Landscaping",
        "yellowpages": "landscaping-lawn-services",
        "overpass": (("craft", "gardener"), ("shop", "garden_centre")),
        "naics": ("561730",),
        "nola": ("Landscaping Services",),
    },
    "auto-repair": {
        "mode": "web",
        "label": "Auto repair",
        "yellowpages": "auto-repair-service",
        "overpass": (("shop", "car_repair"),),
        "naics": ("811111", "811198"),
        "nola": (
            "General Automotive Repair",
            "Automotive Repair & Maintenance, All Other",
            "Automotive Mechanical & Electrical Repair & Maintenance, Other",
        ),
        "yellowpagespk": ("automotive",),
    },
    "pest-control": {
        "mode": "web",
        "label": "Pest control",
        "yellowpages": "pest-control-services",
        "overpass": (("craft", "pest_control"),),
        "naics": ("561710",),
        "nola": ("Exterminating & Pest Control Services",),
    },
    "commercial-cleaning": {
        "mode": "web",
        "label": "Commercial cleaning",
        "yellowpages": "janitorial-service",
        "overpass": (("shop", "laundry"), ("craft", "cleaning")),
        "naics": ("561720",),
        "nola": ("Janitorial Services",),
    },
    # --------------------------------------------------------------- tech --
    # OpenStreetMap has one tag for all of these, office=it, so outside the UK
    # the three return the same businesses. Companies House tells them apart.
    "software": {
        "mode": "tech",
        "label": "Software companies",
        "overpass": (("office", "it"),),
        "companies_house": ("62011", "62012"),
        "naics": ("541511", "513210", "511210"),
        "nola": ("Custom Computer Programming Services",),
        "yellowpagespk": ("software-houses",),
        "techhub": True,
    },
    "it-services": {
        "mode": "tech",
        "label": "IT consultancies & services",
        "overpass": (("office", "it"),),
        "companies_house": ("62020", "62030", "62090"),
        "naics": ("541512", "541519"),
        "nola": ("Computer Systems Design Services", "Computer Facilities Management Services"),
        "yellowpagespk": ("software-houses", "web-development"),
        "techhub": True,
    },
    "data-hosting": {
        "mode": "tech",
        "label": "Data, hosting & web platforms",
        "overpass": (("office", "it"),),
        "companies_house": ("63110", "63120"),
        "naics": ("518210", "519290", "519130"),
        "nola": ("Data Processing Services",),
        "techhub": True,
    },
}


def choices(mode=None):
    """Key and label for every trade, optionally only one mode's, for a picker."""
    return [
        (key, entry["label"])
        for key, entry in sorted(TRADES.items(), key=lambda item: item[1]["label"])
        if mode is None or entry["mode"] == mode
    ]


def trade_mode(key):
    entry = TRADES.get(key)
    return entry["mode"] if entry else None


def is_trade(key):
    """Whether a submitted trade is one the Sources can be asked for."""
    return key in TRADES


def source_key(trade_key, source):
    """How a given Source names a trade, or None if that Source has no term."""
    entry = TRADES.get(trade_key)
    return entry.get(source) if entry else None


# Markets as (city, region, country, latitude, longitude). Generated from
# OpenStreetMap's Nominatim geocoder in a single one-off lookup during
# development and kept here, so the application never calls Nominatim itself.
#
# Searching by distance from these coordinates replaced matching administrative
# boundaries by name, which failed three ways: Pakistani boundaries are named in
# Urdu, so "Lahore" matched nothing; "Newport" is two places in Britain; and
# "Portland" two in America. Where a name was ambiguous the geocoder's first
# answer was the city meant: Newport in Wales, Islamabad Capital Territory,
# Hyderabad in Sindh. Brighton and Hove did not resolve and is left out.
#
# US regions stay two-letter state codes, because YellowPages builds its paths
# from them.
MARKETS = (
    # GB
    ("Aberdeen", "Scotland", "GB", 57.1482, -2.0928),
    ("Belfast", "Northern Ireland", "GB", 54.5964, -5.9302),
    ("Birmingham", "England", "GB", 52.4949, -1.8518),
    ("Bristol", "England", "GB", 51.4538, -2.5973),
    ("Cambridge", "England", "GB", 52.1976, 0.1392),
    ("Cardiff", "Wales", "GB", 51.4817, -3.1792),
    ("Coventry", "England", "GB", 52.4082, -1.5105),
    ("Edinburgh", "Scotland", "GB", 55.9533, -3.1884),
    ("Exeter", "England", "GB", 50.7256, -3.5269),
    ("Glasgow", "Scotland", "GB", 55.8612, -4.2502),
    ("Leeds", "England", "GB", 53.7974, -1.5438),
    ("Leicester", "England", "GB", 52.6362, -1.1332),
    ("Liverpool", "England", "GB", 53.3933, -2.9166),
    ("London", "England", "GB", 51.5074, -0.1278),
    ("Manchester", "England", "GB", 53.4425, -2.2325),
    ("Milton Keynes", "England", "GB", 52.0407, -0.7594),
    ("Newcastle upon Tyne", "England", "GB", 54.9738, -1.6132),
    ("Newport", "Wales", "GB", 51.5882, -2.9975),
    ("Norwich", "England", "GB", 52.6286, 1.2924),
    ("Nottingham", "England", "GB", 52.9534, -1.1496),
    ("Oxford", "England", "GB", 51.752, -1.2578),
    ("Plymouth", "England", "GB", 50.3714, -4.1424),
    ("Reading", "England", "GB", 51.4564, -0.9701),
    ("Sheffield", "England", "GB", 53.3807, -1.4702),
    ("Southampton", "England", "GB", 50.9025, -1.4042),
    ("York", "England", "GB", 53.9591, -1.0815),
    # PK
    ("Faisalabad", "Punjab", "PK", 31.4221, 73.0923),
    ("Gujranwala", "Punjab", "PK", 32.1525, 74.1934),
    ("Hyderabad", "Sindh", "PK", 25.4075, 68.3613),
    ("Islamabad", "Islamabad Capital Territory", "PK", 33.6938, 73.0652),
    ("Karachi", "Sindh", "PK", 24.8547, 67.0207),
    ("Lahore", "Punjab", "PK", 31.5657, 74.3142),
    ("Multan", "Punjab", "PK", 30.1978, 71.472),
    ("Peshawar", "Khyber Pakhtunkhwa", "PK", 34.0124, 71.5787),
    ("Quetta", "Balochistan", "PK", 30.1958, 67.0172),
    ("Rawalpindi", "Punjab", "PK", 33.5915, 73.0537),
    ("Sialkot", "Punjab", "PK", 32.4945, 74.5416),
    # US
    ("Albuquerque", "NM", "US", 35.0841, -106.651),
    ("Atlanta", "GA", "US", 33.7545, -84.3898),
    ("Austin", "TX", "US", 30.2711, -97.7437),
    ("Baltimore", "MD", "US", 39.2909, -76.6108),
    ("Birmingham", "AL", "US", 33.5207, -86.8024),
    ("Boise", "ID", "US", 43.6166, -116.2009),
    ("Boston", "MA", "US", 42.3588, -71.0578),
    ("Charlotte", "NC", "US", 35.2272, -80.8431),
    ("Chicago", "IL", "US", 41.8756, -87.6244),
    ("Cincinnati", "OH", "US", 39.1013, -84.5127),
    ("Cleveland", "OH", "US", 41.4997, -81.6937),
    ("Colorado Springs", "CO", "US", 38.834, -104.8253),
    ("Columbus", "OH", "US", 39.9623, -83.0007),
    ("Dallas", "TX", "US", 32.7763, -96.7969),
    ("Denver", "CO", "US", 39.7392, -104.9849),
    ("Des Moines", "IA", "US", 41.5869, -93.6249),
    ("Detroit", "MI", "US", 42.3316, -83.0466),
    ("El Paso", "TX", "US", 31.7601, -106.487),
    ("Fort Worth", "TX", "US", 32.7532, -97.3327),
    ("Fresno", "CA", "US", 36.7394, -119.7848),
    ("Grand Rapids", "MI", "US", 42.9632, -85.6679),
    ("Greenville", "SC", "US", 34.8514, -82.3985),
    ("Houston", "TX", "US", 29.7589, -95.3677),
    ("Indianapolis", "IN", "US", 39.7683, -86.1584),
    ("Jacksonville", "FL", "US", 30.3262, -81.6579),
    ("Kansas City", "MO", "US", 39.1001, -94.5781),
    ("Knoxville", "TN", "US", 35.9604, -83.921),
    ("Las Vegas", "NV", "US", 36.1674, -115.1484),
    ("Little Rock", "AR", "US", 34.7465, -92.2896),
    ("Louisville", "KY", "US", 38.2542, -85.7594),
    ("Memphis", "TN", "US", 35.146, -90.0518),
    ("Miami", "FL", "US", 25.7742, -80.1936),
    ("Milwaukee", "WI", "US", 43.0386, -87.9091),
    ("Minneapolis", "MN", "US", 44.9773, -93.2655),
    ("Nashville", "TN", "US", 36.1623, -86.7743),
    ("New Orleans", "LA", "US", 29.9575, -90.0629),
    ("Oklahoma City", "OK", "US", 35.473, -97.5171),
    ("Omaha", "NE", "US", 41.2587, -95.9384),
    ("Orlando", "FL", "US", 28.5421, -81.379),
    ("Philadelphia", "PA", "US", 39.9527, -75.1635),
    ("Phoenix", "AZ", "US", 33.4484, -112.0741),
    ("Pittsburgh", "PA", "US", 40.4407, -80.0026),
    ("Portland", "OR", "US", 45.5202, -122.6742),
    ("Raleigh", "NC", "US", 35.7804, -78.6391),
    ("Richmond", "VA", "US", 37.5385, -77.4343),
    ("Sacramento", "CA", "US", 38.5811, -121.4939),
    ("Salt Lake City", "UT", "US", 40.7596, -111.8868),
    ("San Antonio", "TX", "US", 29.4246, -98.4951),
    ("San Diego", "CA", "US", 32.7157, -117.1638),
    ("Seattle", "WA", "US", 47.6038, -122.3301),
    ("Spokane", "WA", "US", 47.6572, -117.4235),
    ("St. Louis", "MO", "US", 38.6254, -90.19),
    ("Tampa", "FL", "US", 27.945, -82.4583),
    ("Tucson", "AZ", "US", 32.2229, -110.9748),
    ("Tulsa", "OK", "US", 36.1563, -95.9928),
    ("Wichita", "KS", "US", 37.6922, -97.3375),
)


def _as_market(row):
    city, region, country, lat, lon = row
    return {
        "city": city,
        "region": region,
        "country": country,
        "lat": lat,
        "lon": lon,
        "radius_km": DEFAULT_RADIUS_KM,
        "key": f"{city}|{region}|{country}",
        "label": f"{city}, {region}",
    }


def markets(country=None):
    """Every market, optionally one country's, as dicts."""
    return [_as_market(row) for row in MARKETS if country is None or row[2] == country]


def markets_by_country():
    """Markets grouped by country, in the order the picker shows them."""
    return [(code, COUNTRY_LABELS[code], markets(code)) for code in COUNTRY_LABELS]


def find_market(key):
    """The market a picker key names, or None."""
    for row in MARKETS:
        market = _as_market(row)
        if market["key"] == key:
            return market
    return None
