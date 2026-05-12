# ----- library import -----
import time
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse

# ----- local import -----
from src.classes.ScrapeRequest import ScrapeRequest
from src.utils.logger import setup_logging, get_logger
from src.classes.Scraper import Scraper
from src.classes.Product import Product

setup_logging()
logger = get_logger("MAIN")

app = FastAPI(title="Amazon Web-Scraper", version="1.0.0")


# ----- routes -----
@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <html>
        <body style="text-align: center">
            <h2>Amazon Web-Scraper</h2>
            <p>Welcome to home page!!</p>
        </body>
    </html>
    """


@app.post("/api/scrape", response_class=JSONResponse)
async def scrape_product(body: ScrapeRequest):
    url = body.url.strip()
    logger.info("Received scrape request for URL: %s", url)

    # ----- validate amazon url -----
    if not Scraper.check_amazon_url(url):
        logger.warning("Invalid Amazon URL: %s", url)
        raise HTTPException(
            status_code=400, detail="Oops... Invalid URL. It must be from amazon.in"
        )

    # ----- scrape product -----
    scraper = Scraper(url)

    t0: float = time.perf_counter()

    try:
        product: Product | None = scraper.scraping_data()
    except Exception as e:
        logger.error("Internal scraper error %s, %s", url, str(e))
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occured while processing the request.",
        )

    elapsed: float = time.perf_counter() - t0

    if not product:
        logger.error("Scraping failed for URL: %s (%.2fs)", url, elapsed)
        raise HTTPException(
            status_code=422,
            detail="Failed to extract product data. The page may be blocked or the URL is unsupported.",
        )

    logger.info("Scraping completed in %.2fs", elapsed)
    return JSONResponse(content=product.to_dict())
