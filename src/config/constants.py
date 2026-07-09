# ----- library import -----
import re
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
HEADLESS = True
PAGE_DELAY = 1.2
SCROLL_DELAY = 0.5
CAPTCHA_WAIT = 120

# ----- pre-compiled regex patterns for performance -----
REGEX_ASIN = re.compile(
    r"/(?:dp|gp/product|product-reviews)/([A-Z0-9]{10})", re.IGNORECASE
)
REGEX_IMAGE_EXT = re.compile(r"\.[A-Za-z0-9]+$")
REGEX_IMAGE_SIZE = re.compile(
    r"\._[A-Z0-9_,.-]+_\.(?:jpg|jpeg|png|gif)$", re.IGNORECASE
)
REGEX_RATING = re.compile(r"([\d.]+)")
REGEX_NON_DIGIT = re.compile(r"[^\d]")
REGEX_TITLE_STRIP = re.compile(r"^[\d.]+\s*out\s*of\s*5\s*stars\s*", re.IGNORECASE)
REGEX_VARIANT_ROW = re.compile(r"^inline-twister-row-")
REGEX_WHITESPACE = re.compile(r"\s+")
REGEX_DELIVERY_DATE = re.compile(
    r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[,.]?\s*(\d{4})?\b",
    re.IGNORECASE,
)
REGEX_PRICE_CLEAN = re.compile(r"[^\d.]")

# ----- timeout for otp input -----
OTP_WAIT_TIMEOUT = 180

# ----- sign in attempts -----
SIGNIN_MAX_ATTEMPTS = 2

# ----- otp attempts -----
OTP_MAX_ATTEMPTS = 3

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
