# ----- library import -----
import asyncio
import csv
import json
import os
import random
import re
from datetime import date as DateType
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import parse_qs, quote_plus, urlparse, urlunparse

from bs4 import BeautifulSoup
from playwright_stealth.stealth import Stealth
from playwright.async_api import async_playwright
from playwright.async_api import Error as PlaywrightError
import requests

# ----- local import -----
from src.config.constants import (
    CAPTCHA_WAIT,
    HEADERS,
    MONTH_MAP,
    NEXT_PAGE_SELECTORS,
    OTP_MAX_ATTEMPTS,
    OTP_WAIT_TIMEOUT,
    OUTPUT_DIR,
    PAGE_DELAY,
    REVIEWS_OUTPUT_DIR,
    SCROLL_DELAY,
    SEARCH_NEXT_PAGE_SELECTORS,
    SEARCH_OUTPUT_DIR,
    SESSION_DIR,
    SIGNIN_MAX_ATTEMPTS,
)
from src.config.selectors import (
    OTP_INPUT_FALLBACKS,
    OTP_SEND_BUTTON_FALLBACKS,
    OTP_SUBMIT_FALLBACKS,
    SELECTORS,
)
from src.utils.logger import get_logger
from .Product import Product
from .Review import Review
from .BrowserManager import BrowserManager
from .OtpManager import OtpManager
from .ScrapeFailReason import ScrapeFailReason
from .ScrapeResult import ScrapeResult
from .Settings import settings

# ----- initialize logging configuration -----
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
        logger.debug("Scraper initialized for URL: %s", self.url)

    # ----- create a fresh requests session with randomized headers -----
    @staticmethod
    def _new_session() -> requests.Session:
        session = requests.Session()
        headers = dict(HEADERS)
        session.headers.update(headers)
        return session

    # ----- url validation & normalization -----
    @staticmethod
    def check_amazon_url(url: str) -> bool:
        logger.debug("Validating target Amazon URL: %s", url)
        try:
            parsed_url = urlparse(url)
            if parsed_url.scheme not in ("http", "https"):
                logger.warning("Invalid URL scheme '%s' for URL: %s", parsed_url.scheme, url)
                return False

            domain: str = parsed_url.netloc.lower()
            if ":" in domain:
                domain = domain.split(":")[0]

            valid = domain == "amazon.in" or domain.endswith(".amazon.in")
            if not valid:
                logger.warning("Domain verification failed: '%s' is not an allowed Amazon India domain", domain)
            else:
                logger.info("Amazon URL validation completed successfully")
            return valid

        except Exception as exc:
            logger.error("URL validation failed: %s", exc, exc_info=True)
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
            return asin

        parsed_url = urlparse(url)
        params = parse_qs(parsed_url.query)

        if "asin" in params and params["asin"]:
            asin = params["asin"][0].upper()
            logger.debug("Extracted ASIN from query parameters: %s", asin)
            return asin

        logger.error("Failed to extract ASIN from URL: %s", url)
        raise ValueError(f"Could not extract a valid ASIN from URL: {url}")

    # ----- product title -----
    def title_details(self, soup: BeautifulSoup) -> str:
        title_tag = soup.find(*SELECTORS["title"])
        if title_tag:
            return title_tag.get_text(strip=True)
        logger.warning("Product title element not found in DOM")
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
            logger.warning("Product price element not found in DOM")
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
            logger.warning("Product images container not found in DOM")
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
            logger.debug("Successfully parsed %d high-res image URLs", len(img_urls))
            return img_urls

        logger.warning("No product image URLs were extracted")
        return None

    # ----- product ratings -----
    def ratings_details(self, soup: BeautifulSoup) -> Optional[float]:
        for selector in [SELECTORS["ratings_popover"], SELECTORS["ratings_alt"]]:
            ratings_tag = soup.find(*selector)
            if ratings_tag and ratings_tag.get_text().strip():
                match = _REGEX_RATING.search(ratings_tag.get_text().strip())
                if match:
                    return float(match.group(1))
        logger.warning("Product rating not found")
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

        logger.warning("Product description unavailable")
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
                    logger.warning("Failed to parse variant dimensions JSON: %s", exc)
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
            logger.warning("No product reviews found on page")
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
                logger.error("Failed to parse review card layout: %s", exc)
                continue

        return reviews_list

    # ----- storage handling for reviews -----
    @staticmethod
    def save_reviews(asin: str) -> Tuple[str, str]:
        os.makedirs(REVIEWS_OUTPUT_DIR, exist_ok=True)
        csv_path = str(REVIEWS_OUTPUT_DIR / f"reviews_{asin}.csv")
        json_path = str(REVIEWS_OUTPUT_DIR / f"reviews_{asin}.json")

        for path in (csv_path, json_path):
            if os.path.exists(path):
                os.remove(path)
                logger.debug("Purged old tracking data file: %s", path)

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
            json.dump({"asin": asin, "total_reviews": 0, "reviews": []}, f, indent=4, ensure_ascii=False)

        logger.info("Initialized storage files | CSV: %s | JSON: %s", csv_path, json_path)
        return csv_path, json_path

    # ----- save data into csv and json file -----
    @staticmethod
    def write_reviews_to_storage(csv_path: str, json_path: str, reviews: list) -> None:
        if not reviews:
            logger.debug("No updates to persist; skipping storage update")
            return

        filename = os.path.basename(json_path)
        asin_match = re.search(r"reviews_([A-Z0-9]{10})", filename, re.IGNORECASE)
        asin_val = asin_match.group(1).upper() if asin_match else "UNKNOWN"

        with open(csv_path, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for r in reviews:
                r_num = r.get("review_number") if isinstance(r, dict) else getattr(r, "review_number", "")
                r_name = r.get("reviewer_name") if isinstance(r, dict) else getattr(r, "reviewer_name", "")
                r_loc = r.get("review_location") if isinstance(r, dict) else getattr(r, "review_location", "")
                r_date = r.get("review_date") if isinstance(r, dict) else getattr(r, "review_date", "")
                r_title = r.get("review_title") if isinstance(r, dict) else getattr(r, "review_title", "")
                r_rat = r.get("rating") if isinstance(r, dict) else getattr(r, "rating", "")
                r_body = r.get("review_body") if isinstance(r, dict) else getattr(r, "review_body", "")
                r_help = r.get("review_helpful") if isinstance(r, dict) else getattr(r, "review_helpful", "")

                writer.writerow([r_num, r_name, r_loc, r_date, r_title, r_rat, r_body, r_help])

        try:
            if os.path.exists(json_path) and os.path.getsize(json_path) > 0:
                with open(json_path, mode="r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict) or "reviews" not in data:
                    data = {"asin": asin_val, "total_reviews": 0, "reviews": []}
            else:
                data = {"asin": asin_val, "total_reviews": 0, "reviews": []}
        except (json.JSONDecodeError, FileNotFoundError):
            logger.warning("JSON tracking file corrupt or missing; resetting file structure: %s", json_path)
            data = {"asin": asin_val, "total_reviews": 0, "reviews": []}

        for r in reviews:
            if isinstance(r, dict):
                data["reviews"].append(r)
            else:
                data["reviews"].append({
                    "review_number": getattr(r, "review_number", ""),
                    "reviewer_name": getattr(r, "reviewer_name", ""),
                    "review_date": getattr(r, "review_date", ""),
                    "review_location": getattr(r, "review_location", ""),
                    "rating": getattr(r, "rating", None),
                    "review_title": getattr(r, "review_title", ""),
                    "review_body": getattr(r, "review_body", ""),
                    "review_helpful": getattr(r, "review_helpful", "")
                })

        data["total_reviews"] = len(data["reviews"])

        with open(json_path, mode="w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    # ----- automation tasks of playwright browser -----
    @staticmethod
    async def scroll_page(page) -> None:
        await asyncio.sleep(0.5)
        current_position = await page.evaluate("window.scrollY")

        while True:
            total_height = await page.evaluate("document.body.scrollHeight")
            distance = random.randint(250, 450)
            current_position += distance

            if current_position > total_height:
                current_position = total_height

            await page.evaluate(
                f"window.scrollTo({{top: {current_position}, behavior: 'smooth'}});"
            )

            await asyncio.sleep(random.uniform(0.15, 0.3))

            if current_position >= total_height:
                await asyncio.sleep(0.5)
                new_height = await page.evaluate("document.body.scrollHeight")
                if new_height == total_height:
                    break

        target_view_position = max(0, current_position - 450)
        await page.evaluate(
            f"window.scrollTo({{top: {target_view_position}, behavior: 'smooth'}});"
        )
        await asyncio.sleep(SCROLL_DELAY)

    # ----- find next page button in reviews page -----
    @staticmethod
    async def find_next_page_selector(page) -> Optional[str]:
        for selector in NEXT_PAGE_SELECTORS:
            try:
                if await page.is_visible(selector, timeout=800):
                    return selector
            except Exception:
                continue
        logger.debug("Next page selector not found for review pagination")
        return None

    # ----- taking details of reviews from reviews page -----
    @staticmethod
    def parse_page_reviews(nodes: list, seen: set, counter: int) -> Tuple[list, int]:
        reviews = []

        for node in nodes:
            name_el = node.find(*SELECTORS["reviewer"])
            date_el = node.find(*SELECTORS["review_date"])
            title_el = node.find(*SELECTORS["review_title"]) or node.select_one(".review-title")
            rating_el = node.find(*SELECTORS["review_rating"]) or node.select_one(".review-rating")
            body_el = node.find(*SELECTORS["review_body"]) or node.select_one(".review-text")
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

            rating_key = f"{rating:.1f}" if rating is not None else "none"
            sig = hash(f"{reviewer_name}_{review_date}_{review_title_text}_{rating_key}")
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
        return reviews, counter

    # ----- utility to convert SELECTORS tuple to playwright CSS string -----
    @staticmethod
    def _get_css_selector(selector_key: str) -> str:
        tag, attrs = SELECTORS[selector_key]
        attr_str = "".join([f"[{k}='{v}']" for k, v in attrs.items()])
        return f"{tag}{attr_str}"

    # ----- sign-in automation -----
    @staticmethod
    async def _navigate_to_post_login(page, post_login_url: str) -> None:
        if not post_login_url:
            return

        try:
            await page.goto("https://www.amazon.in", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(1.5)
        except Exception as exc:
            logger.debug("Homepage hop failed before redirect (continuing): %s", exc)

        await page.goto(post_login_url, wait_until="domcontentloaded", timeout=60000)

    @staticmethod
    async def _handle_signin(page, post_login_url: str) -> None:
        email = settings.AMAZON_EMAIL
        password = settings.AMAZON_PASSWORD

        if not email or not password:
            logger.warning("Amazon credentials missing in settings; skipping automated sign-in.")
            return

        email_sel = Scraper._get_css_selector("email")
        continue_sel = Scraper._get_css_selector("continue")
        password_sel = Scraper._get_css_selector("password")
        login_sel = Scraper._get_css_selector("login")

        try:
            logger.info("Evaluating Amazon login page...")

            try:
                if await page.locator(password_sel).count() > 0:
                    logger.info("Isolated password prompt detected; skipping email input.")
                    password_locator = page.locator(password_sel)
                    await password_locator.wait_for(state="visible", timeout=10000)
                    await password_locator.fill("")

                    logger.info("Submitting password...")
                    await password_locator.fill(password)
                    await asyncio.sleep(1)
                    await page.locator(login_sel).click()
                    await page.wait_for_load_state("domcontentloaded", timeout=30000)
                    logger.info("Password context challenge submitted.")

                    if post_login_url:
                        await Scraper._navigate_to_post_login(page, post_login_url)
                    return
            except Exception as exc:
                logger.debug("Password-only prompt analysis completed: %s", exc)

            email_selector_to_use = None
            try:
                await page.wait_for_selector(f"{email_sel}, #ap_email", state="visible", timeout=10000)
                if await page.locator(email_sel).count() > 0:
                    email_selector_to_use = email_sel
                elif await page.locator("#ap_email").count() > 0:
                    email_selector_to_use = "#ap_email"
            except Exception:
                pass

            if not email_selector_to_use:
                logger.debug("Standard login elements not found in viewport.")
                return

            logger.info("Amazon login email prompt verified.")
            email_locator = page.locator(email_selector_to_use)
            await email_locator.wait_for(state="visible", timeout=10000)
            await email_locator.fill("")

            logger.info("Entering email...")
            await email_locator.fill(email)
            logger.info("Email submitted successfully.")
            await asyncio.sleep(1)

            if await page.locator(continue_sel).count() > 0:
                await page.locator(continue_sel).click()

            new_user_selectors = [
                "input.a-button-input[aria-labelledby*='intention']",
                "text=Create account",
                "text=Proceed to create an account",
                "text=We cannot find an account with that email address"
            ]

            is_new_user = False
            password_visible = False

            for _ in range(30):
                if await page.locator(password_sel).is_visible():
                    password_visible = True
                    break

                for selector in new_user_selectors:
                    if await page.locator(selector).count() > 0 and await page.locator(selector).first.is_visible():
                        is_new_user = True
                        break
                if is_new_user:
                    break
                await asyncio.sleep(0.5)

            # ----- handle if email id is new on amazon -----
            if is_new_user:
                raise RuntimeError("Login Error - New user detected. Please use a registered email id and password.")

            if not password_visible:
                raise TimeoutError("Timed out waiting for password input or new-user screen sequence.")

            # ----- log and fill password -----
            password_locator = page.locator(password_sel)
            await password_locator.wait_for(state="visible", timeout=5000)
            await password_locator.fill("")

            logger.info("Entering password...")
            await password_locator.fill(password)
            logger.info("Password entered successfully.")
            await asyncio.sleep(1)
            await page.locator(login_sel).click()
            await page.wait_for_load_state("domcontentloaded", timeout=30000)

            if any(key in page.url.lower() for key in ("mfa", "auth-mfa", "verification", "ap/cvf")):
                logger.warning("MFA / OTP challenge encountered. Prompting user code via dashboard popup.")
                await Scraper._handle_otp_challenge(page)

            logger.info("Amazon authentication sequence completed.")
            if post_login_url:
                await Scraper._navigate_to_post_login(page, post_login_url)

        except Exception as exc:
            logger.error("%s", exc)
            if "New user detected" in str(exc):
                raise
            await asyncio.sleep(CAPTCHA_WAIT)

    # ----- locate the first matching selector out of a list of css fallbacks -----
    @staticmethod
    async def _first_visible_locator(page, css_fallbacks: list):
        for css in css_fallbacks:
            try:
                locator = page.locator(css).first
                if await locator.count() > 0 and await locator.is_visible():
                    return locator
            except Exception:
                continue
        return None

    @staticmethod
    async def _first_visible_locator_any_frame(page, css_fallbacks: list):
        locator = await Scraper._first_visible_locator(page, css_fallbacks)
        if locator is not None:
            return locator

        try:
            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                for css in css_fallbacks:
                    try:
                        frame_locator = frame.locator(css).first
                        if await frame_locator.count() > 0 and await frame_locator.is_visible():
                            return frame_locator
                    except Exception:
                        continue
        except Exception:
            pass

        return None

    # ----- handle otp challange -----
    @staticmethod
    async def _handle_otp_challenge(page) -> None:
        channel_options = await Scraper._detect_otp_channel_options(page)
        if channel_options:
            resolved = await Scraper._handle_otp_channel_choice(page, channel_options)
            if not resolved:
                logger.error("Failed to resolve OTP delivery-method choices; aborting verification flow.")
                return

        await Scraper._request_and_submit_otp_code(page)

    # ----- choose from option for otp -----
    @staticmethod
    async def _detect_otp_channel_options(page) -> list:
        try:
            radios = page.locator("input[type='radio']:visible")
            count = await radios.count()
        except Exception:
            return []

        if count == 0:
            return []

        try:
            otp_input_present = await Scraper._first_visible_locator_any_frame(page, OTP_INPUT_FALLBACKS)
            if otp_input_present is not None:
                return []
        except Exception:
            pass

        options = []
        for i in range(count):
            radio = radios.nth(i)
            try:
                label_text = (await Scraper._radio_label_text(page, radio)).strip()
                if not label_text:
                    continue
                value = await radio.get_attribute("value") or str(i)
                options.append({"index": i, "value": value, "label": label_text})
            except Exception:
                continue

        return options

    # ----- radio buttons text -----
    @staticmethod
    async def _radio_label_text(page, radio) -> str:
        try:
            radio_id = await radio.get_attribute("id")
            if radio_id:
                label = page.locator(f"label[for='{radio_id}']")
                if await label.count() > 0:
                    text = await label.first.inner_text()
                    if text.strip():
                        return text
        except Exception:
            pass

        try:
            ancestor_label = radio.locator("xpath=ancestor::label[1]")
            if await ancestor_label.count() > 0:
                text = await ancestor_label.first.inner_text()
                if text.strip():
                    return text
        except Exception:
            pass

        try:
            parent = radio.locator("xpath=..")
            text = await parent.inner_text()
            return text
        except Exception:
            return ""

    # ----- select from otp option -----
    @staticmethod
    async def _handle_otp_channel_choice(page, options: list) -> bool:
        labels = [o["label"] for o in options]
        logger.warning("Amazon delivery option required (options: %s). Requesting choice from dashboard.", labels)

        choice_future = await OtpManager.request_choice(labels)
        logger.info("Waiting up to %ds for user OTP channel choice submission via dashboard.", OTP_WAIT_TIMEOUT)

        try:
            chosen_label = await asyncio.wait_for(choice_future, timeout=OTP_WAIT_TIMEOUT)
        except asyncio.TimeoutError:
            logger.error("Timed out waiting for user OTP channel choice selection after %ds.", OTP_WAIT_TIMEOUT)
            OtpManager.cancel_choice()
            return False
        except asyncio.CancelledError:
            logger.warning("OTP channel choice wait sequence canceled by system.")
            raise

        match = next((o for o in options if o["label"] == chosen_label), None)
        if match is None:
            logger.warning("Selected choice '%s' mismatch; fallback to first available option.", chosen_label)
            match = options[0]

        try:
            radios = page.locator("input[type='radio']:visible")
            await radios.nth(match["index"]).check(force=True)
        except Exception as exc:
            logger.error("Failed to select OTP delivery option '%s': %s", match["label"], exc)
            return False

        await asyncio.sleep(0.3)

        send_btn = await Scraper._first_visible_locator(page, OTP_SEND_BUTTON_FALLBACKS)
        if send_btn is None:
            text_btn = page.get_by_role("button", name="Send OTP").or_(page.get_by_text("Send OTP"))
            if await text_btn.count() == 0:
                logger.error("Could not locate 'Send OTP' button element on screen.")
                return False
            send_btn = text_btn.first

        try:
            await send_btn.click()
            await page.wait_for_load_state("domcontentloaded", timeout=30000)
        except Exception as exc:
            logger.debug("Navigation wait exception after sending OTP: %s", exc)

        logger.info("OTP delivery method '%s' selected and request dispatched.", match["label"])
        return True

    # ----- request and submit otp for OTP_MAX_ATTEMPTS -----
    @staticmethod
    async def _request_and_submit_otp_code(page, max_attempts: int = OTP_MAX_ATTEMPTS) -> None:
        error_message = None

        for attempt in range(1, max_attempts + 1):
            otp_future = await OtpManager.request_otp(error=error_message)
            logger.info("Waiting up to %ds for dashboard user OTP entry (attempt %d/%d).", OTP_WAIT_TIMEOUT, attempt, max_attempts)

            try:
                otp_code = await asyncio.wait_for(otp_future, timeout=OTP_WAIT_TIMEOUT)
            except asyncio.TimeoutError:
                logger.error("Timed out waiting for dashboard user OTP code entry after %ds.", OTP_WAIT_TIMEOUT)
                OtpManager.cancel()
                return
            except asyncio.CancelledError:
                logger.warning("OTP wait process canceled by system.")
                raise

            logger.info("OTP received from dashboard (attempt %d/%d). Parsing page fields...", attempt, max_attempts)

            otp_input = await Scraper._locate_otp_input(page)
            if otp_input is None:
                logger.error("OTP code provided but verification text fields not found on page: %s", page.url)
                await Scraper._save_otp_debug_snapshot(page)
                OtpManager.cancel()
                return

            await otp_input.wait_for(state="visible", timeout=10000)
            await otp_input.fill("")
            await otp_input.fill(otp_code)
            await asyncio.sleep(0.5)

            otp_submit = await Scraper._first_visible_locator_any_frame(page, OTP_SUBMIT_FALLBACKS)
            if otp_submit is not None:
                await otp_submit.click()
            else:
                await otp_input.press("Enter")

            try:
                await page.wait_for_load_state("domcontentloaded", timeout=30000)
            except Exception:
                logger.debug("Navigation timeout following OTP submission (continuing).")

            if not await Scraper.is_login_page(page):
                logger.info("OTP verified successfully. Browser session authenticated.")
                OtpManager.cancel()
                return

            logger.warning("OTP submission attempt %d/%d failed to clear verification screen. Retrying...", attempt, max_attempts)

            if attempt < max_attempts:
                error_message = "That code didn't work. Please check it and try again."
                await asyncio.sleep(1)
                continue

        logger.error("All %d OTP submission attempts exhausted; authentication challenge failed.", max_attempts)
        OtpManager.cancel()

    # ----- fill otp input box -----
    @staticmethod
    async def _locate_otp_input(page):
        try:
            await page.wait_for_selector(", ".join(OTP_INPUT_FALLBACKS), state="visible", timeout=20000)
        except Exception:
            pass

        otp_input = await Scraper._first_visible_locator_any_frame(page, OTP_INPUT_FALLBACKS)
        if otp_input is not None:
            return otp_input

        frames_to_scan = [page.main_frame] + [f for f in page.frames if f != page.main_frame]
        for frame in frames_to_scan:
            try:
                candidates = frame.locator("input:visible")
                count = await candidates.count()
                for i in range(count):
                    candidate = candidates.nth(i)
                    try:
                        input_type = (await candidate.get_attribute("type")) or "text"
                        if input_type.lower() in ("hidden", "checkbox", "radio", "submit", "button", "image"):
                            continue

                        name = (await candidate.get_attribute("name")) or ""
                        cid = (await candidate.get_attribute("id")) or ""
                        autocomplete = (await candidate.get_attribute("autocomplete")) or ""
                        placeholder = (await candidate.get_attribute("placeholder")) or ""
                        haystack = f"{name} {cid} {autocomplete} {placeholder}".lower()

                        if any(token in haystack for token in ("otp", "code", "pin", "one-time", "otc")):
                            return candidate
                    except Exception:
                        continue
            except Exception:
                continue

        return None

    # ----- save screenshot if the otp not successfull -----
    @staticmethod
    async def _save_otp_debug_snapshot(page) -> None:
        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            debug_path = str(OUTPUT_DIR / "debug_otp_page.png")
            await page.screenshot(path=debug_path, full_page=True)
            logger.info("Saved screenshot of unrecognized verification page to: %s", debug_path)
        except Exception as exc:
            logger.debug("Failed to capture OTP debug screenshot: %s", exc)

    @staticmethod
    async def ensure_logged_in(page, target_url: str, max_attempts: int = SIGNIN_MAX_ATTEMPTS) -> bool:
        if not await Scraper.is_login_page(page):
            return True

        for attempt in range(1, max_attempts + 1):
            logger.info("Login page redirect detected. Starting authentication workflow (attempt %d/%d)...", attempt, max_attempts)
            await Scraper._handle_signin(page, target_url)
            await asyncio.sleep(2)

            if not await Scraper.is_login_page(page):
                logger.info("Authentication validated successfully.")
                return True

            logger.warning("Still on login/verification interface after attempt %d/%d.", attempt, max_attempts)

            if attempt < max_attempts:
                try:
                    await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                except Exception as exc:
                    logger.debug("Target URL re-navigation failed before fallback retry: %s", exc)
                await asyncio.sleep(1)

        logger.error("Authentication failed. Session stuck on auth screens after %d attempts.", max_attempts)
        raise RuntimeError("Authentication check failed — Session stuck on authentication interface.")

    @staticmethod
    async def is_login_page(page) -> bool:
        url = page.url.lower()
        if any(token in url for token in ("ap/signin", "signin", "ap/login", "authentication")):
            return True

        email_sel = Scraper._get_css_selector("email")
        password_sel = Scraper._get_css_selector("password")

        try:
            return (
                await page.locator(email_sel).count() > 0
                or await page.locator("#ap_email").count() > 0
                or await page.locator(password_sel).count() > 0
            )
        except Exception:
            return False

    # ----- pure async playwright execution context for dedicated reviews loop -----
    @staticmethod
    async def run_reviews_playwright(url: str) -> list:
        try:
            asin = Scraper.extract_asin(url)
            logger.debug("Extracted ASIN: %s", asin)
        except ValueError as e:
            logger.error(str(e))
            return []

        reviews_url = f"https://www.amazon.in/product-reviews/{asin}?reviewerType=all_reviews"
        csv_path, json_path = Scraper.save_reviews(asin)

        reviews_session_dir = os.path.join(SESSION_DIR, f"reviews_{asin}")
        os.makedirs(reviews_session_dir, exist_ok=True)

        seen: set = set()
        total = 0
        page_num = 1

        async with async_playwright():
            context = await BrowserManager.start()
            try:
                try:
                    page = await context.new_page()
                except PlaywrightError as e:
                    if "TargetClosedError" in str(e) or "closed" in str(e).lower():
                        logger.warning("Browser context closed before initialization of reviews loop could finish.")
                        return []
                    raise e

                await Stealth().apply_stealth_async(page)
                await page.goto(reviews_url, wait_until="domcontentloaded", timeout=60000)

                try:
                    await Scraper.ensure_logged_in(page, reviews_url)
                except RuntimeError as auth_err:
                    raise auth_err

                while True:
                    try:
                        await asyncio.sleep(0)
                    except asyncio.CancelledError:
                        logger.info("ASIN %s: Reviews extraction worker caught cancellation signal. Exiting gracefully.", asin)
                        raise

                    logger.info("[Reviews ASIN: %s] Scraping page %d...", asin, page_num)

                    is_captcha_page = await page.locator("form[action*='captcha'], input[id='captchacharacters']").count() > 0
                    if is_captcha_page:
                        logger.warning("Captcha challenge page detected. Pausing process for %ds.", CAPTCHA_WAIT)
                        await asyncio.sleep(CAPTCHA_WAIT)

                    await Scraper.scroll_page(page)

                    page_source = await page.content()
                    soup = BeautifulSoup(page_source, "html.parser")

                    nodes = soup.select('[data-hook="review"]') or soup.select(".review")

                    if not nodes:
                        logger.info("No tracking review cards match layout structures on page %d. Processing complete.", page_num)
                        break

                    reviews, total = Scraper.parse_page_reviews(nodes, seen, total)

                    current_stored_count = total - len(reviews)
                    allowed_remaining = settings.THRESHOLD_LIMIT - current_stored_count

                    if len(reviews) > allowed_remaining:
                        reviews = reviews[:allowed_remaining]
                        total = settings.THRESHOLD_LIMIT

                    Scraper.write_reviews_to_storage(csv_path, json_path, reviews)

                    logger.info("[Reviews ASIN: %s] Page %d complete | Added +%d reviews | Total collected: %d", asin, page_num, len(reviews), total)

                    if total >= settings.THRESHOLD_LIMIT:
                        logger.info("Extraction threshold reached. Completed %d items from %d pages.", settings.THRESHOLD_LIMIT, page_num)
                        break

                    next_selector = await Scraper.find_next_page_selector(page)
                    if not next_selector:
                        logger.info("Pagination sequence completed.")
                        break

                    next_button = page.locator(next_selector).first
                    await next_button.scroll_into_view_if_needed()
                    await asyncio.sleep(0.5)

                    try:
                        await next_button.click()
                        await page.wait_for_load_state("domcontentloaded", timeout=15000)
                    except Exception:
                        logger.warning("Pagination event element selection triggered unusual state change. Proceeding...")

                    try:
                        await page.wait_for_selector("[data-hook='review']", state="attached", timeout=8000)
                    except Exception:
                        logger.warning("Expected review cards not found in immediate viewport post-navigation.")

                    await asyncio.sleep(PAGE_DELAY)
                    page_num += 1
            finally:
                try:
                    await page.close()
                except Exception:
                    pass

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                final_reviews = json.load(f)
            return final_reviews.get("reviews", []) if isinstance(final_reviews, dict) else final_reviews
        except Exception as err:
            logger.error("Failed to read consolidated storage data file from disk: %s", err)
            return []

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
    def _extract_delivery_days(card: BeautifulSoup) -> Union[int, str]:
        container = card.select_one("div[data-cy='delivery-recipe-container']")
        search_root = container if container else card
        for span in search_root.find_all("span"):
            text = span.get_text(separator=" ", strip=True)
            if any(kw in text.lower() for kw in ("delivery", "arrive", "get it", "ships")):
                days = Scraper._parse_delivery_days(text)
                if days is not None:
                    return days

        for span in search_root.select("span.a-text-bold"):
            text = span.get_text(strip=True)
            days = Scraper._parse_delivery_days(text)
            if days is not None:
                return days

        return "Unavailable"

    # ----- search products prices -----
    @staticmethod
    def _extract_search_price(card: BeautifulSoup) -> Union[float, str]:
        for sel in (
            "span.a-price:not(.a-text-strike) span.a-offscreen",
            "span[data-a-color='base'] span.a-offscreen",
        ):
            tag = card.select_one(sel)
            if tag:
                cleaned = _REGEX_PRICE_CLEAN.sub("", tag.get_text(strip=True))
                cleaned = cleaned.rstrip(".")
                try:
                    return float(cleaned) if cleaned else "Unavailable"
                except ValueError:
                    continue

        whole_el = card.select_one("span.a-price-whole")
        if whole_el:
            whole = _REGEX_NON_DIGIT.sub("", whole_el.get_text(strip=True))
            frac_el = card.select_one("span.a-price-fraction")
            frac = _REGEX_NON_DIGIT.sub("", frac_el.get_text(strip=True)) if frac_el else "00"
            frac = frac.ljust(2, "0")[:2]
            try:
                return float(f"{whole}.{frac}") if whole else "Unavailable"
            except ValueError:
                return "Unavailable"

        return "Unavailable"

    # ----- saving data of the searched product -----
    @staticmethod
    def _parse_search_card(card: BeautifulSoup) -> Optional[Dict[str, Any]]:
        asin = card.get("data-asin", "").strip()
        if not asin:
            return None

        title: str = "N/A"
        h2_anchor = card.select_one("h2 a") or card.select_one("a.a-link-normal.s-line-clamp-2")
        if h2_anchor:
            title = h2_anchor.get("aria-label", "").strip()
            if not title:
                title = h2_anchor.get_text(separator=" ", strip=True)
        if title == "N/A" or not title:
            h2_tag = card.select_one("h2")
            if h2_tag:
                title = h2_tag.get_text(separator=" ", strip=True) or "N/A"

        price = Scraper._extract_search_price(card)
        link: str = f"https://www.amazon.in/dp/{asin}/"
        delivery_duration_days = Scraper._extract_delivery_days(card)

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
        return str(SEARCH_OUTPUT_DIR / filename)

    # ----- next button for next page -----
    @staticmethod
    async def _find_search_next_page(page) -> Optional[str]:
        for selector in SEARCH_NEXT_PAGE_SELECTORS:
            try:
                locator = page.locator(selector).first
                if await locator.is_visible(timeout=800):
                    return selector
            except Exception:
                continue
        logger.debug("Next page selector missing from search catalog layout context.")
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
            logger.error("Failed to save search history temp storage file on page %d: %s", page_num, exc, exc_info=True)

    # ----- playwright execution context for dedicated search query loop -----
    @staticmethod
    async def run_search_playwright(query: str) -> Dict[str, Any]:
        base_url = "https://www.amazon.in"
        output_path = Scraper._build_search_output_path(query)
        search_url = f"{base_url}/s?k={quote_plus(query)}"
        all_products: List[Dict[str, Any]] = []
        seen_asins: set = set()
        page_num = 1

        safe_slug = re.sub(r"[^\w\-_]", "_", query.strip().lower())
        search_session_dir = os.path.join(SESSION_DIR, f"search_{safe_slug}")
        os.makedirs(search_session_dir, exist_ok=True)

        async with async_playwright():
            context = await BrowserManager.start()
            try:
                try:
                    page = await context.new_page()
                except PlaywrightError as e:
                    if "TargetClosedError" in str(e) or "closed" in str(e).lower():
                        logger.warning("Browser context closed before search operations could initialize.")
                        return {"status": "cancelled", "message": "Browser session closed."}
                    raise e
                await Stealth().apply_stealth_async(page)

                logger.debug("Navigating browser to: %s", search_url)
                await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)

                while True:
                    try:
                        await asyncio.sleep(0)
                    except asyncio.CancelledError:
                        logger.info("[Search Query: '%s'] Core search processing worker received interruption flag.", query)
                        raise

                    await Scraper.ensure_logged_in(page, search_url)
                    logger.info("[Search Query: '%s'] Scraping catalog page %d...", query, page_num)

                    is_captcha_page = await page.locator("form[action*='captcha'], input[id='captchacharacters']").count() > 0
                    if is_captcha_page:
                        logger.warning("Captcha block parsed. Stopping execution runner for %ds.", CAPTCHA_WAIT)
                        await asyncio.sleep(CAPTCHA_WAIT)

                    if await Scraper.is_login_page(page):
                        logger.warning("Unexpected navigation redirect triggered away from catalog path structure.")
                        if not await Scraper.ensure_logged_in(page, search_url):
                            break

                    await Scraper.scroll_page(page)

                    soup = BeautifulSoup(await page.content(), "html.parser")
                    cards = soup.select("div[data-component-type='s-search-result'][data-asin]")
                    if not cards:
                        cards = soup.select("div.s-result-item[data-asin]")

                    clean_query = re.sub(r"[^\w\s]", " ", query.lower().strip())
                    STOP_WORDS = {"and", "for", "with", "the", "under", "from", "in", "of", "to", "by", "a", "an", "online"}
                    query_tokens = [token for token in clean_query.split() if token and token not in STOP_WORDS]

                    page_extracted_count = 0
                    for card in cards:
                        if len(all_products) >= settings.THRESHOLD_LIMIT:
                            break

                        try:
                            asin = card.get("data-asin", "").strip()
                            if not asin or asin in seen_asins:
                                continue
                            product = Scraper._parse_search_card(card)

                            if product:
                                title_lower = product["title"].lower()

                                if "case" not in clean_query and "cover" not in clean_query:
                                    if any(stop_pattern in title_lower for stop_pattern in [" case ", " cover ", " pouch "]):
                                        continue

                                if len(query_tokens) >= 2:
                                    primary_identifier = query_tokens[0]
                                    primary_matched = (primary_identifier in title_lower) or (primary_identifier in title_lower.replace("-", ""))
                                    other_tokens_match = any(token in title_lower for token in query_tokens[1:])

                                    if not (primary_matched and other_tokens_match):
                                        continue

                                elif len(query_tokens) == 1:
                                    if not any(token in title_lower for token in query_tokens):
                                        continue

                                seen_asins.add(asin)
                                all_products.append(product)
                                page_extracted_count += 1
                        except Exception as exc:
                            logger.warning("Skipped anomalous result node on page %d: %s", page_num, exc)
                            continue

                    Scraper._persist_search_progress(all_products, output_path, page_num)
                    logger.info("[Search Query: '%s'] Page %d complete | Added +%d items | Total items: %d", query, page_num, page_extracted_count, len(all_products))

                    if len(all_products) >= settings.THRESHOLD_LIMIT:
                        break

                    next_selector = await Scraper._find_search_next_page(page)
                    if not next_selector:
                        logger.info("Search pagination sequence hit final results page panel framework.")
                        break

                    next_button = page.locator(next_selector).first
                    await next_button.scroll_into_view_if_needed()
                    await asyncio.sleep(0.5)

                    try:
                        await next_button.click()
                        await page.wait_for_load_state("domcontentloaded", timeout=15000)
                    except Exception:
                        logger.warning("Pagination selection event execution caught exception step panel updates.")

                    await Scraper.ensure_logged_in(page, search_url)

                    _CARD_SELECTOR = "div[data-component-type='s-search-result'][data-asin], div.s-result-item[data-asin]"
                    try:
                        await page.wait_for_selector(_CARD_SELECTOR, state="attached", timeout=8000)
                    except Exception:
                        logger.warning("Catalog results not visible; re-verifying verification layers...")
                        if await Scraper.is_login_page(page):
                            await Scraper.ensure_logged_in(page, search_url)
                            await page.wait_for_selector(_CARD_SELECTOR, state="attached", timeout=10000)

                    await asyncio.sleep(PAGE_DELAY)
                    page_num += 1

            finally:
                Scraper._persist_search_progress(all_products, output_path, page_num)
                try:
                    await page.close()
                except Exception:
                    pass

        logger.debug("Scraping completed successfully — %d elements processed via %d pages.", len(all_products), page_num)
        return {"total_products": len(all_products), "products": all_products}

    # ----- asynchronous single product scraping context -----
    async def scraping_data(self) -> ScrapeResult:
        logger.info("Starting product data extraction workflow...")
        try:
            try:
                asin = Scraper.extract_asin(self.url)
                logger.debug("Extracted ASIN: %s", asin)
            except ValueError as e:
                return ScrapeResult(
                    product=None,
                    success=False,
                    reason=ScrapeFailReason.PARSE_ERROR,
                    detail=str(e),
                )

            session = Scraper._new_session()
            response = await asyncio.to_thread(session.get, self.url, timeout=15)
            if response.status_code == 404:
                return ScrapeResult(
                    product=None,
                    success=False,
                    reason=ScrapeFailReason.PARSE_ERROR,
                    detail="Target product entry not found in active catalog maps (404 Error).",
                )

            response.raise_for_status()
            self.save_raw_response(response.text)

        except requests.RequestException as error:
            logger.error("HTTP network execution failure: %s", error, exc_info=True)
            return ScrapeResult(
                product=None,
                success=False,
                reason=ScrapeFailReason.NETWORK_ERROR,
                detail=f"Network error while fetching URL: {error}",
            )

        soup = BeautifulSoup(response.content, "html.parser")
        if Scraper.is_blocked(soup):
            logger.warning("Amazon robot verification intercept or block detected.")
            return ScrapeResult(
                product=None,
                success=False,
                reason=ScrapeFailReason.BLOCKED,
                detail="Amazon blocked the request. Try again later.",
            )

        try:
            title = self.title_details(soup)

            product = Product(
                asin=asin,
                title=title,
                image=self.image_details(soup),
                price=self.price_details(soup),
                ratings=self.ratings_details(soup),
                ratings_count=self.ratings_count(soup),
                description=self.description_details(soup, title),
                variants=self.variants_details(soup),
            )
            return ScrapeResult(product=product, success=True, reason=None, detail="")

        except Exception as exc:
            return ScrapeResult(
                product=None,
                success=False,
                reason=ScrapeFailReason.PARSE_ERROR,
                detail=f"Failed to parse product data: {exc}",
            )

    # ----- taking html file of the product page -----
    def save_raw_response(self, html_content: str) -> None:
        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            file_path = str(OUTPUT_DIR / "source.html")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            logger.info("Raw source HTML committed successfully to storage workspace.")
        except OSError as e:
            logger.error("Failed to write raw HTML layout to disk tracking structure paths: %s", e)

    # ----- data display formatting output -----
    @staticmethod
    def print_data(product: Product) -> None:
        print(json.dumps(product.to_dict(), ensure_ascii=False, indent=4))