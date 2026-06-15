# ----- library import -----
import re
import os
import csv
import json
import time
import asyncio
import requests
from bs4 import BeautifulSoup
from typing import List, Optional, Tuple, Dict, Any
from urllib.parse import parse_qs, urlparse, urlunparse

from playwright_stealth.stealth import Stealth
from playwright.sync_api import sync_playwright

# ----- local import -----
from .Review import Review
from .Product import Product
from .ScrapeResult import ScrapeResult
from .ScrapeFailReason import ScrapeFailReason
from src.config.selectors import SELECTORS
from src.config.constants import HEADERS, OUTPUT_DIR, COOKIES
from src.utils.logger import get_logger, setup_logging

# ----- initialize logging configuration -----
setup_logging()
logger = get_logger("SCRAPER")


# ----- review scraper constants -----
_SESSION_DIR = "./amazon_user_session"
_PAGE_DELAY = 2.5
_SCROLL_DELAY = 0.4
_CAPTCHA_WAIT = 20
_HEADLESS = False
_NEXT_PAGE_SELECTORS = [
    "li.a-last a",
    "ul.a-pagination li.a-last a",
    "a:has-text('Next page')",
    "a:has-text('Next >')",
    "a:has-text('More reviews')",
    "[data-hook='show-more-button']",
]

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


class Scraper:
    # ----- initialization -----
    def __init__(self, url: str) -> None:
        self.url: str = Scraper.normalize_url(url)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.cookies.update(COOKIES)
        logger.debug("Scraper initialized for URL: %s", self.url)

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
            title = title_tag.get_text(strip=True)
            return title
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
    def image_details(self, soup: BeautifulSoup) -> Optional[list[str]]:
        img_urls = []

        tag, attrs = SELECTORS["images"]
        img_elements = soup.find_all(tag, attrs=attrs)

        for img in img_elements:
            src = img.get("src")
            if src:
                match = _REGEX_IMAGE_SIZE.search(src)
                if match:
                    ext_match = _REGEX_IMAGE_EXT.search(match.group(0))
                    ext = ext_match.group(0) if ext_match else ".jpg"
                    high_res_src = _REGEX_IMAGE_SIZE.sub(ext, src)
                else:
                    high_res_src = src

                if high_res_src not in img_urls:
                    img_urls.append(high_res_src)

        if img_urls:
            logger.debug("Found %d image(s)", len(img_urls))
            return img_urls
        logger.warning("No product images found")
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

    # ----- review date and location -----
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

    # ----- product reviews -----
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
                review_title = (
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
                        review_title=review_title,
                        rating=rating,
                        review_body=review_body,
                        review_helpful=review_helpful,
                    )
                )
            except Exception as exc:
                logger.error("Failed to parse an individual review block: %s", exc)
                continue

        return reviews_list

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

    # ----- format of json and csv file for storing reviews -----
    @staticmethod
    def save_reviews(directory: str, asin: str) -> Tuple[str, str]:
        os.makedirs(directory, exist_ok=True)
        csv_path = os.path.join(directory, f"reviews_{asin}.csv")
        json_path = os.path.join(directory, f"reviews_{asin}.json")

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
            with open(json_path, mode="r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            logger.warning("JSON file missing or invalid; starting fresh: %s", json_path)
            data = []
        data.extend(reviews)
        with open(json_path, mode="w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logger.debug("Updated JSON with %d review(s): %s", len(reviews), json_path)

    # ----- automation tasks of playwright browser -----
    @staticmethod
    def scroll_page(page) -> None:
        for ratio in (0.4, 0.8, 1.0):
            page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {ratio});")
            time.sleep(_SCROLL_DELAY)

    # ----- find next page button in reviews page -----
    @staticmethod
    def find_next_page_selector(page) -> Optional[str]:
        for selector in _NEXT_PAGE_SELECTORS:
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

            review_title = Scraper.review_title(
                raw_title, f"{rating} out of 5 stars" if rating else ""
            )
            review_location, review_date = Scraper.review_date_location(raw_meta)

            sig = hash(f"{reviewer_name}_{review_date}_{review_title}_{rating}")
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
                    "review_title": review_title,
                    "review_body": review_body,
                    "review_helpful": helpful_votes,
                }
            )

        logger.debug("Parsed %d new review(s) from %d node(s)", len(reviews), len(nodes))
        return reviews, counter

    # ----- open playwrite browser for reviews -----
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
        csv_path, json_path = Scraper.save_reviews(OUTPUT_DIR, asin)
        logger.info("Initialized output files for ASIN: %s", asin)

        seen: set = set()
        total = 0
        page_num = 1

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                _SESSION_DIR,
                headless=_HEADLESS,
                user_agent=HEADERS["User-Agent"],
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()

            # ----- updated stealth application -----
            Stealth().apply_stealth_sync(page)

            page.goto(reviews_url, wait_until="domcontentloaded", timeout=60000)

            while True:
                logger.info("Scraping reviews page %d...", page_num)
                content = page.content()

                if "captcha" in content.lower() or "robot" in content.lower():
                    logger.warning(
                        "CAPTCHA detected. Resume process after %ds...",
                        _CAPTCHA_WAIT,
                    )
                    time.sleep(_CAPTCHA_WAIT)

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
                logger.info(
                    "Page %d: +%d reviews (running total: %d)",
                    page_num,
                    len(reviews),
                    total,
                )

                next_selector = Scraper.find_next_page_selector(page)
                if not next_selector:
                    logger.info(
                        "No further pages found. Scraping complete."
                    )
                    break

                page.locator(next_selector).scroll_into_view_if_needed()
                time.sleep(0.3)
                page.click(next_selector)
                page.wait_for_load_state("networkidle", timeout=20000)
                time.sleep(_PAGE_DELAY)
                page_num += 1

            context.close()

        logger.info("Done. %d reviews saved to '%s/'", total, OUTPUT_DIR)
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    async def scrape_reviews_playwright(self, url: str) -> list:
        return await asyncio.to_thread(Scraper.run_playwright_sync, url)

    # ----- output of product data -----
    @staticmethod
    def print_data(product: Product) -> None:
        print(json.dumps(product.to_dict(), ensure_ascii=False, indent=4))

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

    # ----- scraping data from the url -----
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