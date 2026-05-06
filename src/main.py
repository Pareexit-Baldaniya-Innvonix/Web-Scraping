# ----- library import -----
import time

# ----- local import -----
from utils.logger import setup_logging, get_logger
from classes.Scraper import Scraper
from classes.Product import Product

setup_logging()
logger = get_logger("MAIN")


def main() -> None:
    logger.info("Application started.")

    try:
        # ----- taking input of the amazon product using URL -----
        product_url: str = input("Enter any amazon product link: ").strip()
        logger.debug("Product URL fetched successfully!")

        # ----- validation of the url -----
        if not Scraper.check_amazon_url(product_url):
            logger.error("Invalid link.")
            return

        # ----- scraping -----
        scraper = Scraper(product_url)

        t0: float = time.perf_counter()
        product: Product | None = scraper.scraping_data()
        elapsed: float = time.perf_counter() - t0

        # ----- check scraping is completed or not. -----
        if product:
            logger.info("Scraping completed in %.2fs", elapsed)
            scraper.save_data(product)
        else:
            logger.error("Scraping failed after %.2fs", elapsed)
    except Exception:
        logger.error("An unexpected error occurred.")


if __name__ == "__main__":
    main()
