# ----- library import -----
from pathlib import Path
from typing import Dict

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}

_BASE_PATH = Path(__file__).resolve().parent.parent

LOG_DIR = "logs"
OUTPUT_DIR = "output"
SEARCH_OUTPUT_DIR = "output/searches"
REVIEWS_OUTPUT_DIR = "output/reviews"

# ----- review scraper constants -----
SESSION_DIR = str(_BASE_PATH / "amazon_user_session")
PAGE_DELAY = 1.2
SCROLL_DELAY = 0.5
CAPTCHA_WAIT = 3
NEXT_PAGE_SELECTORS = [
    "li.a-last a",
    "ul.a-pagination li.a-last a",
    "a:has-text('Next page')",
    "a:has-text('Next >')",
    "a:has-text('More reviews')",
    "[data-hook='show-more-button']",
]

# ----- search scraper constants -----
SEARCH_NEXT_PAGE_SELECTORS = [
    "a.s-pagination-next",
    "span.s-pagination-strip a.s-pagination-next",
    "ul.a-pagination li.a-last a",
    "li.a-last a",
    "a[aria-label='Go to next page']",
    "span.s-pagination-strip a:has-text('Next')",
    "ul.a-pagination a:has-text('Next')",
]

MONTH_MAP: Dict[str, int] = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
