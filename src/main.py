# ----- library import -----
import asyncio
import logging
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# ----- local imports -----
from src.classes.PollingEndpointAccessFilter import PollingEndpointAccessFilter
from src.classes.OtpChoiceRequest import OtpChoiceRequest
from src.classes.OtpManager import OtpManager
from src.classes.OtpRequest import OtpRequest
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

logging.getLogger("uvicorn.access").addFilter(PollingEndpointAccessFilter())

app = FastAPI(title="Amazon Web-Scraper", version="1.0.0")

# ----- active task registry -----
_active_tasks: dict[str, asyncio.Task] = {}

# ----- otp long-poll timing -----
OTP_LONG_POLL_TIMEOUT = 25.0
OTP_LONG_POLL_INTERVAL = 0.5

# ----- mount static asset directories -----
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    logger.warning(
        "Static files directory not found at '%s'. Dashboard styles may break.",
        STATIC_DIR,
    )


async def _run_cancellable(task_key: str, coro, request: Request):
    task = asyncio.ensure_future(coro)
    _active_tasks[task_key] = task
    logger.debug("Task initialized with key: %s", task_key)

    try:
        while not task.done():
            # ----- poll for client disconnect -----
            if await request.is_disconnected():
                logger.warning(
                    "Client connection closed unexpectedly. Aborting active task: %s",
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
        logger.warning("Task execution aborted by explicit cancellation.")
        task.cancel()
        raise HTTPException(
            status_code=499,
            detail="Task successfully aborted on user request.",
        )
    finally:
        _active_tasks.pop(task_key, None)
        logger.debug("Task cleared from execution queue: %s", task_key)


# ----- base route -----
@app.get("/", response_class=HTMLResponse)
async def root():
    html_file = TEMPLATES_DIR / "index.html"
    if html_file.exists():
        return FileResponse(html_file)

    logger.error("Dashboard index UI template asset missing at: %s", html_file)
    return HTMLResponse(
        content="<h1>Scraper Dashboard</h1><p>UI template missing or corrupted.</p>",
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
    logger.info("Received request to search product: '%s'", q)

    existing = _active_tasks.get(task_key)
    if existing and not existing.done():
        logger.warning(
            "Search task already active for query '%s'. Cancelling existing task.",
            q,
        )
        existing.cancel()

    scraper = Scraper("https://www.amazon.in")

    try:
        search_result = await _run_cancellable(
            task_key,
            scraper.run_search_playwright(q),
            request,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Product search task failed due to a processing error.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete marketplace search.",
        )

    return JSONResponse(content=search_result)


# ----- product scraping route -----
@app.post("/api/scrape")
async def scrape_product(body: ScrapeRequest, request: Request):
    url = Scraper.normalize_url(body.url.strip())
    task_key = f"scrape:{url}"
    logger.info("Received metadata extraction request for product URL: %s", url)

    if not Scraper.check_amazon_url(url):
        logger.warning("Invalid target URL rejected: %s", url)
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
            "Unexpected error while running single item scraping routine: %s", exc
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
            "Scraping halted after %.2fs (Status: %d, Reason: %s): %s",
            elapsed,
            status_code,
            result.reason,
            result.detail,
        )
        raise HTTPException(status_code=status_code, detail=result.detail)

    logger.info("Product data parsed and mapped in %.2fs.", elapsed)
    return JSONResponse(content=result.product.to_dict())


# ----- product reviews route -----
@app.post("/api/scrape/reviews")
async def scrape_reviews(body: ScrapeRequest, request: Request):
    url = Scraper.normalize_url(body.url.strip())
    task_key = f"reviews:{url}"
    logger.info("Received reviews extraction request for URL: %s", url)

    if not Scraper.check_amazon_url(url):
        logger.warning("Invalid review URL rejected: %s", url)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Oops... Invalid URL. It must be from https and amazon.in",
        )

    scraper = Scraper(url)

    try:
        reviews = await _run_cancellable(
            task_key,
            scraper.run_reviews_playwright(url),
            request,
        )
    except HTTPException:
        raise
    except RuntimeError as exc:
        logger.error("Scraping halted by internal pipeline error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
    except Exception:
        logger.exception("Playwright reviews pagination crashed unexpectedly.")
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


# ----- otp status long-poll endpoint -----
@app.get("/api/otp/status")
async def otp_status(request: Request):
    elapsed = 0.0
    initial_waiting = OtpManager.is_waiting()
    while elapsed < OTP_LONG_POLL_TIMEOUT:
        if OtpManager.is_waiting() != initial_waiting:
            break
        if await request.is_disconnected():
            break
        await asyncio.sleep(OTP_LONG_POLL_INTERVAL)
        elapsed += OTP_LONG_POLL_INTERVAL

    return JSONResponse(
        content={"waiting": OtpManager.is_waiting(), "error": OtpManager.get_error()}
    )


# ----- otp submission endpoint -----
@app.post("/api/otp/submit")
async def otp_submit(body: OtpRequest):
    otp = body.otp.strip()
    logger.info("Received OTP code submission from dashboard.")

    accepted = OtpManager.submit_otp(otp)
    if not accepted:
        logger.warning("OTP submission rejected; no active OTP request found.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active OTP request found. The login step may have already timed out or completed.",
        )

    return JSONResponse(content={"submitted": True})


# ----- otp delivery-method choice long-poll endpoint -----
@app.get("/api/otp/choice/status")
async def otp_choice_status(request: Request):
    elapsed = 0.0
    initial_waiting = OtpManager.is_choice_waiting()
    while elapsed < OTP_LONG_POLL_TIMEOUT:
        if OtpManager.is_choice_waiting() != initial_waiting:
            break
        if await request.is_disconnected():
            break
        await asyncio.sleep(OTP_LONG_POLL_INTERVAL)
        elapsed += OTP_LONG_POLL_INTERVAL

    return JSONResponse(
        content={
            "waiting": OtpManager.is_choice_waiting(),
            "options": OtpManager.get_choice_options(),
        }
    )


# ----- otp delivery-method choice submission endpoint -----
@app.post("/api/otp/choice/submit")
async def otp_choice_submit(body: OtpChoiceRequest):
    choice = body.choice.strip()
    logger.info("Received OTP delivery method selection: %s", choice)

    accepted = OtpManager.submit_choice(choice)
    if not accepted:
        logger.warning("OTP choice submission rejected; no waiting choice request was active.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active OTP delivery-method request found, or the submitted option was invalid.",
        )

    return JSONResponse(content={"submitted": True})


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
            "Task cancellation requested, but no matching task was found for key: %s",
            task_key,
        )
        raise HTTPException(
            status_code=404,
            detail=f"No active task found matching key: {task_key}",
        )

    task.cancel()
    logger.info("Active task explicitly cancelled by user: %s", task_key)
    return JSONResponse(content={"cancelled": True, "task_key": task_key})