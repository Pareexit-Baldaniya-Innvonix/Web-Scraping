# ----- library import -----
import asyncio
import csv
import json
import os
import random
import re
import time
from datetime import date as DateType
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, quote_plus, urlparse, urlunparse

from bs4 import BeautifulSoup
from playwright_stealth.stealth import Stealth
from playwright.sync_api import sync_playwright
import requests

# ----- local import -----
from src.config.constants import (
    CAPTCHA_WAIT,
    HEADLESS,
    HEADERS,
    MONTH_MAP,
    NEXT_PAGE_SELECTORS,
    OUTPUT_DIR,
    PAGE_DELAY,
    REVIEWS_OUTPUT_DIR,
    SCROLL_DELAY,
    SEARCH_NEXT_PAGE_SELECTORS,
    SEARCH_OUTPUT_DIR,
    SESSION_DIR,
)
from src.config.selectors import SELECTORS
from src.utils.logger import get_logger, setup_logging
from .Product import Product
from .Review import Review
from .ScrapeFailReason import ScrapeFailReason
from .ScrapeResult import ScrapeResult
from .Settings import settings

# ----- initialize logging configuration -----
setup_logging()
logger = get_logger("SCRAPER")

# ----- pre-compiled regex patterns for performance -----
_REGEX_ASIN = re.compile(
    r"/(?:dp|gp/product|product-reviews)/([A-Z0-9]{10})", re.IGNORECASE
)
_REGEX_IMAGE_EXT = re.compile(r"\.[A-Za-z0-9]+$")
_REGEX_IMAGE_SIZE = re.compile(
    r"\._[A-Z0-9_,.-]+_\.(?:jpg|jpeg|png|gif)$", re.IGNORECASE
)
_REGEX_RATING = re.compile(r"([\d.]+)")
_REGEX_NON_DIGIT = re.compile(r"[^\d]")
_REGEX_TITLE_STRIP = re.compile(r"^[\d.]+\s*out\s*of\s*5\s*stars\s*", re.IGNORECASE)
_REGEX_VARIANT_ROW = re.compile(r"^inline-twister-row-")
_REGEX_WHITESPACE = re.compile(r"\s+")
_REGEX_DELIVERY_DATE = re.compile(
    r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[,.]?\s*(\d{4})?\b",
    re.IGNORECASE,
)
_REGEX_PRICE_CLEAN = re.compile(r"[^\d.]")


class Scraper:
    # ----- initialization -----
    def __init__(self, url: str) -> None:
        self.url: str = Scraper.normalize_url(url)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        logger.debug("Scraper initialized for URL: %s", self.url)

    # ----- url validation & normalization -----
    @staticmethod
    def check_amazon_url(url: str) -> bool:
        logger.debug("Validating URL...")
        try:
            parsed_url = urlparse(url)
            if parsed_url.scheme not in ("http", "https"):
                logger.warning(
                    "Invalid scheme '%s' for URL: %s", parsed_url.scheme, url
                )
                return False

            domain: str = parsed_url.netloc.lower()
            if ":" in domain:
                domain = domain.split(":")[0]

            valid = domain == "amazon.in" or domain.endswith(".amazon.in")
            if not valid:
                logger.warning("Domain '%s' is not www.amazon.in", domain)
            else:
                logger.info("URL validated successfully")
            return valid

        except Exception as exc:
            logger.error("URL validation raised an exception: %s", exc, exc_info=True)
            return False

    # ----- add subdomain to the url -----
    @staticmethod
    def normalize_url(url: str) -> str:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()

        host = netloc.split(":")[0]
        port = netloc[len(host) :]

        if host == "amazon.in":
            netloc = f"www.amazon.in{port}"

        return urlunparse(parsed._replace(netloc=netloc, query=""))

    # ----- check if url/user is blocked -----
    @staticmethod
    def is_blocked(soup: BeautifulSoup) -> bool:
        page_title = soup.find("title")
        if page_title:
            t = page_title.get_text(strip=True).lower()
            if any(
                kw in t
                for kw in (
                    "robot check",
                    "something went wrong",
                    "page not found",
                    "sign in",
                    "captcha",
                )
            ):
                return True

        body_text = soup.get_text(separator=" ", strip=True).lower()
        if any(
            kw in body_text
            for kw in (
                "type the characters you see",
                "enter the characters you see",
                "sorry, we just need to make sure you're not a robot",
            )
        ):
            return True
        return False

    # ----- product asin -----
    @staticmethod
    def extract_asin(url: str) -> str:
        match = _REGEX_ASIN.search(url)
        if match:
            asin = match.group(1).upper()
            logger.debug("Extracted ASIN from path: %s", asin)
            return asin

        parsed_url = urlparse(url)
        params = parse_qs(parsed_url.query)

        if "asin" in params and params["asin"]:
            asin = params["asin"][0].upper()
            logger.debug("Extracted ASIN from query params: %s", asin)
            return asin

        logger.error("Could not extract a valid ASIN from URL: %s", url)
        raise ValueError(f"Could not extract a valid ASIN from URL: {url}")

    # ----- product title -----
    def title_details(self, soup: BeautifulSoup) -> str:
        title_tag = soup.find(*SELECTORS["title"])
        if title_tag:
            return title_tag.get_text(strip=True)
        logger.warning("Title not found")
        return "N/A"

    # ----- product price -----
    def price_details(self, soup: BeautifulSoup) -> Optional[float]:
        core_block = soup.find("div", id="corePriceDisplay_desktop_feature_div")
        search_root = core_block if core_block else soup

        price_span = search_root.find("span", {"class": "priceToPay"})
        scoped_root = price_span if price_span else search_root

        whole_tag = scoped_root.find(*SELECTORS["price_whole"])
        fraction_tag = scoped_root.find(*SELECTORS["price_fraction"])

        if not whole_tag:
            logger.warning("Price not found")
            return None

        whole = _REGEX_NON_DIGIT.sub("", whole_tag.get_text(strip=True))
        if not whole:
            return None

        fraction_text = fraction_tag.get_text(strip=True) if fraction_tag else "00"
        fraction = _REGEX_NON_DIGIT.sub("", fraction_text)
        fraction = fraction.ljust(2, "0")[:2] if fraction else "00"

        try:
            return float(f"{whole}.{fraction}")
        except ValueError:
            return None

    # ----- product image -----
    def image_details(self, soup: BeautifulSoup) -> Optional[List[str]]:
        img_urls = []

        container_tag, container_attrs = SELECTORS["images"]
        container = soup.find(container_tag, attrs=container_attrs)

        if not container:
            container = soup.find("div", id="imgTagWrapperId")

        if not container:
            logger.warning("No product images container found")
            return None

        img_elements = container.find_all("img")

        for img in img_elements:
            src = (
                img.get("data-old-hires")
                or img.get("data-a-dynamic-image")
                or img.get("src")
            )
            if not src:
                continue

            # ----- parse structural JSON maps if present -----
            if src.startswith("{"):
                try:
                    expanded_urls = json.loads(src).keys()
                except Exception:
                    expanded_urls = []
            else:
                expanded_urls = [src]

            for url in expanded_urls:
                if (
                    "images-eu" in url
                    or "_AC_UL" in url
                    or "images-amazon.com/images/G/" in url
                ):
                    continue

                if "play-button" in url.lower() or "_pk" in url.lower():
                    continue

                # ----- extract the clean, original high-res image URL -----
                match = _REGEX_IMAGE_SIZE.search(url)
                if match:
                    ext_match = _REGEX_IMAGE_EXT.search(match.group(0))
                    ext = ext_match.group(0) if ext_match else ".jpg"
                    high_res_src = _REGEX_IMAGE_SIZE.sub(ext, url)
                else:
                    high_res_src = url

                if high_res_src not in img_urls:
                    img_urls.append(high_res_src)

        if img_urls:
            logger.debug("Found %d clean image(s)", len(img_urls))
            return img_urls

        logger.warning("No main product images found")
        return None

    # ----- product ratings -----
    def ratings_details(self, soup: BeautifulSoup) -> Optional[float]:
        for selector in [SELECTORS["ratings_popover"], SELECTORS["ratings_alt"]]:
            ratings_tag = soup.find(*selector)
            if ratings_tag and ratings_tag.get_text().strip():
                match = _REGEX_RATING.search(ratings_tag.get_text().strip())
                if match:
                    return float(match.group(1))
        logger.warning("Rating not found")
        return None

    # ----- product ratings count -----
    def ratings_count(self, soup: BeautifulSoup) -> Optional[int]:
        element = soup.find(*SELECTORS["reviews_text"])
        if element:
            raw = element.get_text(strip=True).strip("()")
            cleaned = _REGEX_NON_DIGIT.sub("", raw)
            try:
                return int(cleaned)
            except ValueError:
                return None
        logger.warning("Review count not found")
        return None

    # ----- product description -----
    def description_details(self, soup: BeautifulSoup, title: str = "") -> str:
        bullets = soup.find(*SELECTORS["feature_bullets"])
        if bullets:
            items = [
                _REGEX_WHITESPACE.sub(" ", li.get_text().strip())
                for li in bullets.find_all("span", {"class": "a-list-item"})
            ]
            items = [i for i in items if i and i.lower() != "about this item"]
            if items:
                return " ".join(items)

        el = soup.find(*SELECTORS["product_description"])
        if el:
            text = " ".join(el.get_text(strip=True).split())
            if text and text.lower() != " ".join(title.split()).lower():
                return text

        logger.warning("Description not found")
        return "N/A"

    # ----- product variants -----
    def variants_details(self, soup: BeautifulSoup) -> Optional[List[Dict[str, Any]]]:
        variants = []
        json_dim_options = {}

        for tag in soup.find_all("script", {"type": "a-state"}):
            if "desktop-twister-sort-filter-data" in tag.get("data-a-state", ""):
                try:
                    dims = json.loads(tag.text).get("sortedDimValuesForAllDims", {})
                    for dim_key, values in dims.items():
                        json_dim_options[dim_key] = [
                            v.get("dimensionValueDisplayText", "").strip()
                            for v in values
                            if v.get("dimensionValueDisplayText", "").strip()
                        ]
                except Exception as exc:
                    logger.warning("Failed to parse twister a-state JSON: %s", exc)
                break

        container = soup.find(*SELECTORS["variants_container"])
        if not container:
            return variants

        rows = container.find_all("div", id=lambda x: x and _REGEX_VARIANT_ROW.match(x))
        for row in rows:
            dim_key = row.get("id", "").replace("inline-twister-row-", "")
            variant_label = dim_key.replace("_name", "").replace("_", " ").title()

            options = []
            for li in row.find_all("li"):
                raw = li.get("title", "").strip()
                if not raw:
                    img = li.find("img")
                    raw = (img.get("alt") or "").strip() if img else ""
                if not raw:
                    swatch_span = li.find(
                        "span", {"class": "swatch-title-text-display"}
                    )
                    raw = swatch_span.get_text(strip=True) if swatch_span else ""
                if not raw:
                    raw = li.get_text(strip=True)

                if (
                    raw
                    and not re.fullmatch(r"[←→‹›<>\d\s]+", raw)
                    and raw not in options
                ):
                    options.append(raw)

            if not options and dim_key in json_dim_options:
                options = json_dim_options[dim_key]

            variants.append({"type": variant_label, "options": options})
        return variants

    # ----- review text processing utilities -----
    @staticmethod
    def review_date_location(raw: str) -> Tuple[Optional[str], Optional[str]]:
        if not raw:
            return None, None
        if "Reviewed in" in raw and " on " in raw:
            parts = raw.split(" on ")
            date = parts[1].strip()
            location = parts[0].replace("Reviewed in", "").strip()
            return location, date
        return None, raw.strip()

    # ----- title of the review -----
    @staticmethod
    def review_title(raw_title: str, rating_text_to_strip: str = "") -> str:
        if rating_text_to_strip and rating_text_to_strip in raw_title:
            return raw_title.replace(rating_text_to_strip, "").strip()
        return _REGEX_TITLE_STRIP.sub("", raw_title).strip()

    # ----- product page reviews handling -----
    def reviews_details(self, soup: BeautifulSoup) -> List[Review]:
        reviews_list: List[Review] = []
        review_blocks = soup.find_all(*SELECTORS["review_container"])

        if not review_blocks:
            logger.warning("No individual product reviews found on this page")
            return reviews_list

        for index, block in enumerate(review_blocks, start=1):
            try:
                author_el = block.find(*SELECTORS["reviewer"])
                reviewer_name = (
                    author_el.get_text(strip=True) if author_el else "Anonymous"
                )

                rating_el = block.find(*SELECTORS["review_rating"])
                rating = None
                rating_str = ""
                if rating_el:
                    rating_str = rating_el.get_text(strip=True)
                    match = _REGEX_RATING.search(rating_str)
                    if match:
                        rating = float(match.group(1))

                title_el = block.find(*SELECTORS["review_title"])
                review_title_text = (
                    self.review_title(
                        title_el.get_text(separator=" ", strip=True), rating_str
                    )
                    if title_el
                    else ""
                )

                date_el = block.find(*SELECTORS["review_date"])
                review_location, review_date = self.review_date_location(
                    date_el.get_text(strip=True) if date_el else ""
                )

                body_el = block.find(*SELECTORS["review_body"])
                review_body = (
                    body_el.get_text(separator=" ", strip=True) if body_el else ""
                )

                helpful_el = block.find(*SELECTORS["review_helpful"])
                review_helpful = (
                    helpful_el.get_text(strip=True)
                    if helpful_el
                    else "0 people found this helpful"
                )

                reviews_list.append(
                    Review(
                        review_number=index,
                        reviewer_name=reviewer_name,
                        review_date=review_date,
                        review_location=review_location,
                        review_title=review_title_text,
                        rating=rating,
                        review_body=review_body,
                        review_helpful=review_helpful,
                    )
                )
            except Exception as exc:
                logger.error("Failed to parse an individual review block: %s", exc)
                continue

        return reviews_list

    # ----- storage handling for reviews -----
    @staticmethod
    def save_reviews(asin: str) -> Tuple[str, str]:
        os.makedirs(REVIEWS_OUTPUT_DIR, exist_ok=True)
        csv_path = os.path.join(REVIEWS_OUTPUT_DIR, f"reviews_{asin}.csv")
        json_path = os.path.join(REVIEWS_OUTPUT_DIR, f"reviews_{asin}.json")

        for path in (csv_path, json_path):
            if os.path.exists(path):
                os.remove(path)
                logger.debug("Removed existing file: %s", path)

        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(
                [
                    "Review Number",
                    "Reviewer Name",
                    "Review Location",
                    "Review Date",
                    "Review Title",
                    "Rating (Float)",
                    "Review Body",
                    "Helpful Votes",
                ]
            )

        with open(json_path, mode="w", encoding="utf-8") as f:
            json.dump([], f)

        logger.info("Output files created — CSV: %s | JSON: %s", csv_path, json_path)
        return csv_path, json_path

    # ----- save data into csv and json file -----
    @staticmethod
    def write_reviews_to_storage(csv_path: str, json_path: str, reviews: list) -> None:
        if not reviews:
            logger.debug("No new reviews to write; skipping storage update")
            return

        # ----- CSV append -----
        with open(csv_path, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for r in reviews:
                writer.writerow(
                    [
                        r["review_number"],
                        r["reviewer_name"],
                        r["review_location"],
                        r["review_date"],
                        r["review_title"],
                        r["rating"],
                        r["review_body"],
                        r["review_helpful"],
                    ]
                )
        logger.debug("Appended %d review(s) to CSV: %s", len(reviews), csv_path)

        # ----- JSON append -----
        try:
            if os.path.exists(json_path) and os.path.getsize(json_path) > 0:
                with open(json_path, mode="r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = []
        except (json.JSONDecodeError, FileNotFoundError):
            logger.warning(
                "JSON file corrupt or missing; starting fresh: %s", json_path
            )
            data = []

        data.extend(reviews)
        with open(json_path, mode="w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logger.debug("Updated JSON with %d review(s): %s", len(reviews), json_path)

    # ----- automation tasks of playwright browser -----
    @staticmethod
    def scroll_page(page) -> None:
        # ----- initialize height maps -----
        time.sleep(0.5)

        total_height = page.evaluate("document.body.scrollHeight")
        target_view_position = max(0, total_height - 550)
        current_position = 0

        while current_position < target_view_position:
            # ----- randomize step size -----
            distance = random.randint(150, 350)
            current_position += distance

            if current_position > target_view_position:
                current_position = target_view_position

            # ----- smooth scroll step -----
            page.evaluate(
                f"window.scrollTo({{top: {current_position}, behavior: 'smooth'}});"
            )

            # ----- delay -----
            time.sleep(random.uniform(0.1, 0.3))

            total_height = page.evaluate("document.body.scrollHeight")
            target_view_position = max(0, total_height - 550)

        # ----- final positioning exactly on the page number view -----
        page.evaluate(
            f"window.scrollTo({{top: {target_view_position}, behavior: 'smooth'}});"
        )
        time.sleep(SCROLL_DELAY)

    # ----- find next page button in reviews page -----
    @staticmethod
    def find_next_page_selector(page) -> Optional[str]:
        for selector in NEXT_PAGE_SELECTORS:
            try:
                if page.is_visible(selector, timeout=800):
                    return selector
            except Exception:
                continue
        logger.debug("No next-page selector found on current page")
        return None

    # ----- taking details of reviews from reviews page -----
    @staticmethod
    def parse_page_reviews(nodes: list, seen: set, counter: int) -> Tuple[list, int]:
        reviews = []

        for node in nodes:
            name_el = node.find(*SELECTORS["reviewer"])
            date_el = node.find(*SELECTORS["review_date"])
            title_el = node.find(*SELECTORS["review_title"]) or node.select_one(
                ".review-title"
            )
            rating_el = node.find(*SELECTORS["review_rating"]) or node.select_one(
                ".review-rating"
            )
            body_el = node.find(*SELECTORS["review_body"]) or node.select_one(
                ".review-text"
            )
            helpful_el = node.find(*SELECTORS["review_helpful"])

            reviewer_name = name_el.get_text(strip=True) if name_el else "Anonymous"
            raw_title = title_el.get_text(strip=True) if title_el else ""
            review_body = body_el.get_text(strip=True) if body_el else ""
            helpful_votes = helpful_el.get_text(strip=True) if helpful_el else "0"
            raw_meta = date_el.get_text(strip=True) if date_el else ""

            rating = None
            if rating_el:
                match = _REGEX_RATING.search(rating_el.get_text(strip=True))
                if match:
                    rating = float(match.group(1))

            review_title_text = Scraper.review_title(
                raw_title, f"{rating} out of 5 stars" if rating else ""
            )
            review_location, review_date = Scraper.review_date_location(raw_meta)

            sig = hash(f"{reviewer_name}_{review_date}_{review_title_text}_{rating}")
            if sig in seen:
                continue

            seen.add(sig)
            counter += 1
            reviews.append(
                {
                    "review_number": counter,
                    "reviewer_name": reviewer_name,
                    "review_date": review_date,
                    "review_location": review_location,
                    "rating": rating,
                    "review_title": review_title_text,
                    "review_body": review_body,
                    "review_helpful": helpful_votes,
                }
            )

        logger.debug(
            "Parsed %d new review(s) from %d node(s)", len(reviews), len(nodes)
        )
        return reviews, counter

    # ----- sign-in automation -----
    @staticmethod
    def _handle_signin(page, post_login_url: str) -> None:
        email = settings.AMAZON_EMAIL
        password = settings.AMAZON_PASSWORD

        if not email or not password:
            logger.warning("AMAZON_EMAIL or AMAZON_PASSWORD not configured.")
            return

        try:
            logger.info("Checking for Amazon login page...")

            # ----- password -----
            try:
                if page.locator("#ap_password").count() > 0:
                    logger.info("Password page detected.")

                    password_locator = page.locator("#ap_password")
                    password_locator.wait_for(state="visible", timeout=10000)

                    password_locator.fill("")
                    password_locator.fill(password)

                    time.sleep(1)

                    page.locator("#signInSubmit").click()

                    page.wait_for_load_state("domcontentloaded", timeout=30000)

                    logger.info("Password submitted successfully.")

                    if post_login_url:
                        page.goto(
                            post_login_url, wait_until="domcontentloaded", timeout=60000
                        )

                    return

            except Exception as exc:
                logger.debug("Password-only login path skipped: %s", exc)

            # ----- email -----
            email_selector = None

            try:
                page.wait_for_selector(
                    "#ap_email, #ap_email_login", state="visible", timeout=10000
                )

                if page.locator("#ap_email_login").count() > 0:
                    email_selector = "#ap_email_login"

                elif page.locator("#ap_email").count() > 0:
                    email_selector = "#ap_email"

            except Exception:
                pass

            if not email_selector:
                logger.debug("No login form detected.")
                return

            logger.info("Amazon login page detected.")

            email_locator = page.locator(email_selector)

            email_locator.wait_for(state="visible", timeout=10000)

            email_locator.fill("")
            email_locator.fill(email)

            time.sleep(1)

            if page.locator("#continue").count() > 0:
                page.locator("#continue").click()

            page.wait_for_selector("#ap_password", state="visible", timeout=15000)

            password_locator = page.locator("#ap_password")

            password_locator.fill("")
            password_locator.fill(password)

            time.sleep(1)

            page.locator("#signInSubmit").click()

            page.wait_for_load_state("domcontentloaded", timeout=30000)

            # ----- otp / captcha-----
            if any(
                key in page.url.lower()
                for key in (
                    "mfa",
                    "auth-mfa",
                    "verification",
                    "ap/cvf",
                )
            ):
                logger.warning(
                    "OTP page detected. Waiting %ds.",
                    CAPTCHA_WAIT,
                )

                time.sleep(CAPTCHA_WAIT)

            logger.info("Amazon login completed.")

            if post_login_url:
                page.goto(post_login_url, wait_until="domcontentloaded", timeout=60000)

        except Exception as exc:
            logger.error(
                "Auto-login failed: %s",
                exc,
                exc_info=True,
            )

            time.sleep(CAPTCHA_WAIT)

    @staticmethod
    def ensure_logged_in(page, target_url: str) -> bool:
        if not Scraper.is_login_page(page):
            return True

        logger.info("Login page detected. Re-authenticating...")

        Scraper._handle_signin(page, target_url)

        time.sleep(2)

        if Scraper.is_login_page(page):
            logger.error("Login failed. Still on signin page.")
            return False

        logger.info("Successfully authenticated.")

        return True

    @staticmethod
    def is_login_page(page) -> bool:
        url = page.url.lower()

        if any(
            token in url
            for token in (
                "ap/signin",
                "signin",
                "ap/login",
                "authentication",
            )
        ):
            return True

        try:
            return (
                page.locator("#ap_email").count() > 0
                or page.locator("#ap_email_login").count() > 0
                or page.locator("#ap_password").count() > 0
            )
        except Exception:
            return False

    # ----- playwright execution context for dedicated reviews loop -----
    @staticmethod
    def run_playwright_sync(url: str) -> list:
        try:
            asin = Scraper.extract_asin(url)
        except ValueError as e:
            logger.error(str(e))
            return []

        reviews_url = (
            f"https://www.amazon.in/product-reviews/{asin}?reviewerType=all_reviews"
        )

        csv_path, json_path = Scraper.save_reviews(asin)
        logger.info("Initialized output files for ASIN: %s", asin)

        asin_session_dir = os.path.join(SESSION_DIR, f"reviews_{asin.lower()}")
        os.makedirs(asin_session_dir, exist_ok=True)

        seen: set = set()
        total = 0
        page_num = 1

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                asin_session_dir,
                headless=HEADLESS,
                user_agent=HEADERS["User-Agent"],
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()

            Stealth().apply_stealth_sync(page)
            page.goto(reviews_url, wait_until="domcontentloaded", timeout=60000)

            while True:
                Scraper.ensure_logged_in(page, reviews_url)

                logger.info("Scraping reviews page %d for ASIN %s...", page_num, asin)
                content = page.content()

                if "captcha" in content.lower() or "robot" in content.lower():
                    logger.warning(
                        "CAPTCHA detected. Resume process after %ds...",
                        CAPTCHA_WAIT,
                    )
                    time.sleep(CAPTCHA_WAIT)

                if Scraper.is_login_page(page):
                    logger.warning("Amazon redirected to login page.")

                    if not Scraper.ensure_logged_in(page, reviews_url):
                        break

                Scraper.scroll_page(page)
                soup = BeautifulSoup(page.content(), "html.parser")
                nodes = soup.select("[data-hook='review']") or soup.select(".review")

                if not nodes:
                    logger.info(
                        "No review elements found on this page. Pagination complete."
                    )
                    break

                reviews, total = Scraper.parse_page_reviews(nodes, seen, total)
                Scraper.write_reviews_to_storage(csv_path, json_path, reviews)

                # ----- update the log runtime count -----
                logger.info(
                    "ASIN %s Page %d: +%d reviews (running total: %d)",
                    asin,
                    page_num,
                    len(reviews),
                    total,
                )

                # ----- stops when reviews are more than equal to THRESHOLD_LIMIT -----
                if total >= settings.THRESHOLD_LIMIT:
                    break

                next_selector = Scraper.find_next_page_selector(page)
                if not next_selector:
                    logger.info("No further pages found. Scraping complete.")
                    break

                page.locator(next_selector).scroll_into_view_if_needed()
                time.sleep(0.3)

                old_review_locator = page.locator("[data-hook='review']").first

                page.click(next_selector)

                page.wait_for_load_state("domcontentloaded", timeout=20000)
                Scraper.ensure_logged_in(page, reviews_url)

                try:
                    old_review_locator.wait_for(state="detached", timeout=5000)
                except Exception:
                    pass

                try:
                    page.wait_for_selector("[data-hook='review']", timeout=15000)
                except Exception:
                    logger.warning(
                        "Review elements not found. Checking for login page..."
                    )

                    if Scraper.is_login_page(page):
                        logger.info("Login page detected. Re-authenticating...")
                        Scraper.ensure_logged_in(page, reviews_url)

                        page.wait_for_selector("[data-hook='review']", timeout=15000)

                time.sleep(PAGE_DELAY)
                page_num += 1

            context.close()

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                final_reviews = json.load(f)
            logger.info(
                "Done. %d verified reviews verified in storage file '%s'",
                len(final_reviews),
                json_path,
            )
            return final_reviews
        except Exception as err:
            logger.error("Failed to read back final clean JSON data: %s", err)
            return []

    # ----- asynchronously scrapes product reviews by running the synchronous scraping process -----
    async def scrape_reviews_playwright(self, url: str) -> list:
        return await asyncio.to_thread(Scraper.run_playwright_sync, url)

    # ----- search results parsing utilities -----
    @staticmethod
    def _parse_delivery_days(text: str) -> Optional[int]:
        match = _REGEX_DELIVERY_DATE.search(text)
        if not match:
            return None

        day: int = int(match.group(1))
        month: int = MONTH_MAP[match.group(2).lower()]
        raw_year: Optional[str] = match.group(3)

        today = DateType.today()
        year: int = int(raw_year) if raw_year else today.year

        try:
            delivery_date = DateType(year, month, day)
        except ValueError:
            return None

        if delivery_date < today and not raw_year:
            try:
                delivery_date = DateType(today.year + 1, month, day)
            except ValueError:
                return None

        return max(0, (delivery_date - today).days)

    # ----- product delivery days -----
    @staticmethod
    def _extract_delivery_days(card: BeautifulSoup) -> Optional[int]:
        container = card.select_one("div[data-cy='delivery-recipe-container']")

        search_root = container if container else card
        for span in search_root.find_all("span"):
            text = span.get_text(separator=" ", strip=True)
            if any(
                kw in text.lower() for kw in ("delivery", "arrive", "get it", "ships")
            ):
                days = Scraper._parse_delivery_days(text)
                if days is not None:
                    return days

        for span in search_root.select("span.a-text-bold"):
            text = span.get_text(strip=True)
            days = Scraper._parse_delivery_days(text)
            if days is not None:
                return days

        return None

    # ----- search products prices -----
    @staticmethod
    def _extract_search_price(card: BeautifulSoup) -> Optional[float]:
        for sel in (
            "span.a-price:not(.a-text-strike) span.a-offscreen",
            "span[data-a-color='base'] span.a-offscreen",
        ):
            tag = card.select_one(sel)
            if tag:
                cleaned = _REGEX_PRICE_CLEAN.sub("", tag.get_text(strip=True))
                cleaned = cleaned.rstrip(".")
                try:
                    return float(cleaned) if cleaned else None
                except ValueError:
                    continue

        whole_el = card.select_one("span.a-price-whole")
        if whole_el:
            whole = _REGEX_NON_DIGIT.sub("", whole_el.get_text(strip=True))
            frac_el = card.select_one("span.a-price-fraction")
            frac = (
                _REGEX_NON_DIGIT.sub("", frac_el.get_text(strip=True))
                if frac_el
                else "00"
            )
            frac = frac.ljust(2, "0")[:2]
            try:
                return float(f"{whole}.{frac}") if whole else None
            except ValueError:
                return None

        return None

    # ----- saving data of the searched product -----
    @staticmethod
    def _parse_search_card(card: BeautifulSoup) -> Optional[Dict[str, Any]]:
        asin = card.get("data-asin", "").strip()
        if not asin:
            return None

        title: str = "N/A"
        h2_anchor = card.select_one("h2 a") or card.select_one(
            "a.a-link-normal.s-line-clamp-2"
        )
        if h2_anchor:
            title = h2_anchor.get("aria-label", "").strip()
            if not title:
                title = h2_anchor.get_text(separator=" ", strip=True)
        if title == "N/A" or not title:
            h2_tag = card.select_one("h2")
            if h2_tag:
                title = h2_tag.get_text(separator=" ", strip=True) or "N/A"

        price: Optional[float] = Scraper._extract_search_price(card)
        link: str = f"https://www.amazon.in/dp/{asin}/"
        delivery_duration_days: Optional[int] = Scraper._extract_delivery_days(card)

        return {
            "title": title,
            "price": price,
            "link": link,
            "delivery_duration_days": delivery_duration_days,
        }

    # ----- search workflows and storage persistence -----
    @staticmethod
    def _build_search_output_path(query: str) -> str:
        os.makedirs(SEARCH_OUTPUT_DIR, exist_ok=True)
        safe_query = re.sub(r"[^\w\-_]", "_", query.strip().lower())
        filename = f"search_{safe_query}.json"
        return os.path.join(SEARCH_OUTPUT_DIR, filename)

    # ----- next button for next page -----
    @staticmethod
    def _find_search_next_page(page) -> Optional[str]:
        for selector in SEARCH_NEXT_PAGE_SELECTORS:
            try:
                locator = page.locator(selector).first
                if locator.is_visible(timeout=800):
                    return selector
            except Exception:
                continue
        logger.debug("No next-page selector found on current search page")
        return None

    # ----- save data into temp file before saving it in actual file  -----
    @staticmethod
    def _persist_search_progress(
        all_products: List[Dict[str, Any]], output_path: str, page_num: int
    ) -> None:
        temp_path = f"{output_path}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as fh:
                json.dump(
                    {"total_products": len(all_products), "products": all_products},
                    fh,
                    indent=4,
                    ensure_ascii=False,
                )
            os.replace(temp_path, output_path)
        except Exception as exc:
            logger.error(
                "Failed to persist search progress after page %d: %s",
                page_num,
                exc,
                exc_info=True,
            )

    # ----- playwright execution context for dedicated search query loop -----
    @staticmethod
    def _run_search_playwright_sync(
        query: str, base_url: str, output_path: str
    ) -> List[Dict[str, Any]]:
        search_url = f"{base_url}/s?k={quote_plus(query)}"
        all_products: List[Dict[str, Any]] = []
        seen_asins: set = set()
        page_num = 1

        safe_slug = re.sub(r"[^\w]", "_", query.strip().lower())[:24]
        session_dir = os.path.join(SESSION_DIR, f"search_{safe_slug}")
        os.makedirs(session_dir, exist_ok=True)

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                session_dir,
                headless=HEADLESS,
                user_agent=HEADERS["User-Agent"],
                viewport={"width": 1280, "height": 800},
            )
            try:
                page = context.new_page()
                Stealth().apply_stealth_sync(page)

                logger.debug("Navigating to search URL: %s", search_url)
                page.goto(search_url, wait_until="domcontentloaded", timeout=60000)

                while True:
                    Scraper.ensure_logged_in(page, search_url)

                    logger.info("[Product: %s] scraping page %d...", query, page_num)

                    try:
                        content = page.content()
                        if "captcha" in content.lower() or "robot" in content.lower():
                            time.sleep(CAPTCHA_WAIT)

                        Scraper.scroll_page(page)
                        soup = BeautifulSoup(page.content(), "html.parser")

                        cards = soup.select(
                            "div[data-component-type='s-search-result'][data-asin]"
                        )
                        if not cards:
                            cards = soup.select("div.s-result-item[data-asin]")

                        for card in cards:
                            try:
                                asin = card.get("data-asin", "").strip()
                                if not asin or asin in seen_asins:
                                    continue
                                product = Scraper._parse_search_card(card)
                                if product:
                                    seen_asins.add(asin)
                                    all_products.append(product)
                            except Exception as exc:
                                logger.warning(
                                    "Failed to parse a card on page %d: %s",
                                    page_num,
                                    exc,
                                )
                                continue

                    except Exception as exc:
                        logger.error(
                            "Error while scraping page %d: %s",
                            page_num,
                            exc,
                            exc_info=True,
                        )

                    Scraper._persist_search_progress(
                        all_products, output_path, page_num
                    )

                    # ----- stops when reviews are more than equal to THRESHOLD_LIMIT -----
                    if len(all_products) >= settings.THRESHOLD_LIMIT:
                        break

                    try:
                        next_selector = Scraper._find_search_next_page(page)
                    except Exception as exc:
                        logger.error(
                            "Failed to locate next-page control on page %d: %s",
                            page_num,
                            exc,
                        )
                        next_selector = None

                    if not next_selector:
                        logger.debug(
                            "No further pages detected — stopping after page %d",
                            page_num,
                        )
                        break

                    try:
                        next_locator = page.locator(next_selector).first
                        next_locator.scroll_into_view_if_needed()
                        time.sleep(0.3)
                        next_locator.click()
                        try:
                            page.wait_for_load_state("domcontentloaded", timeout=30000)
                        except Exception:
                            logger.debug(
                                "domcontentloaded timed out on page %d",
                                page_num + 1,
                            )

                        # ----- redirect to signin page -----
                        Scraper.ensure_logged_in(page, search_url)

                        _CARD_SELECTOR = (
                            "div[data-component-type='s-search-result'][data-asin],"
                            "div.s-result-item[data-asin]"
                        )
                        try:
                            page.wait_for_selector(
                                _CARD_SELECTOR, state="attached", timeout=15000
                            )
                        except Exception:
                            logger.warning(
                                "No result cards found on page %d within timeout — "
                                "page may be empty or blocked",
                                page_num + 1,
                            )
                        time.sleep(PAGE_DELAY)
                        page_num += 1
                    except Exception as exc:
                        logger.error(
                            "Failed to navigate to page %d: %s",
                            page_num + 1,
                            exc,
                            exc_info=True,
                        )
                        break

            finally:
                Scraper._persist_search_progress(all_products, output_path, page_num)
                context.close()

        logger.debug(
            "Search scrape complete — %d unique products across %d page(s)",
            len(all_products),
            page_num,
        )
        return all_products

    # ----- save data to actual directory path -----
    async def scrape_search_playwright(self, query: str) -> List[Dict[str, Any]]:
        output_path = Scraper._build_search_output_path(query)
        products: List[Dict[str, Any]] = await asyncio.to_thread(
            Scraper._run_search_playwright_sync, query, self.url, output_path
        )
        return products

    # ----- synchronous single product scraping context -----
    def scraping_data(self) -> ScrapeResult:
        logger.info("Scraping started.")
        try:
            response = self.session.get(self.url, timeout=15)
            if response.status_code == 404:
                return ScrapeResult(
                    success=False,
                    reason=ScrapeFailReason.PARSE_ERROR,
                    detail="Product not found (404).",
                )

            response.raise_for_status()
            self.save_raw_response(response.text)

        except requests.RequestException as error:
            logger.error("Request error: %s", error, exc_info=True)
            return ScrapeResult(
                success=False,
                reason=ScrapeFailReason.NETWORK_ERROR,
                detail=f"Network error while fetching URL: {error}",
            )

        soup = BeautifulSoup(response.content, "html.parser")

        if Scraper.is_blocked(soup):
            logger.warning("Blocked by Amazon (CAPTCHA or redirect)")
            return ScrapeResult(
                success=False,
                reason=ScrapeFailReason.BLOCKED,
                detail="Amazon blocked the request. Try again later.",
            )

        try:
            title = self.title_details(soup)
            reviews = self.reviews_details(soup)

            product = Product(
                title=title,
                image=self.image_details(soup),
                price=self.price_details(soup),
                ratings=self.ratings_details(soup),
                ratings_count=self.ratings_count(soup),
                description=self.description_details(soup, title),
                variants=self.variants_details(soup),
                reviews=reviews,
            )

            logger.info(
                "Product extracted: Title: '%s' | Price: %s | Ratings: %s | Ratings_count: %s | Reviews_count: %d",
                product.title,
                product.price,
                product.ratings if product.ratings else 0,
                product.ratings_count if product.ratings_count else 0,
                len(product.reviews) if product.reviews else 0,
            )
            return ScrapeResult(success=True, product=product)

        except Exception as exc:
            logger.error("Extraction failed: %s", exc, exc_info=True)
            return ScrapeResult(
                success=False,
                reason=ScrapeFailReason.PARSE_ERROR,
                detail=f"Failed to parse product data: {exc}",
            )

    # ----- taking html file of the product page -----
    def save_raw_response(self, html_content: str) -> None:
        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            file_path: str = os.path.join(OUTPUT_DIR, "source.html")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            logger.info("Raw HTML of the url saved successfully!")
        except OSError as e:
            logger.error("Failed to save HTML source: %s", e)

    # ----- data display formatting output -----
    @staticmethod
    def print_data(product: Product) -> None:
        print(json.dumps(product.to_dict(), ensure_ascii=False, indent=4))
