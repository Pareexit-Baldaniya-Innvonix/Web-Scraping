# ----- library import -----
import re
import os
import json
from sqlite3.dbapi2 import Timestamp
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from typing import Optional, Union

# ----- local import -----
from config.constants import HEADERS, OUTPUT_DIR
from config.selectors import SELECTORS
from .Product import Product
from utils.logger import get_logger

logger = get_logger("SCRAPER")


class Scraper:
    def __init__(self, url: str) -> None:
        self.url: str = url
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    # ----- url validation -----
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

            # ----- strip port number if present -----
            domain: str = parsed_url.netloc.lower()
            if ":" in domain:
                domain = domain.split(":")[0]

            # ----- only amazon.in and www.amazon.in domain accepted -----
            valid = domain == "amazon.in" or domain.endswith(".amazon.in")
            if not valid:
                logger.warning("Domain '%s' is not www.amazon.in", domain)
            else:
                logger.info("URL validated successfully")
            return valid

        except Exception as exc:
            logger.error("URL validation raised an exception: %s", exc, exc_info=True)
            return False

    # ----- scraping data from the url (core implementation) -----
    def scraping_data(self) -> Optional[Product]:
        logger.info("Scraping started.")

        try:
            # ----- getting response of the url -----
            response = self.session.get(self.url, timeout=10)
            response.raise_for_status()

            self.save_raw_response(response.text)

        except requests.RequestException as error:
            logger.error("Request error: %s", error, exc_info=True)
            return None

        soup = BeautifulSoup(response.content, "html.parser")

        # ----- fetch every field individually -----
        try:
            product = Product(
                title=self.title_details(soup),
                price=self.price_details(soup),
                ratings=self.ratings_details(soup),
                reviews=self.reviews_details(soup),
                description=self.description_details(soup),
                variants=self.variants_details(soup),
            )
            logger.info(
                "Product extracted | title='%s' price=%s ratings=%s reviews=%s",
                product.title[:60],
                product.price,
                product.ratings,
                product.reviews,
            )
            return product
        except Exception as exc:
            logger.error("Extraction failed: %s", exc, exc_info=True)
            return None

    # ----- saving response of URL as a html file -----
    def save_raw_response(self, html_content: str) -> None:
        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            file_path: str = os.path.join(OUTPUT_DIR, f"source.html")

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            logger.info("Raw HTML of the url saved successfully!")
        except OSError as e:
            logger.error("Failed to save HTML source: %s", e)

    # ----- product title -----
    def title_details(self, soup: BeautifulSoup) -> str:
        tag, attrs = SELECTORS["title"]
        title_tag = soup.find(tag, attrs=attrs)
        if title_tag:
            title = title_tag.get_text(strip=True)
            logger.debug("Title: %s", title)
            return title

        logger.warning("Title not found")
        return "N/A"

    # ----- product price -----
    def price_details(self, soup: BeautifulSoup) -> str:
        whole_tag = soup.find(*SELECTORS["price_whole"])
        fraction_tag = soup.find(*SELECTORS["price_fraction"])
        symbol_tag = soup.find(*SELECTORS["price_symbol"])

        if whole_tag:
            whole = whole_tag.get_text(strip=True)
            fraction = fraction_tag.get_text(strip=True) if fraction_tag else "00"
            symbol = symbol_tag.get_text(strip=True) if symbol_tag else "₹"

            price = f"{symbol}{whole}{fraction}"
            logger.debug("Price: %s", price)
            return price

        logger.warning("Price not found")
        return "N/A"

    # ----- product ratings -----
    def ratings_details(self, soup: BeautifulSoup) -> str:
        rating_selectors = [
            SELECTORS["ratings_popover"],
            SELECTORS["ratings_alt"],
        ]
        for tag, attrs in rating_selectors:
            ratings_tag = soup.find(tag, attrs=attrs)
            if ratings_tag:
                text = ratings_tag.get_text().strip()
                if text:
                    text = re.sub(r"^[\d.]+\s+(?=[\d.]+ out of)", "", text).strip()
                    logger.debug("Ratings: %s", text)
                    return text

        logger.warning("Ratings not found")
        return "N/A"

    # ----- product reviews -----
    def reviews_details(self, soup: BeautifulSoup) -> str:
        tag, attrs = SELECTORS["reviews_text"]
        element = soup.find(tag, attrs=attrs)
        if element:
            text = element.get_text(strip=True).strip("()")
            logger.debug("Reviews: %s", text)
            return text

        logger.warning("Review count not found")
        return "N/A"

    # ----- product description -----
    def description_details(self, soup: BeautifulSoup) -> dict[str, any]:
        # ----- product description block -----
        tag, attrs = SELECTORS["product_description"]
        for selector in [
            (tag, attrs),
            ("span", attrs),  # fallback: same id, span tag
        ]:
            el = soup.find(*selector)
            if el:
                text = el.get_text(strip=True)
                if text:
                    logger.debug("Description found via productDescription element")
                    return text

        # ----- getting all bullet points from description -----
        bullets_tag, bullets_attrs = SELECTORS["feature_bullets"]
        bullets = soup.find(bullets_tag, attrs=bullets_attrs)
        if bullets:
            items = [
                li.get_text().strip()
                for li in bullets.find_all("span", {"class": "a-list-item"})
            ]
            # ----- removes empty items -----
            items = [i for i in items if i and i.lower() != "about this item"]
            if items:
                logger.debug(
                    "Description found via feature-bullets (%d items)", len(items)
                )
                return items

        logger.warning("Description not found")
        return "N/A"

    # ----- all variants of the product -----
    def variants_details(self, soup: BeautifulSoup) -> list[dict]:
        variants = []

        # ----- container for all variant details -----
        container_tag, container_attrs = SELECTORS["variants_container"]
        container = soup.find(container_tag, attrs=container_attrs)
        if not container:
            logger.warning("Variants container not found")
            return variants

        # ----- Find all rows (Color, Size, Style, etc.) -----
        rows = container.find_all(
            "div", id=lambda x: x and x.startswith("inline-twister-row-")
        )

        for row in rows:
            variant_id = row.get("id", "")
            variant_label = (
                variant_id.replace("inline-twister-row-", "")
                .replace("_name", "")
                .capitalize()
            )

            options = []
            for li in row.find_all("li"):
                li_title = li.get("title", "").strip()
                img = li.find("img")
                img_alt = (img.get("alt") or "").strip() if img else ""

                raw = li_title or img_alt or li.get_text().strip()

                if raw and not re.fullmatch(r"[←→‹›<>\d]+", raw):
                    options.append(raw)

            variants.append(
                {
                    "type": variant_label,
                    "options": options,
                }
            )

            logger.debug(
                "Variant=%s, options=%s",
                variant_label,
                options,
            )

        logger.info("Variants extracted: %d group(s)", len(variants))
        return variants

    # ----- save data into specific file -----
    @staticmethod
    def save_data(product: Product) -> None:
        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            filename: str = os.path.join(OUTPUT_DIR, "product.json")
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(product.to_dict(), f, ensure_ascii=False, indent=4)
            logger.info("Data saved successfully.")
        except OSError as exc:
            logger.error("Failed to save data: %s", exc, exc_info=True)
            raise