from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "app.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"
MULTISPORT_DUMP_PATH = DATA_DIR / "multisport_raw_dump.json"
FACILITY_OVERRIDES_PATH = DATA_DIR / "facility_overrides.json"

# Geographic center of Poland, used as the search anchor for the Multisport
# scraper (its search UI is centered on a map viewport) at a zoom level wide
# enough that the viewport covers the whole country in one pass.
POLAND_CENTER = {"lat": 52.0, "lon": 19.2}

# Generous bounding box around Poland (min_lat, min_lon, max_lat, max_lon),
# used to drop the odd bad-data location a provider's own API hands back
# (e.g. a handful of Medicover entries with a stale/test placeholder
# coordinate, or a missing longitude silently defaulting to 0) before it
# ends up as a stray pin off in the ocean or another country.
POLAND_BBOX = (49.0, 14.0, 55.0, 24.5)

# Packages supported today. Adding a new one (e.g. FitProfit) only requires
# a new entry here plus a new scrapers/scrape_<slug>.py writing into the same
# raw_facilities table with this package's id - no other code needs to change.
PACKAGES = [
    {"slug": "medicover_sport", "display_name": "Medicover Sport"},
    {"slug": "multisport", "display_name": "Multisport"},
    {"slug": "beactive", "display_name": "BeActive"},
]

# Matching thresholds (see match.py).
#
# Name similarity is the mandatory floor (MATCH_NAME_SIMILARITY_MIN) because
# address text alone is not a reliable discriminator: many unrelated
# businesses share one street address (shopping malls, large sports
# complexes with several independent tenants), so address similarity is only
# used to lower the bar for an already-plausible name match, never to
# substitute for one entirely.
MATCH_DISTANCE_THRESHOLD_M = 100
MATCH_NAME_SIMILARITY_MIN = 55
MATCH_NAME_SIMILARITY_STRONG = 80
MATCH_ADDRESS_SIMILARITY_THRESHOLD = 70
