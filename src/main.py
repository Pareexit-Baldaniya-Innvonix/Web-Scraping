# ----- library import -----
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# ----- local imports -----
from src.classes.ScrapeFailReason import ScrapeFailReason
from src.classes.ScrapeRequest import ScrapeRequest
from src.classes.Scraper import Scraper
from src.classes.SearchRequest import SearchRequest
from src.utils.logger import get_logger, setup_logging

# ----- path configurations -----
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# ----- initialize logging system -----
setup_logging()
logger = get_logger("MAIN")

app = FastAPI(title="Amazon Web-Scraper", version="1.0.0")

# ----- mount static asset directories -----
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    logger.warning(
        "Static directory not found at %s. UI might look broken.", STATIC_DIR
    )


# ----- base route -----
@app.get("/", response_class=HTMLResponse)
async def root():
    html_file = TEMPLATES_DIR / "index.html"
    if html_file.exists():
        return FileResponse(html_file)

    logger.error("UI Dashboard file missing at expected path: %s", html_file)
    return HTMLResponse(
        content="<h1>Scraper Dashboard</h1><p>UI file not found</p>",
        status_code=status.HTTP_404_NOT_FOUND,
    )


# ----- product search route -----
@app.post("/api/search")
async def search_products(body: SearchRequest):
    q = body.query.strip()
    logger.info("Received catalog search request for query: '%s'", q)

    scraper = Scraper("https://www.amazon.in")
    t0 = time.perf_counter()

    try:
        products = await scraper.scrape_search_playwright(q)
    except Exception as exc:
        logger.exception(
            "Playwright search operation encountered a critical failure: %s", str(exc)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete structural marketplace search extraction synchronously.",
        )

    elapsed = time.perf_counter() - t0
    logger.info(
        "Total %d entries saved for [Product: %s] in %.2fs",
        len(products),
        q,
        elapsed,
    )

    return JSONResponse(content={"products": products})


# ----- product scraping route -----
@app.post("/api/scrape")
async def scrape_product(body: ScrapeRequest):
    url = Scraper.normalize_url(body.url.strip())
    logger.info("Received scrape request for URL: %s", url)

    # ----- validate amazon url -----
    if not Scraper.check_amazon_url(url):
        logger.warning("Validation failed — Invalid Amazon URL dropped: %s", url)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Oops... Invalid URL. It must be from https and amazon.in",
        )

    # ----- scrape product -----
    scraper = Scraper(url)
    t0 = time.perf_counter()

    try:
        result = await scraper.scraping_data()
    except Exception as exc:
        logger.exception(
            "Unexpected structural crash during scraping execution: %s", str(exc)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during execution.",
        )

    elapsed = time.perf_counter() - t0

    # ----- handle result -----
    if not result.success:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        if result.reason == ScrapeFailReason.BLOCKED:
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        elif result.reason == ScrapeFailReason.NETWORK_ERROR:
            status_code = status.HTTP_502_BAD_GATEWAY

        logger.error(
            "Scraping failed after %.2fs. Status: %d, Reason: %s, Detail: %s",
            elapsed,
            status_code,
            result.reason,
            result.detail,
        )
        raise HTTPException(status_code=status_code, detail=result.detail)

    logger.info("Scraping completed successfully in %.2fs", elapsed)
    return JSONResponse(content=result.product.to_dict())


# ----- product reviews route -----
@app.post("/api/scrape/reviews")
async def scrape_reviews(body: ScrapeRequest):
    url = Scraper.normalize_url(body.url.strip())
    logger.info("Received reviews scrape request for URL: %s", url)

    # ----- validate amazon url -----
    if not Scraper.check_amazon_url(url):
        logger.warning(
            "Validation failed — Invalid Amazon URL dropped for reviews: %s", url
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Oops... Invalid URL. It must be from https and amazon.in",
        )

    scraper = Scraper(url)
    t0 = time.perf_counter()

    try:
        reviews = await scraper.scrape_reviews_playwright(url)
    except Exception as exc:
        logger.exception(
            "Playwright review scraper raised an unhandled exception: %s", str(exc)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to extract reviews dynamically.",
        )

    elapsed = time.perf_counter() - t0
    asin = Scraper.extract_asin(url)

    logger.info(
        "Review scraping completed in %.2fs — Extracted %d reviews for ASIN: %s",
        elapsed,
        len(reviews),
        asin,
    )

    return JSONResponse(
        content={
            "asin": asin,
            "reviews_count": len(reviews),
            "reviews": reviews,
        }
    )
