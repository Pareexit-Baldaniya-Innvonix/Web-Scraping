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
from src.config.constants import HEADERS, OUTPUT_DIR
from src.config.selectors import SELECTORS
from .Product import Product
from src.utils.logger import get_logger

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
                reviews_count=self.reviews_count(soup),
                description=self.description_details(soup),
                variants=self.variants_details(soup),
            )
            logger.info(
                "Product extracted | title='%s' price=%s ratings=%s reviews_count=%s",
                product.title[:60],
                product.price,
                product.ratings,
                product.reviews_count,
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
    def price_details(self, soup: BeautifulSoup) -> Optional[float]:
        core_block = soup.find("div", id="corePriceDisplay_desktop_feature_div")
        search_root = core_block if core_block else soup

        price_span = search_root.find("span", {"class": "priceToPay"})
        scoped_root = price_span if price_span else search_root

        whole_tag = scoped_root.find("span", {"class": "a-price-whole"})
        fraction_tag = scoped_root.find("span", {"class": "a-price-fraction"})

        if not whole_tag:
            logger.warning("Price not found")
            return None

        whole = (
            whole_tag.get_text(strip=True)
            .replace(",", "")
            .replace("₹", "")
            .rstrip(".")
            .strip()
        )

        if not whole.isdigit():
            logger.warning("Unexpected whole-price value after cleaning: '%s'", whole)
            return None

        fraction = fraction_tag.get_text(strip=True) if fraction_tag else "00"
        fraction = fraction.ljust(2, "0")[:2]

        if not fraction.isdigit():
            logger.warning("Unexpected fraction value after cleaning: '%s'", fraction)
            fraction = "00"

        try:
            price = float(f"{whole}.{fraction}")
            logger.debug("Price: %s", price)
            return price
        except ValueError:
            logger.warning("Could not convert price to float: %s.%s", whole, fraction)
            return None

    # ----- product ratings -----
    def ratings_details(self, soup: BeautifulSoup) -> float:
        rating_selectors = [
            SELECTORS["ratings_popover"],
            SELECTORS["ratings_alt"],
        ]
        for tag, attrs in rating_selectors:
            ratings_tag = soup.find(tag, attrs=attrs)
            if ratings_tag:
                text = ratings_tag.get_text().strip()
                if text:
                    match = re.match(r"([\d.]+)", text)
                    if match:
                        try:
                            rating = float(match.group(1))
                            logger.debug("Rating: %s", rating)
                            return rating
                        except ValueError:
                            logger.warning(
                                "Could not parse rating float from: %s", text
                            )

        logger.warning("Rating not found")
        return None

    # ----- product reviews -----
    def reviews_count(self, soup: BeautifulSoup) -> Optional[int]:
        tag, attrs = SELECTORS["reviews_text"]
        element = soup.find(tag, attrs=attrs)
        if element:
            raw = element.get_text(strip=True).strip("()")
            cleaned = raw.replace(",", "")
            try:
                count = int(cleaned)
                logger.debug("Reviews count: %s", count)
                return count
            except ValueError:
                logger.warning("Could not convert review count to int: %s", raw)
                return None

        logger.warning("Review count not found")
        return None

    # ----- product description -----
    def description_details(self, soup: BeautifulSoup) -> str:
        tag, attrs = SELECTORS["product_description"]
        for selector in [(tag, attrs), ("span", attrs)]:
            el = soup.find(*selector)
            if el:
                text = " ".join(el.get_text(strip=True).split())
                if text:
                    logger.debug("Description found via productDescription element")
                    return text

        bullets_tag, bullets_attrs = SELECTORS["feature_bullets"]
        bullets = soup.find(bullets_tag, attrs=bullets_attrs)
        if bullets:
            items = [
                " ".join(li.get_text().strip().split())
                for li in bullets.find_all("span", {"class": "a-list-item"})
            ]
            items = [i for i in items if i and i.lower() != "about this item"]
            if items:
                description = " ".join(items)
                logger.debug(
                    "Description built from feature-bullets (%d items)", len(items)
                )
                return description

        logger.warning("Description not found")
        return "N/A"

    # ----- all variants of the product -----
    def variants_details(self, soup: BeautifulSoup) -> Optional[list[dict]]:
        variants = []

        # ----- build a lookup from the a-state JSON (reliable fallback) -----
        json_dim_options = {}
        for tag in soup.find_all("script", {"type": "a-state"}):
            state_attr = tag.get("data-a-state", "")
            if "desktop-twister-sort-filter-data" in state_attr:
                try:
                    data = json.loads(tag.string)
                    dims = data.get("sortedDimValuesForAllDims", {})
                    for dim_key, values in dims.items():
                        json_dim_options[dim_key] = [
                            v.get("dimensionValueDisplayText", "").strip()
                            for v in values
                            if v.get("dimensionValueDisplayText", "").strip()
                        ]
                except Exception as exc:
                    logger.warning("Failed to parse twister a-state JSON: %s", exc)
                break

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
            row_id = row.get("id", "")
            dim_key = row_id.replace("inline-twister-row-", "")
            # strip _name suffix, replace remaining underscores with spaces
            variant_label = dim_key.replace("_name", "").replace("_", " ").title()

            options = []
            for li in row.find_all("li"):
                # priority 1: title attribute
                raw = li.get("title", "").strip()

                # priority 2: img alt text (image swatches)
                if not raw:
                    img = li.find("img")
                    raw = (img.get("alt") or "").strip() if img else ""

                # priority 3: swatch-title-text-display span (text swatches)
                if not raw:
                    swatch_span = li.find(
                        "span", {"class": "swatch-title-text-display"}
                    )
                    if swatch_span:
                        raw = swatch_span.get_text(strip=True)

                # priority 4: full li text
                if not raw:
                    raw = li.get_text(strip=True)

                if raw and not re.fullmatch(r"[←→‹›<>\d\s]+", raw):
                    if raw not in options:
                        options.append(raw)

            # priority 5: fall back to a-state JSON for this dimension
            if not options and dim_key in json_dim_options:
                options = json_dim_options[dim_key]
                logger.debug(
                    "Variant=%s options sourced from a-state JSON", variant_label
                )

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

    # ----- save data into stdout -----
    @staticmethod
    def print_data(product: Product) -> None:
        print(json.dumps(product.to_dict(), ensure_ascii=False, indent=4))
