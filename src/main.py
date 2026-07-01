# ----- library import -----
import asyncio
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
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

# ----- active task registry  -----
_active_tasks: dict[str, asyncio.Task] = {}

# ----- mount static asset directories -----
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    logger.warning(
        "Static files root route path directory not found at target tracking path location '%s'. Layout graphics elements might break in dashboard view.",
        STATIC_DIR,
    )


async def _run_cancellable(task_key: str, coro, request: Request):
    task = asyncio.ensure_future(coro)
    _active_tasks[task_key] = task
    logger.debug("Task_key: %s", task_key)

    try:
        while not task.done():
            # ----- poll for client disconnect -----
            if await request.is_disconnected():
                logger.warning(
                    "Active socket connection channel closed by peer connection. Request key task aborted: %s",
                    task_key,
                )
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                raise HTTPException(
                    status_code=499,
                    detail="Request cancelled by client connection drop.",
                )
            await asyncio.sleep(0.5)

        return task.result()

    except asyncio.CancelledError:
        logger.warning(
            "Active task received an explicit cancellation loop command."
        )
        task.cancel()
        raise HTTPException(
            status_code=499,
            detail="Task successfully aborted on user request.",
        )
    finally:
        _active_tasks.pop(task_key, None)
        logger.debug("Task completed of task_key: %s", task_key)


# ----- base route -----
@app.get("/", response_class=HTMLResponse)
async def root():
    html_file = TEMPLATES_DIR / "index.html"
    if html_file.exists():
        return FileResponse(html_file)

    logger.error(
        "Dashboard UI static assembly framework index template asset is missing at: %s",
        html_file,
    )
    return HTMLResponse(
        content="<h1>Scraper Dashboard</h1><p>UI target component missing or corrupted inside path structure locations.</p>",
        status_code=status.HTTP_404_NOT_FOUND,
    )


# ----- list active tasks -----
@app.get("/api/tasks")
async def list_tasks():
    return JSONResponse(
        content={"active_tasks": [k for k, t in _active_tasks.items() if not t.done()]}
    )


# ----- product search route -----
@app.post("/api/search")
async def search_products(body: SearchRequest, request: Request):
    q = body.query.strip()
    task_key = f"search:{q}"
    logger.info("Received request to search: '%s'", q)

    existing = _active_tasks.get(task_key)
    if existing and not existing.done():
        logger.warning(
            "Identical search execution worker process already active for tracking key '%s' — Killing concurrent process context to start fresh query chain execution.",
            q,
        )
        existing.cancel()

    scraper = Scraper("https://www.amazon.in")
    t0 = time.perf_counter()

    try:
        search_result = await _run_cancellable(
            task_key,
            scraper.run_search_playwright(q),
            request,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Task canceled by the user."
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete structural marketplace search extraction synchronously.",
        )

    return JSONResponse(content=search_result)


# ----- product scraping route -----
@app.post("/api/scrape")
async def scrape_product(body: ScrapeRequest, request: Request):
    url = Scraper.normalize_url(body.url.strip())
    task_key = f"scrape:{url}"
    logger.info(
        "Received direct asset metadata extraction target assignment request for URL path footprint: %s",
        url,
    )

    if not Scraper.check_amazon_url(url):
        logger.warning(
            "Target parameter check failure — Invalid marketplace origin drop: %s", url
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Oops... Invalid URL. It must be from https and amazon.in",
        )

    scraper = Scraper(url)
    t0 = time.perf_counter()

    try:
        result = await _run_cancellable(
            task_key,
            scraper.scraping_data(),
            request,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Unexpected structural runtime fault during scraping process layout loop execution step: %s",
            str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during execution.",
        )

    elapsed = time.perf_counter() - t0

    if not result.success:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        if result.reason == ScrapeFailReason.BLOCKED:
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        elif result.reason == ScrapeFailReason.NETWORK_ERROR:
            status_code = status.HTTP_502_BAD_GATEWAY

        logger.error(
            "Scraping routine dropped execution cycle following processing delay of %.2fs. Error layout mapping -> HTTP Status: %d, Engine Reason Code: %s, Diagnostic string: %s",
            elapsed,
            status_code,
            result.reason,
            result.detail,
        )
        raise HTTPException(status_code=status_code, detail=result.detail)

    logger.info(
        "Single item element structure parsed and mapped down into domain objects completely in %.2fs",
        elapsed,
    )
    return JSONResponse(content=result.product.to_dict())


# ----- product reviews route -----
@app.post("/api/scrape/reviews")
async def scrape_reviews(body: ScrapeRequest, request: Request):
    url = Scraper.normalize_url(body.url.strip())
    task_key = f"reviews:{url}"
    logger.info(
        "Received reviews request for URL: %s",
        url,
    )

    if not Scraper.check_amazon_url(url):
        logger.warning(
            "Target validation baseline logic verification crash — Rejected unauthorized remote host location parameter domain context query for reviews pipeline: %s",
            url,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Oops... Invalid URL. It must be from https and amazon.in",
        )

    scraper = Scraper(url)
    t0 = time.perf_counter()

    try:
        reviews = await _run_cancellable(
            task_key,
            scraper.run_reviews_playwright(url),
            request,
        )
    except HTTPException:
        raise
    except RuntimeError as exc:
        logger.error("Scraping execution halted by internal execution error: %s", str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scraping context suspended: {str(exc)}"
        )
    except Exception as exc:
        logger.exception(
            "Playwright async pagination engine driver raised an unhandled tracking operation crash exception: %s",
            str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to extract reviews dynamically.",
        )

    asin = Scraper.extract_asin(url)

    return JSONResponse(
        content={
            "asin": asin,
            "reviews_count": len(reviews),
            "reviews": reviews,
        }
    )


# ----- explicit cancel endpoint -----
@app.post("/api/cancel/{task_key:path}")
async def cancel_task(task_key: str):
    task_key = task_key.strip('"').strip("'")

    if ":" in task_key:
        prefix, url_part = task_key.split(":", 1)
        if prefix in ("scrape", "reviews"):
            normalized_url = Scraper.normalize_url(url_part.strip('"'))
            task_key = f"{prefix}:{normalized_url}"
        elif prefix == "search":
            task_key = f"search:{url_part.strip()}"

    task = _active_tasks.get(task_key)
    if task is None or task.done():
        logger.warning(
            "API termination dispatch command rejected — No matching background execution context found for key: %s",
            task_key,
        )
        raise HTTPException(
            status_code=(
                status.HTTP_444_RESPONSE_VALUE_MISSING
                if hasattr(status, "HTTP_444_RESPONSE_VALUE_MISSING")
                else status.HTTP_404_NOT_FOUND
            ),
            detail=f"No active task found matching target contextual identifier: {task_key}",
        )

    task.cancel()
    logger.info(
        "Active operation context killed explicitly by cancel request: %s",
        task_key,
    )
    return JSONResponse(content={"cancelled": True, "task_key": task_key})
