# ----- library import -----
from pathlib import Path
from typing import Dict

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Ch-Ua": '"Not A(Quantity;Brandon";v="99", "Brave";v="140", "Chromium";v="140"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Linux"',
}

_BASE_PATH = Path(__file__).resolve().parent.parent

LOG_DIR = Path("logs")
OUTPUT_DIR = Path("output")
SEARCH_OUTPUT_DIR = OUTPUT_DIR / "searches"
REVIEWS_OUTPUT_DIR = OUTPUT_DIR / "reviews"

# ----- review scraper constants -----
SESSION_DIR = str(_BASE_PATH / "amazon_user_session")
HEADLESS = False
PAGE_DELAY = 1.2
SCROLL_DELAY = 0.5
CAPTCHA_WAIT = 45

# ----- css selectors for next page button -----
NEXT_PAGE_SELECTORS = [
    "li.a-last a",
    "ul.a-pagination li.a-last a",
    "a.s-pagination-next",
    "[data-hook='show-more-button']",
]

# ----- search scraper constants -----
SEARCH_NEXT_PAGE_SELECTORS = [
    "a.s-pagination-next",
    "span.s-pagination-strip a.s-pagination-next",
    "ul.a-pagination li.a-last a",
    "li.a-last a",
    "a[aria-label='Go to next page']",
]

# ----- months map -----
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
