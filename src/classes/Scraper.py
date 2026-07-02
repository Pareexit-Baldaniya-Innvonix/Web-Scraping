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
    OUTPUT_DIR,
    PAGE_DELAY,
    REVIEWS_OUTPUT_DIR,
    SCROLL_DELAY,
    SEARCH_NEXT_PAGE_SELECTORS,
    SEARCH_OUTPUT_DIR,
    SESSION_DIR,
)
from src.config.selectors import SELECTORS
from src.utils.logger import get_logger
from .Product import Product
from .Review import Review
from .BrowserManager import BrowserManager
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
        logger.debug("Scraper successfully initialized for URL: %s", self.url)

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
        logger.debug("Validating Target Amazon URL: %s", url)
        try:
            parsed_url = urlparse(url)
            if parsed_url.scheme not in ("http", "https"):
                logger.warning(
                    "Invalid URL scheme '%s' provided for URL: %s", parsed_url.scheme, url
                )
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
            logger.error("URL validation encountered an unexpected exception: %s", exc, exc_info=True)
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

        logger.error("Failed to extract a valid Amazon ASIN from URL: %s", url)
        raise ValueError(f"Could not extract a valid ASIN from URL: {url}")

    # ----- product title -----
    def title_details(self, soup: BeautifulSoup) -> str:
        title_tag = soup.find(*SELECTORS["title"])
        if title_tag:
            return title_tag.get_text(strip=True)
        logger.warning("Product title element could not be found in the DOM")
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
            logger.warning("Product price element could not be found in the DOM")
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
            logger.warning("No main product images container found in the DOM")
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
            logger.debug("Successfully parsed %d clean high-resolution image URLs", len(img_urls))
            return img_urls

        logger.warning("No high-resolution product image links were extracted")
        return None

    # ----- product ratings -----
    def ratings_details(self, soup: BeautifulSoup) -> Optional[float]:
        for selector in [SELECTORS["ratings_popover"], SELECTORS["ratings_alt"]]:
            ratings_tag = soup.find(*selector)
            if ratings_tag and ratings_tag.get_text().strip():
                match = _REGEX_RATING.search(ratings_tag.get_text().strip())
                if match:
                    return float(match.group(1))
        logger.warning("Product aggregate rating not found")
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
        logger.warning("Global review count metrics not found")
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

        logger.warning("Product description text completely unavailable")
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
                    logger.warning("Failed to parse dynamic twister multi-variant dimension state JSON: %s", exc)
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
            logger.warning("No individual product reviews found on this landing page layout")
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
                logger.error("Failed to parse single isolated review card structure: %s", exc)
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
                logger.debug("Purged old structural data file: %s", path)

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

        logger.info("Initialized tracking files successfully | CSV: %s | JSON: %s", csv_path, json_path)
        return csv_path, json_path

    # ----- save data into csv and json file -----
    @staticmethod
    def write_reviews_to_storage(csv_path: str, json_path: str, reviews: list) -> None:
        if not reviews:
            logger.debug("No updates to persist; skipping storage commit")
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
            logger.warning("JSON persistence target corrupt or missing; dropping back to standard frame initialization: %s", json_path)
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
        logger.debug("There is no next-page element for pagination in current page")
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
    async def _handle_signin(page, post_login_url: str) -> None:
        email = settings.AMAZON_EMAIL
        password = settings.AMAZON_PASSWORD

        if not email or not password:
            logger.warning("Amazon login credentials missing in local settings; dropping automation path.")
            return

        email_sel = Scraper._get_css_selector("email")
        continue_sel = Scraper._get_css_selector("continue")
        password_sel = Scraper._get_css_selector("password")
        login_sel = Scraper._get_css_selector("login")

        try:
            logger.info("Evaluating Amazon Login page...")

            try:
                if await page.locator(password_sel).count() > 0:
                    logger.info("Isolated password input detected; routing straight to password dispatch.")
                    password_locator = page.locator(password_sel)
                    await password_locator.wait_for(state="visible", timeout=10000)
                    await password_locator.fill("")
                    
                    logger.info("Entering password into isolated prompt: %s", password)
                    await password_locator.fill(password)
                    await asyncio.sleep(1)
                    await page.locator(login_sel).click()
                    await page.wait_for_load_state("domcontentloaded", timeout=30000)
                    logger.info("Password context challenge dispatched successfully.")

                    if post_login_url:
                        await page.goto(post_login_url, wait_until="domcontentloaded", timeout=60000)
                    return
            except Exception as exc:
                logger.debug("Password-only shortcut evaluated and skipped: %s", exc)

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
                logger.debug("Standard identity/login input frames not found in viewport.")
                return

            logger.info("Primary Amazon Email identity prompt verified.")
            email_locator = page.locator(email_selector_to_use)
            await email_locator.wait_for(state="visible", timeout=10000)
            await email_locator.fill("")
            
            # ----- log and fill email -----
            logger.info("Entering email...")
            await email_locator.fill(email)
            logger.info("Email entered successfully!")
            await asyncio.sleep(1)

            if await page.locator(continue_sel).count() > 0:
                await page.locator(continue_sel).click()

            logger.info("Waiting for password screen or validation shift...")
            
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
                logger.warning("Email not recognized. 'It looks like you are new to Amazon' state or warning detected.")
                
                create_account_btn = page.locator("input.a-button-input[aria-labelledby*='intention']").or_(
                    page.locator("input#continue[type='submit']")
                ).or_(
                    page.get_by_text("Proceed to create an account")
                )
                
                if await create_account_btn.count() > 0:
                    try:
                        await create_account_btn.first.click(force=True)
                        await page.wait_for_load_state("domcontentloaded")
                    except Exception:
                        pass
                
                logger.info("Pausing automation for 120 seconds for manual intervention / account registration.")
                await asyncio.sleep(120) 
                
                if post_login_url:
                    await page.goto(post_login_url, wait_until="domcontentloaded", timeout=60000)
                return

            if not password_visible:
                raise TimeoutError("Timed out waiting for password field to appear or new user prompt to step in.")

            # ----- log and fill password -----
            password_locator = page.locator(password_sel)
            await password_locator.wait_for(state="visible", timeout=5000)
            await password_locator.fill("")
            
            logger.info("Entering password...")
            await password_locator.fill(password)
            logger.info("Password entered successfully!")
            await asyncio.sleep(1)
            await page.locator(login_sel).click()
            await page.wait_for_load_state("domcontentloaded", timeout=30000)

            if any(key in page.url.lower() for key in ("mfa", "auth-mfa", "verification", "ap/cvf")):
                logger.warning("Multi-Factor Authentication or OTP challenge encountered! Parking session for %ds.", CAPTCHA_WAIT)
                await asyncio.sleep(CAPTCHA_WAIT)

            logger.info("Amazon credentials authentication lifecycle completed.")
            if post_login_url:
                await page.goto(post_login_url, wait_until="domcontentloaded", timeout=60000)

        except Exception as exc:
            logger.error("Automated re-authentication routine failed: %s", exc, exc_info=True)
            await asyncio.sleep(CAPTCHA_WAIT)

    @staticmethod
    async def ensure_logged_in(page, target_url: str) -> bool:
        if not await Scraper.is_login_page(page):
            return True

        logger.info("Login page redirect detected. Initiating automated authentication workflow...")
        await Scraper._handle_signin(page, target_url)
        await asyncio.sleep(2)

        if await Scraper.is_login_page(page):
            logger.error("Authentication check failed — Session stuck on authentication interface.")
            raise RuntimeError("Authentication check failed — Session stuck on authentication interface.")

        logger.info("Authentication validated successfully.")
        return True

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
            logger.debug("Extracted ASIN from URL path: %s", asin)
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

        async with async_playwright() as p:
            context = await BrowserManager.start()
            try:
                try:
                    page = await context.new_page()
                except PlaywrightError as e:
                    if "TargetClosedError" in str(e) or "closed" in str(e).lower():
                        logger.warning("Browser context was closed before the page could open in reviews parsing loop.")
                        return []
                    raise e

                await Stealth().apply_stealth_async(page) 
                await page.goto(reviews_url, wait_until="domcontentloaded", timeout=60000)

                try:
                    await Scraper.ensure_logged_in(page, reviews_url)
                except RuntimeError as auth_err:
                    logger.error("Stopping reviews scraper loop due to fatal initial authentication error.", auth_err)
                    raise 

                while True:
                    try:
                        await asyncio.sleep(0)
                    except asyncio.CancelledError:
                        logger.info("ASIN %s: Reviews extraction worker caught cancellation signal. Halting execution gracefully.", asin)
                        raise

                    logger.info("[Reviews ASIN: %s] Started scraping page %d...", asin, page_num)

                    is_captcha_page = await page.locator("form[action*='captcha'], input[id='captchacharacters']").count() > 0
                    if is_captcha_page:
                        logger.warning(" [BLOCK] Captcha payload page confirmed. Interrupted for %ds.", CAPTCHA_WAIT)
                        await asyncio.sleep(CAPTCHA_WAIT)

                    await Scraper.scroll_page(page)
                    
                    page_source = await page.content()
                    soup = BeautifulSoup(page_source, "html.parser")

                    nodes = soup.select('[data-hook="review"]') or soup.select(".review")

                    if not nodes:
                        logger.info("No matching review cards matching standard selectors parsed on page %d. Processing complete.", page_num)
                        break

                    reviews, total = Scraper.parse_page_reviews(nodes, seen, total)
                    
                    current_stored_count = total - len(reviews)
                    allowed_remaining = settings.THRESHOLD_LIMIT - current_stored_count
                    
                    if len(reviews) > allowed_remaining:
                        reviews = reviews[:allowed_remaining]
                        total = settings.THRESHOLD_LIMIT

                    Scraper.write_reviews_to_storage(csv_path, json_path, reviews)

                    logger.info("[Reviews ASIN: %s] Page %d scrapped successfully | Added +%d reviews | Total data: %d", asin, page_num, len(reviews), total)

                    if total >= settings.THRESHOLD_LIMIT:
                        logger.info("Scraping completed successfully - %d data compiled from %d pages", settings.THRESHOLD_LIMIT, page_num)
                        break

                    next_selector = await Scraper.find_next_page_selector(page)
                    if not next_selector:
                        logger.info("Task completed")
                        break

                    next_button = page.locator(next_selector).first
                    await next_button.scroll_into_view_if_needed()
                    await asyncio.sleep(0.5)

                    try:
                        await next_button.click()
                        await page.wait_for_load_state("domcontentloaded", timeout=15000)
                    except Exception:
                        logger.warning("Pagination event execution triggered a non-standard browser DOM event structure shift. Continuing cautiously...")

                    try:
                        await page.wait_for_selector("[data-hook='review']", state="attached", timeout=8000)
                    except Exception:
                        logger.warning("Target metrics missing from immediate viewport following navigation action.")

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
            logger.error("Failed to read back final storage file data from the disk: %s", err)
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
        logger.debug("Catalog pagination search selector target missing from DOM context")
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
                "Failed to successfully serialize and swap temporary search storage file at checkpoint step page %d: %s",
                page_num,
                exc,
                exc_info=True,
            )

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

        async with async_playwright() as p:
            context = await BrowserManager.start()
            try:
                try:
                    page = await context.new_page()
                except PlaywrightError as e:
                    if "TargetClosedError" in str(e) or "closed" in str(e).lower():
                        logger.warning("Browser context was closed before the page could open.")
                        return {"status": "cancelled", "message": "Browser session closed."}
                    raise e
                await Stealth().apply_stealth_async(page) 

                logger.debug("Navigating browser to search: %s", search_url)
                await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)

                while True:
                    try:
                        await asyncio.sleep(0)
                    except asyncio.CancelledError:
                        logger.info("[Search Query: '%s'] Main search runtime loop received interruption abort command.", query)
                        raise

                    await Scraper.ensure_logged_in(page, search_url)
                    logger.info("[Search Query: '%s'] Started scraping page %d...", query, page_num)

                    is_captcha_page = await page.locator("form[action*='captcha'], input[id='captchacharacters']").count() > 0
                    if is_captcha_page:
                        logger.warning(" [BLOCK] Captcha page detected. Resting automation threads for %ds.", CAPTCHA_WAIT)
                        await asyncio.sleep(CAPTCHA_WAIT)
                    else:
                        pass

                    if await Scraper.is_login_page(page):
                        logger.warning("Amazon unexpected validation intercept routed session out of the marketplace timeline.")
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
                            logger.warning("Skipped parsing anomalous index result node element on page %d: %s", page_num, exc)
                            continue

                    Scraper._persist_search_progress(all_products, output_path, page_num)
                    logger.info("[Search Query: '%s'] Page %d scrapped successfully | Added +%d items | Total data: %d", query, page_num, page_extracted_count, len(all_products))

                    if len(all_products) >= settings.THRESHOLD_LIMIT:
                        break

                    next_selector = await Scraper._find_search_next_page(page)
                    if not next_selector:
                        logger.info("Search pagination sequence has hit terminal page view layout structure.")
                        break

                    next_button = page.locator(next_selector).first
                    await next_button.scroll_into_view_if_needed()
                    await asyncio.sleep(0.5)

                    try:
                        await next_button.click()
                        await page.wait_for_load_state("domcontentloaded", timeout=15000)
                    except Exception:
                        logger.warning("Search dynamic pagination interaction encountered an exception event step.")

                    await Scraper.ensure_logged_in(page, search_url)

                    _CARD_SELECTOR = "div[data-component-type='s-search-result'][data-asin], div.s-result-item[data-asin]"
                    try:
                        await page.wait_for_selector(_CARD_SELECTOR, state="attached", timeout=8000)
                    except Exception:
                        logger.warning("Result elements not active inside the layout workspace block. Re-verifying active validation layers...")
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

        logger.debug("Scraping completed successfully — %d data compiled from %d pages", len(all_products), page_num)
        return {"total_products": len(all_products), "products": all_products}
    
    # ----- asynchronous single product scraping context -----
    async def scraping_data(self) -> ScrapeResult:
        logger.info("Synchronous single product data extraction task running...")
        try:
            try:
                asin = Scraper.extract_asin(self.url)
                logger.debug("Extracted ASIN from URL path: %s", asin)
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
                    detail="Target product not found or entry dropped from store catalog indices (404 Error code).",
                )

            response.raise_for_status()
            self.save_raw_response(response.text)

        except requests.RequestException as error:
            logger.error("HTTP data extraction execution context failure: %s", error, exc_info=True)
            return ScrapeResult(
                product=None,
                success=False,
                reason=ScrapeFailReason.NETWORK_ERROR,
                detail=f"Network error while fetching URL: {error}",
            )

        soup = BeautifulSoup(response.content, "html.parser")
        if Scraper.is_blocked(soup):
            logger.warning("Amazon network interaction channel block or verification intercept parsed.")
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
            logger.info("Raw interface source layout copy successfully written to workspace disk")
        except OSError as e:
            logger.error("Failed to commit raw DOM layout context data down onto system tracking paths: %s", e)

    # ----- data display formatting output -----
    @staticmethod
    def print_data(product: Product) -> None:
        print(json.dumps(product.to_dict(), ensure_ascii=False, indent=4))