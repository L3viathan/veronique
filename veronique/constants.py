import re
from datetime import timedelta

# Sessions older than this get re-issued
SESSION_REFRESH_AFTER = timedelta(days=7)
# Sessions older than this are invalid
SESSION_MAX_AGE = timedelta(days=30)

# Data claims (meaning claims of internal verbs other than ROOT) are cached for
# this amount of time to speed things up a bit. In principle we should expire
# this cache whenever some action modifying the data claims of a claim is
# taken, but in case that is missed somehow, and just to make sure we only keep
# the entries this amount of time:
CLAIM_DATA_CACHE_TIME = timedelta(minutes=5)

# These params influence the Okapi BM25 algorithm (variant) used by the search
# engine:
# The avgdl is a global value (average length of all documents) that we don't
# want to compute on every search.
SEARCH_AVGDL_CACHE_TIME = timedelta(hours=1)
# This fallback should only be used if there's _nothing_ in the forward index,
# so basically never.
SEARCH_AVGDL_FALLBACK = 15  # just some semi-realistic value
# These three values can be overridden by a setting.
SEARCH_DEFAULT_K1 = 0.25
SEARCH_DEFAULT_B = 0.75
SEARCH_DEFAULT_N = 3

SECURITY_KEY_SIZE = 16
SECURITY_SALT_SIZE = 16
SECURITY_PBKDF2_HMAC_ROUNDS = 500_000

INDEX_DEFAULT_TYPE = "recent_events"
INDEX_DEFAULT_DAYS_AHEAD = 7
INDEX_DEFAULT_DAYS_BACK = 3
INDEX_DEFAULT_RECENT_EVENTS_MOD = 1

DEFAULT_PHONE_REGION = "DE"
DEFAULT_PAGE_SIZE = 20
DEFAULT_APP_NAME = "Véronique"

LOCATION_DEFAULT_LINK_TEMPLATE = "https://www.openstreetmap.org/search?query={}"
MAP_TILES_DEFAULT_ATTRIBUTION_LINK = "http://www.openstreetmap.org/copyright"
MAP_TILES_DEFAULT_ATTRIBUTION_LABEL = "OpenStreetMap"
MAP_TILES_DEFAULT_PROVIDER_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"

# There's (currently) three source types: Text, Website/URL, and Entity.
DEFAULT_SOURCE_TYPE = "T"

TEXT_REF = re.compile(r"\[@(\d+)\]")
DATE_REF = re.compile(r"[12][0-9]{3}-[01][0-9]-[0-3][0-9]")
INPUT_WIDGET_REF = re.compile(r'<span [^>]+data-claim-ref="(\d+)"[^>]+>.+?</span>')
COORDS = re.compile(r"^-?\d+(.\d+)?, ?-?\d+(.\d+)?$")
