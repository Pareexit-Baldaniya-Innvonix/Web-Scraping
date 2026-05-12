# ----- library import -----
import time
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse

# ----- local import -----
from src.utils.logger import setup_logging, get_logger
from src.classes.ScrapeFailReason import ScrapeFailReason
from src.classes.ScrapeRequest import ScrapeRequest
from src.classes.Scraper import Scraper

setup_logging()
logger = get_logger("MAIN")

app = FastAPI(title="Amazon Web-Scraper", version="1.0.0")


# ----- routes -----
@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(
        content="""
    <html>
        <body style="text-align: center">
            <h2>Amazon Web-Scraper</h2>
            <p>Welcome to home page!!</p>
        </body>
    </html>
    """,
        media_type="text/html; charset=utf-8",
    )


@app.post("/api/scrape", response_class=JSONResponse)
async def scrape_product(body: ScrapeRequest):
    url = Scraper.normalize_url(body.url.strip())
    logger.info("Received scrape request for URL: %s", url)

    # ----- validate amazon url -----
    if not Scraper.check_amazon_url(url):
        logger.warning("Invalid Amazon URL: %s", url)
        raise HTTPException(
            status_code=400,
            detail="Oops... Invalid URL. It must be from https and amazon.in",
        )

    # ----- scrape product -----
    scraper = Scraper(url)
    t0 = time.perf_counter()
    result = scraper.scraping_data()
    elapsed = time.perf_counter() - t0

    # ----- Handle Result -----
    if not result.success:
        status_code = 500
        if result.reason == ScrapeFailReason.BLOCKED:
            status_code = 503
        elif result.reason == ScrapeFailReason.NETWORK_ERROR:
            status_code = 502

        raise HTTPException(status_code=status_code, detail=result.detail)

    logger.info("Scraping completed in %.2fs", elapsed)
    return JSONResponse(content=result.product.to_dict())
