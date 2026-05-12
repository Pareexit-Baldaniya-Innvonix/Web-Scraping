# ----- library import -----
from enum import Enum


class ScrapeFailReason(str, Enum):
    BLOCKED = "blocked"
    NETWORK_ERROR = "network_error"
    PARSE_ERROR = "parse_error"
