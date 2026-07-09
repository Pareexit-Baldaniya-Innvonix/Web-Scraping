# 🛒 Amazon Product Scraper

A Python-based web scraper that extracts product details from Amazon India (`amazon.in`) — including title, images, price, ratings, reviews, description, and variants — and exposes the results via a **FastAPI REST API** with a built-in web dashboard UI.

---

## 📁 Project Structure

```
WEB-SCRAPING/
├── logs/
│   └── scraper.log              # Log file output (auto-generated)
├── output/
│   ├── source.html              # Raw HTML of the last /api/scrape response, for debugging (auto-generated, overwritten every scrape)
│   ├── reviews/
│   │   ├── reviews_{ASIN}.csv   # Paginated reviews exported as CSV (auto-generated)
│   │   └── reviews_{ASIN}.json  # Paginated reviews exported as JSON (auto-generated)
│   └── searches/
│       └── search_{query}.json  # Search results exported as JSON (auto-generated)
├── src/
│   ├── amazon_user_session/     # Persistent Chromium user-data-dir for the shared Playwright context (auto-generated, git-ignored — see note below)
│   │   └── Default/             # Standard Chromium profile data written here by Playwright: Cookies, Cache, Local Storage, Session Storage, Service Worker, etc.
│   ├── classes/
│   │   ├── BrowserManager.py            # Shared, process-lifetime Chromium browser/context singleton
│   │   ├── OtpChoiceRequest.py          # Pydantic body model for the OTP delivery-method popup
│   │   ├── OtpManager.py                # Async future-based bridge between the login flow and the dashboard OTP popup
│   │   ├── OtpRequest.py                # Pydantic body model for OTP code submission
│   │   ├── PollingEndpointAccessFilter.py # Logging filter that silences noisy OTP-poller access logs
│   │   ├── Product.py                   # Pydantic product model
│   │   ├── Review.py                    # Pydantic review model
│   │   ├── Scraper.py                   # Core scraping logic (requests + Playwright)
│   │   ├── ScrapeFailReason.py          # Enum for scrape failure categories
│   │   ├── ScrapeRequest.py             # Pydantic request body model
│   │   ├── ScrapeResult.py              # Pydantic result wrapper model
│   │   ├── SearchRequest.py             # Pydantic search request body model
│   │   ├── SearchResult.py              # Pydantic search result model
│   │   └── Settings.py                  # Environment-based settings (pydantic-settings)
│   ├── config/
│   │   ├── constants.py         # HTTP headers, cookies & directory constants
│   │   └── selectors.py         # BeautifulSoup CSS selectors
│   ├── static/
│   │   └── favicon.png          # Dashboard favicon
│   ├── templates/
│   │   └── index.html           # Web dashboard UI (TailwindCSS + glassmorphism)
│   ├── utils/
│   │   └── logger.py            # Centralized logging setup
│   └── main.py                  # FastAPI app entry point (top-level module inside src/)
├── .dockerignore                # Files excluded from the Docker build context
├── .env                         # Local environment variables (git-ignored)
├── .gitignore
├── docker-compose.yml           # One-command container orchestration (build, ports, volumes)
├── Dockerfile                   # Container image definition (Python 3.12 + Playwright/Chromium)
├── example.env                  # Example env file for reference
├── Pipfile                      # Pipenv dependency manifest
├── Pipfile.lock                 # Locked dependency versions
└── README.md
```

---

## ✨ Features

- Validates that the URL belongs to `amazon.in` (http/https scheme, correct domain)
- Automatically normalizes URLs — strips query parameters and ensures the `www.` subdomain
- Scrapes the following product fields:
  - **Title**
  - **Images** (full list of high-resolution CDN URLs, upgraded from thumbnail size)
  - **Price** (integer part + fraction, cleaned and parsed as float)
  - **Ratings** (out of 5)
  - **Ratings count**
  - **Description** (feature bullet points preferred; falls back to product description paragraph)
  - **Variants** (Color, Size, Style, etc.) — multi-strategy extraction with `a-state` JSON fallback

> **Note:** `Scraper` also has a `reviews_details()` helper capable of parsing on-page reviews from a product's own listing, but it is not currently wired into `scraping_data()` / `/api/scrape`, so product-page scrapes do **not** include a `reviews` field. Use the dedicated `/api/scrape/reviews` endpoint (Playwright-driven, paginated) to collect reviews for a product.

- **Search Products** powered by Playwright — searches Amazon by keyword and paginates by clicking "Next" until no further page is found or the `THRESHOLD_LIMIT` item cap is reached, deduplicating results by ASIN and saving output to `output/searches/search_{query}.json`. Each search result includes product title, price, direct product link, and estimated delivery days.

- **Product Reviews** powered by Playwright — paginates through review pages until no further page is found or `THRESHOLD_LIMIT` reviews have been collected, detects CAPTCHAs and waits for manual resolution, deduplicates reviews across pages, and saves results to `output/reviews/reviews_{ASIN}.csv` and `output/reviews/reviews_{ASIN}.json`

- **Automatic Amazon sign-in** — if credentials are provided via `.env`, the scraper detects login/OTP pages and handles authentication automatically before resuming scraping. Supports both email+password and password-only flows, and pauses for OTP/MFA resolution if required.

- **Shared, disk-persisted Playwright browser context** — `BrowserManager` launches a single Chromium context the first time it's needed, via Playwright's `launch_persistent_context(user_data_dir=SESSION_DIR)` (`SESSION_DIR` = `src/amazon_user_session/`), and reuses that same context for every subsequent search and reviews run for the lifetime of the running server process. Because the profile is a real Chromium user-data directory rather than an in-memory session, cookies and login state are written straight to disk as they change — so a successful sign-in survives not just later requests within the same run, but also a server restart, as long as `amazon_user_session/` isn't deleted (in Docker, this directory is a mounted volume, so it also survives container restarts/rebuilds — see [🐳 Docker](#-docker)). If the context is closed unexpectedly, `BrowserManager` resets its internal state so the next request transparently relaunches it from the same on-disk profile.

- **Atomic search file writes** — search progress is first written to a `.tmp` file and then atomically replaced, preventing partial or corrupt output on interruption.
- Saves the raw HTML of the most recent `/api/scrape` response for debugging (`output/source.html`, overwritten on every scrape)
- Environment-aware logging — JSON logs in production, human-readable standard format in development
- Named loggers per module for clean, traceable log output
- REST API with FastAPI — interactive Swagger docs available at `/docs`

- **Built-in web dashboard** at `/`:
  - Glassmorphism dark UI (TailwindCSS + Font Awesome icons)

  - Three scrape modes toggled from the UI: **Product Details**, **Search Products**, and **Product Reviews**

  - Animated laser-beam loading indicator and skeleton screen while scraping

  - Syntax-highlighted JSON output (color-coded keys, strings, numbers, booleans)

  - Clickable image URLs open in a full image preview modal

  - **Download CSV** button for paginated review results
  
  - **Cancel Task** button to abort an in-progress scrape/search/reviews run directly from the UI

- **Cancellable background tasks** — every request (`/api/scrape`, `/api/search`, `/api/scrape/reviews`) runs as an `asyncio` task tracked in an in-memory registry keyed by `{mode}:{normalized_url_or_query}`. Tasks can be cancelled explicitly via `POST /api/cancel/{task_key}`, are automatically cancelled if the client disconnects mid-request (polled every 0.5s), and starting an identical request while one is already running cancels the previous run before starting fresh.

---

## 🔧 Requirements

- Python 3.12
- [Pipenv](https://pipenv.pypa.io/en/latest/)

### Dependencies (from `Pipfile`)

| Package | Purpose |
|---|---|
| `requests` | HTTP requests for product page scraping |
| `beautifulsoup4` | HTML parsing |
| `pydantic` | Product, review & result data models with validation |
| `pydantic-settings` | Environment-based settings |
| `python-json-logger` | JSON log formatter for production |
| `fastapi` | REST API framework |
| `uvicorn` | ASGI server to run FastAPI |
| `playwright` | Browser automation for reviews pagination and product search |
| `playwright-stealth` | Anti-bot stealth patches applied to Playwright pages |

---

## ⚙️ Setup

### 1. Install Pipenv

```bash
pip install pipenv
```

### 2. Install project dependencies

```bash
pipenv install
```

This reads from `Pipfile` and creates an isolated virtual environment automatically.

### 3. Install Playwright browsers

```bash
pipenv run playwright install chromium
```

This downloads the Chromium binary used by the reviews scraper and product search.

### 4. Configure environment variables

Copy `example.env` to `.env` and fill in your values:

```bash
cp example.env .env
```

| Variable | Default | Options / Notes |
|---|---|---|
| `ENV` | *(required)* | `development`, `production` |
| `LOG_LEVEL` | *(required)* | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `AMAZON_EMAIL` | *(required, can not be blank)* | Amazon India account email — **must be an already signed-in account** (see note below) |
| `AMAZON_PASSWORD` | *(required, can not be blank)* | Amazon India account password — **must be an already signed-in account** (see note below) |
| `THRESHOLD_LIMIT` | `200` | Maximum number of reviews or search products to collect before stopping |

`ENV`, `LOG_LEVEL`, `AMAZON_EMAIL`, and `AMAZON_PASSWORD` are all required keys in `Settings` (`pydantic-settings` raises a startup error if any is missing from `.env`), but `AMAZON_EMAIL`/`AMAZON_PASSWORD` can be left as empty strings if you don't want auto sign-in.

In `production`, logs are emitted as **JSON**. In `development`, logs use a human-readable **standard** format.

> **Note:** The `HEADLESS` flag (controls whether Playwright opens a visible browser window) is configured directly in `src/config/constants.py` and defaults to `HEADLESS = True` — Playwright-driven search and reviews scraping run Chromium invisibly in the background by default (this is what makes it possible to run inside Docker, which has no display). CAPTCHA/OTP/MFA challenges are surfaced through the **dashboard OTP popup** instead of a visible window — see [🔑 OTP & MFA Dashboard Popup](#-otp--mfa-dashboard-popup) below. Set `HEADLESS = False` only if you're running locally with a display and prefer to resolve challenges by watching the actual browser window.

> **Note:** `AMAZON_EMAIL` and `AMAZON_PASSWORD` may be left blank. If a login page is detected and no credentials are configured, the scraper logs a warning and continues — but session-gated content may not be accessible.

> ⚠️ **Important — the email must already have a registered Amazon account:** Auto sign-in requires an email/password pair for an account that **already exists** on Amazon. If Amazon doesn't recognize the email (shows a "Create account" prompt or similar "new to Amazon" screen), the scraper does not attempt to register one — it immediately raises an error and aborts that sign-in attempt (see the [🔑 Auto Sign-in](#-auto-sign-in) section). If the email/password **do** belong to an existing account but Amazon still challenges the login with an OTP/MFA step (e.g. a new or unrecognized device), that challenge is resolved through the **dashboard OTP popup** — no visible browser window is needed, even with the default `HEADLESS = True`. Once OTP verification is completed for an existing account, the login is kept alive in the shared browser context (backed by the on-disk profile at `src/amazon_user_session/`) for the rest of that server process's lifetime, so later searches/reviews in the same run won't require OTP again — and because the profile is written to disk (and, in Docker, mounted as a volume), a server or container restart normally does **not** clear it either, so OTP shouldn't be required again unless the `amazon_user_session/` directory is deleted or Amazon invalidates the session itself.

---

## 🚀 Usage

### Start the server

```bash
pipenv run uvicorn src.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

The `--reload` flag enables hot-reloading on code changes (recommended for development).

Open `http://127.0.0.1:8000` in your browser to use the **web dashboard UI**.

---

## 🐳 Docker

The project ships with a `Dockerfile`, `docker-compose.yml`, and `.dockerignore` so it can run without installing Python, Pipenv, or Playwright's browser binaries on the host at all — everything is built into the image.

### 1. Configure environment variables

Docker reads the same `.env` file as the local Pipenv setup:

```bash
cp example.env .env
# then edit .env and fill in ENV, LOG_LEVEL, AMAZON_EMAIL, AMAZON_PASSWORD, THRESHOLD_LIMIT
```

> ⚠️ **Never commit `.env` (or any file with real credentials) to version control.** `.env` is already listed in `.gitignore` and `.dockerignore`, so it's read at build/run time but never baked into the image or pushed to a registry. If credentials were ever committed or shared, rotate the Amazon account password immediately.

### 2. Build and run with Docker Compose (recommended)

```bash
docker compose up --build
```

This builds the image, starts the container in the foreground, and:
- publishes the API on `http://127.0.0.1:8000`
- mounts `./logs`, `./output`, and `./src/amazon_user_session` as volumes, so scrape/search/review output, log files, **and** the persistent Chromium sign-in profile all survive container restarts and rebuilds on the host
- allocates a 1 GB `/dev/shm` (`shm_size`), since Chromium's default shared-memory allowance is too small and will crash on memory-heavy pages
- restarts automatically unless explicitly stopped (`restart: unless-stopped`), with a `30s` grace period on shutdown so `BrowserManager` can flush the browser context to disk cleanly

> **Note:** Neither `docker-compose.yml` nor the `Dockerfile` currently defines a container `HEALTHCHECK`. `GET /api/tasks` is a lightweight endpoint you can point your own external monitoring/orchestration at if you need one.

Run it in the background instead with:

```bash
docker compose up --build -d
```

Stop it with:

```bash
docker compose down
```

### 3. Build and run with plain `docker` (no Compose)

```bash
docker build -t amazon-scraper .

docker run -d \
  --name amazon-scraper \
  -p 8000:8000 \
  --env-file .env \
  --shm-size=1gb \
  -v "$(pwd)/logs:/app/logs" \
  -v "$(pwd)/output:/app/output" \
  -v "$(pwd)/src/amazon_user_session:/app/src/amazon_user_session" \
  amazon-scraper
```

### What the image does

- Base image: `python:3.12-slim`, matching the `python_version = "3.12"` pin in `Pipfile`.
- Dependencies are installed from `Pipfile.lock` via `pipenv install --deploy --system`, so the container gets exactly the locked versions — the build fails loudly if `Pipfile` and `Pipfile.lock` are out of sync instead of silently re-resolving.
- `playwright install --with-deps chromium` installs both the Chromium binary and the OS-level shared libraries it needs, so no manual `apt-get` step is required.
- The app runs as a non-root `appuser`, not `root` — Chromium's sandbox works fine unprivileged, so there's no need to disable it with `--no-sandbox`.
- `uvicorn` is started **without** `--reload` (reload is a filesystem-watching dev convenience with no place in a built image — code changes require rebuilding).
- `logs/`, `output/{reviews,searches}/`, and `src/amazon_user_session/` are created at build time and are the same paths the volumes above mount over. `src/amazon_user_session/` in particular is where Playwright's `launch_persistent_context` writes the Chromium sign-in profile (Cookies, Cache, Local Storage, etc.) — if you skip the volume mounts, the app still works, it just won't persist logs, scrape output, or the signed-in session between container runs.

### Headless mode inside the container

Docker containers have no display, so `HEADLESS` **must** stay at its default of `True` (see `src/config/constants.py`) when running in a container — a visible Chromium window is not an option here. This is exactly what the [🔑 OTP & MFA Dashboard Popup](#-otp--mfa-dashboard-popup) exists for: sign in, search, and review runs that hit a login/OTP/CAPTCHA challenge surface it through `/api/otp/*` and the dashboard popup, so you can resolve it from your browser (pointed at the container's port 8000) even though the browser Playwright is driving is invisible.

---

## 🖥️ Web Dashboard

Navigate to `http://127.0.0.1:8000` in your browser. The dashboard provides three modes toggled from the top tab bar:

- **Product Details** tab — calls `/api/scrape` with a product URL and displays the full product JSON including title, images, price, ratings, description, and variants (no reviews — use the **Product Reviews** tab for that).

- **Search Products** tab — calls `/api/search` with a keyword query, launches a Chromium browser on the server (headless by default) to paginate through search result pages until no further page is found or `THRESHOLD_LIMIT` products are collected, and returns all collected products as JSON. Each result includes the product title, price, Amazon product link, and estimated delivery duration in days.

- **Product Reviews** tab — calls `/api/scrape/reviews` with a product URL, launches a Chromium browser on the server (headless by default) to paginate through review pages until no further page is found or `THRESHOLD_LIMIT` reviews are collected, and returns all collected reviews as JSON. A **Download CSV** button appears once results are ready.

- Syntax-highlighted JSON output with clickable image URLs (opens a preview modal)

- A **Copy Payload** button to copy the raw JSON to clipboard

- A **Cancel Task** button that appears while a scrape is in progress — calls `POST /api/cancel/{task_key}` to abort the active background task for the current mode

- **Task Stats & History panel** (sidebar) — tracks every run made from the dashboard in the browser's `localStorage` (persists across page refreshes, up to 200 entries):
  - Live counters for **Completed**, **Failed**, **Stopped**, and **Total Tasks**
  - Clicking any counter opens a **Task History** modal filtered to that outcome (or all tasks); clicking an individual entry drills into a detail view showing the query/URL, endpoint, start/finish timestamps, duration, result summary or error reason, and the raw JSON payload (payloads over ~20KB are dropped from storage to stay under the browser quota, with a note shown in their place)
  - A **Clear** button wipes all saved stats and history after a confirmation prompt
  - This history is purely client-side (per browser, per machine) — it is not persisted or read by the FastAPI backend, so cancelling/refreshing/using a different browser will not share or preserve it

> **Note:** Product Reviews and Search Products both drive a Chromium browser on the machine running the server. With the default `HEADLESS = True` setting the browser runs invisibly, so CAPTCHA/OTP prompts can't be resolved by looking at a window — instead, an OTP challenge pops up in the dashboard (see [🔑 OTP & MFA Dashboard Popup](#-otp--mfa-dashboard-popup)) for you to submit the code from wherever the dashboard is open. If a CAPTCHA is encountered, the scraper pauses for `CAPTCHA_WAIT` seconds (default: 120 seconds, configurable in `constants.py`) and then continues, whether or not the challenge was resolved. Set `HEADLESS = False` in `src/config/constants.py` if you'd rather run with a visible browser window locally. If Amazon redirects to a login page and credentials are configured in `.env`, sign-in is handled automatically.

---

## 🌐 API Endpoints

### `GET /`

Serves the web dashboard UI (`templates/index.html`).

---

### `GET /api/tasks`

Returns the list of currently active (in-progress, not yet completed) background task keys. Useful for polling whether a scrape, search, or reviews job is still running.

**Success Response — `200 OK`:**
```json
{
    "active_tasks": ["scrape:https://www.amazon.in/dp/B0GL8FNY5G", "search:watermelon seeds"]
}
```

---

### `POST /api/cancel/{task_key}`

Explicitly cancels an active background task by its key. Task keys follow the pattern `{mode}:{normalized_url_or_query}`, where `mode` is `scrape`, `reviews`, or `search` (as returned by `GET /api/tasks`). The URL portion of `scrape`/`reviews` keys is automatically re-normalized server-side before lookup, so it doesn't need to match the original request character-for-character.

No request body is needed — the `task_key` is sent directly in the URL path. FastAPI captures everything after `/api/cancel/` as a single path parameter, including the colon and any embedded URL.

| Task Type | Example `task_key` |
|---|---|
| Scrape | `scrape:https://www.amazon.in/dp/B0GL8FNY5G` |
| Reviews | `reviews:https://www.amazon.in/dp/B0GL8FNY5G` |
| Search | `search:watermelon seeds` |

**Success Response — `200 OK`:**
```json
{
    "cancelled": true,
    "task_key": "scrape:https://www.amazon.in/dp/B0GL8FNY5G"
}
```

**Error Responses:**

| Status | Trigger |
|---|---|
| `404 Not Found` | No active task matches the given `task_key` (already completed, never started, or wrong key) |

```json
{
    "detail": "No active task found matching target contextual identifier: scrape:https://example.com"
}
```

> **Note:** Every long-running request also self-cancels automatically if the HTTP client disconnects mid-request — the server polls connection state every `0.5s` and aborts the underlying `asyncio` task, returning a `499` status internally. Launching a second identical request (same mode + same normalized URL/query) while one is already in flight also cancels the earlier one automatically before starting the new run.

---

### `POST /api/scrape`

Scrapes product details from a given Amazon India product URL using `requests` + `BeautifulSoup`.

> This endpoint does **not** return reviews — the `Product` model has no `reviews` field. For reviews, call `POST /api/scrape/reviews` instead.

**Request Body (JSON):**
```json
{
    "url": "https://www.amazon.in/dp/B0GL8FNY5G"
}
```

**Success Response — `200 OK`:**
```json
{
    "asin": "B0GL8FNY5G",
    "title": "Samsung Galaxy S25 Ultra 5G (Titanium Black, 12GB RAM, 256GB Storage)",
    "image": [
        "https://m.media-amazon.com/images/I/71example1.jpg",
        "https://m.media-amazon.com/images/I/71example2.jpg"
    ],
    "price": 109999.0,
    "ratings": 4.5,
    "ratings_count": 1284,
    "description": "Built-in Privacy Display — ... Snapdragon 8 Elite — ...",
    "variants": [
        {
            "type": "Color",
            "options": ["Titanium Black", "Titanium Gray", "Titanium WhiteSilver"]
        },
        {
            "type": "Size",
            "options": ["12GB + 256GB", "12GB + 512GB"]
        }
    ]
}
```

**Error Responses:**

| Status | Trigger |
|---|---|
| `400 Bad Request` | URL is not a valid `amazon.in` URL (wrong domain or scheme) |
| `422 Unprocessable Entity` | FastAPI request body validation failed (e.g., empty `url` field) |
| `500 Internal Server Error` | Product data could not be parsed from the page |
| `502 Bad Gateway` | Network error while fetching the Amazon URL |
| `503 Service Unavailable` | Request was blocked by Amazon (CAPTCHA or robot check) |

---

### `POST /api/search`

Launches a Playwright-controlled Chromium browser to search Amazon India by keyword and paginate through search result pages. Scraping stops when the "Next" page control is no longer found or the total product count reaches the configured `THRESHOLD_LIMIT` — whichever comes first. Results are saved to `output/searches/search_{query}.json` on the server.

**Request Body (JSON):**
```json
{
    "query": "watermelon seeds"
}
```

**Success Response — `200 OK`:**
```json
{
    "total_products": 2,
    "products": [
        {
            "title": "True Elements Watermelon Seeds 250g - High in Protein | Raw Watermelon Seeds for Eating",
            "price": 319.0,
            "link": "https://www.amazon.in/dp/B01MEHGSRK/",
            "delivery_duration_days": 2
        },
        {
            "title": "Amazon Brand - Vedaka Raw Watermelon Seeds 500G",
            "price": "Unavailable",
            "link": "https://www.amazon.in/dp/B0D1BNTCXM/",
            "delivery_duration_days": "Unavailable"
        }
    ]
}
```

**Search Result Fields:**

| Field | Type | Description |
|---|---|---|
| `total_products` | `int` | Total number of unique products collected across all pages |
| `title` | `string` | Product title as shown on the search result card |
| `price` | `float \| "Unavailable"` | Listed price in INR; the literal string `"Unavailable"` if no price could be parsed from the card |
| `link` | `string` | Direct Amazon product URL (`https://www.amazon.in/dp/{ASIN}/`) |
| `delivery_duration_days` | `int \| "Unavailable"` | Estimated days until delivery, calculated from the delivery date shown on the card; the literal string `"Unavailable"` if not found |

> Products are deduplicated by ASIN across all pages. Results are also progressively saved to disk after each page using atomic writes, so partial results are preserved even if the scraper is interrupted.

---

### `POST /api/scrape/reviews`

Launches a Playwright-controlled Chromium browser to paginate through all review pages for the given product, collecting reviews until no further page is found or the `THRESHOLD_LIMIT` cap is reached. Reviews are also saved to `output/reviews/reviews_{ASIN}.csv` and `output/reviews/reviews_{ASIN}.json` on the server.

**Request Body (JSON):**
```json
{
    "url": "https://www.amazon.in/dp/B0GL8FNY5G"
}
```

**Success Response — `200 OK`:**
```json
{
    "asin": "B0GL8FNY5G",
    "reviews_count": 100,
    "reviews": [
        {
            "review_number": 1,
            "reviewer_name": "Priya M.",
            "review_date": "20 May 2025",
            "review_location": "India",
            "rating": 4.0,
            "review_title": "Great build quality",
            "review_body": "Solid phone with an excellent display...",
            "review_helpful": "3 people found this helpful"
        }
    ]
}
```

> This endpoint runs as a cancellable background task. Expect longer response times depending on the total number of review pages — scraping continues until Amazon has no further review pages or the configured `THRESHOLD_LIMIT` (default: `200`) is reached.

---

## 🧪 Testing with Postman

1. Open Postman and create a new **POST** request.

2. Set the URL to:
   ```
   http://127.0.0.1:8000/api/scrape
   ```

3. Go to the **Body** tab → select **raw** → choose **JSON** from the dropdown.

4. Enter the request body:
   ```json
   {
       "url": "https://www.amazon.in/dp/B0GL8FNY5G"
   }
   ```

5. Click **Send**.

> To test `POST /api/cancel/{task_key}`, set the method to **POST**, build the URL as `http://127.0.0.1:8000/api/cancel/{task_key}` (e.g., `.../api/cancel/scrape:https://www.amazon.in/dp/B0GL8FNY5G`), and leave the **Body** tab set to **none** — no body is required.

You can also explore and test all endpoints interactively via the auto-generated Swagger UI at:
```
http://127.0.0.1:8000/docs
```

---

## ✅ Valid URL Examples

```
https://www.amazon.in/dp/B0DSKL9MQ8

https://amazon.in/dp/B0DSKL9MQ8

https://www.amazon.in/Some-Product-Title/dp/B0F5QLS6SB
```

> **Note:** Query parameters (e.g., `?th=1`, `ref=...`) are automatically stripped by the scraper during URL normalization. Bare `amazon.in` (without `www.`) is also accepted and normalized automatically.

---

## ❌ Invalid URL Examples

```
https://www.amazon.com/dp/B09XYZ1234   # Wrong domain (.com not .in)

http://flipkart.com/product/xyz         # Not Amazon

ftp://www.amazon.in/dp/B0DSKL9MQ8      # Invalid scheme (must be http or https)
```

---

## ⚙️ Scraping Limits

Neither the reviews scraper nor the product search has a hardcoded page cap in code — both paginate by clicking "Next" and stop as soon as **one** of the following happens:

| Feature | Stops When |
|---|---|
| Product Reviews | No further "Next page" element is found, **or** `THRESHOLD_LIMIT` reviews have been collected, **or** the task is cancelled |
| Product Search | No further "Next page" element is found, **or** `THRESHOLD_LIMIT` products have been collected, **or** the task is cancelled |

- `THRESHOLD_LIMIT` (default: `200`, set via `.env`) is the hard upper bound on total items collected for either feature.

- Products in search results are deduplicated by ASIN; reviews are deduplicated by a hash of `reviewer_name + review_date + review_title + rating`.

- In practice, run length still depends on how many result/review pages Amazon actually serves for a given query or product before it runs out of pages.

---

## 🗂️ How It Works

### Product Details (`/api/scrape`)

1. **URL validation** — `Scraper.check_amazon_url()` checks scheme (`http`/`https`) and domain (`amazon.in` or any subdomain).

2. **URL normalization** — `Scraper.normalize_url()` adds `www.` if missing and strips all query parameters.

3. **HTTP request** — A `requests.Session` with browser-like headers and cookies fetches the page HTML.

4. **Block detection** — The page title and body text are scanned for CAPTCHA and robot-check keywords. If found, a `BLOCKED` result is returned.

5. **Parsing** — `BeautifulSoup` with `html.parser` parses the response and each field is extracted via its own method with fallback strategies:

   - **Images:** finds all `<img>` tags inside the `#altImages` thumbnail strip (falling back to `#imgTagWrapperId`) and upgrades thumbnail URLs to full-resolution by stripping the Amazon size suffix.
   - **Price:** searches `corePriceDisplay_desktop_feature_div` → `priceToPay` span → whole/fraction spans.
   - **Ratings:** tries `acrPopover` then `a-icon-alt`.
   - **Description:** tries `feature-bullets` span items first, then falls back to the `productDescription` div.
   - **Variants:** reads `inline-twister-row-*` divs with title/img-alt/swatch-span/text priority, falling back to the `desktop-twister-sort-filter-data` `a-state` JSON embedded in the page.

6. **Output** — `Product` is a Pydantic model; `.to_dict()` serializes it and FastAPI returns it as a JSON response. The raw HTML is saved to `output/source.html` for debugging (this single file is overwritten on every `/api/scrape` call, regardless of ASIN).

> `Scraper.reviews_details()` exists and can parse `[data-hook="review"]` blocks from a product page, but `scraping_data()` does not currently call it, so `/api/scrape` responses never include reviews. Use `/api/scrape/reviews` for reviews.

### Search Products (`/api/search`)

1. The search query is URL-encoded and navigated to `https://www.amazon.in/s?k={query}`.

2. Playwright drives the shared Chromium context managed by `BrowserManager` (launched once per server process and reused across all searches/reviews) with stealth patches applied via `playwright-stealth`.

3. Each page is scrolled to trigger lazy-loaded product cards, then parsed with `BeautifulSoup`.

4. Each result card is parsed for ASIN, title, price, product link, and estimated delivery days. Delivery days are calculated by parsing the delivery date text displayed on the card.

5. Results are filtered by relevance: stop-words are stripped from the query and each product title must contain the primary query token plus at least one secondary token. Accessory-type results (cases, covers, pouches) are automatically excluded unless the query explicitly targets them.

6. Products are deduplicated by ASIN across all pages.

7. After each page, progress is atomically written to `output/searches/search_{query}.json` (via a `.tmp` file swap) so partial results survive any interruption.

8. Pagination continues by clicking the "Next" button until no further page is found or the total product count hits the configured `THRESHOLD_LIMIT`.

### Product Reviews (`/api/scrape/reviews`)

1. The ASIN is extracted from the product URL via regex.

2. Playwright drives the shared Chromium context managed by `BrowserManager` (launched once per server process and reused across all searches/reviews) with stealth patches applied via `playwright-stealth`.

3. The browser navigates to `https://www.amazon.in/product-reviews/{ASIN}?reviewerType=all_reviews`.

4. If a login page is detected, the scraper automatically signs in using `AMAZON_EMAIL` and `AMAZON_PASSWORD` from `.env`. OTP/MFA pages trigger a request through `OtpManager`, which waits up to `OTP_WAIT_TIMEOUT` seconds (default: 180 seconds, configurable in `constants.py`) for the code to be submitted via the dashboard OTP popup before continuing.

5. Each page is scrolled to trigger lazy-loaded content, then parsed with `BeautifulSoup`.

6. If a CAPTCHA is detected in the page content, the scraper pauses for `CAPTCHA_WAIT` seconds (default: 120 seconds, configurable in `constants.py`) for manual resolution.

7. Reviews are deduplicated using a hash of `reviewer_name + date + title + rating` to prevent duplicates across page reloads.

8. After each page, reviews are appended incrementally to `output/reviews/reviews_{ASIN}.csv` and `output/reviews/reviews_{ASIN}.json`.

9. Pagination continues by clicking the next-page control until no further page is found or the `THRESHOLD_LIMIT` review count is hit.

---

## 🔑 Auto Sign-in

When `AMAZON_EMAIL` and `AMAZON_PASSWORD` are set in `.env`, the scraper can automatically authenticate whenever Amazon redirects to a login page during Playwright-driven scraping (both review and product search runs). All Playwright-driven scraping shares a single `BrowserManager`-managed Chromium context for the lifetime of the running server process, so a successful sign-in is reused by later searches/reviews within that same run.

> ⚠️ **Auto sign-in requires an email/password for an account that already exists on Amazon.** If the email is unrecognized (Amazon shows a "Create account" prompt or "We cannot find an account with that email address"), the scraper does **not** try to create one — it raises `RuntimeError("Login Error - New user detected. Please use a registered email id and password.")` and the sign-in attempt fails immediately; there is no manual-resolution path for this case. If the credentials **do** match an existing account but Amazon still challenges the login with an OTP/MFA step (e.g. an unrecognized device), that step **is** handled manually through the **dashboard OTP popup** rather than a visible browser window (see [🔑 OTP & MFA Dashboard Popup](#-otp--mfa-dashboard-popup)). Once the OTP is submitted and login is complete, the shared browser context stays signed in for the rest of that server process's lifetime, so subsequent runs in the same session won't require OTP again. Because the context is a `launch_persistent_context` profile written to `src/amazon_user_session/` on disk (and mounted as a Docker volume in `docker-compose.yml`), the signed-in state normally **survives** a server or container restart too — the next run will only need to sign in (and possibly complete OTP) again if `amazon_user_session/` is deleted/not mounted, or if Amazon itself invalidates the session.

The sign-in flow handles:
- **Email + password** — fills email, clicks Continue, then fills password and submits

- **Password-only** — detects a pre-filled email page and fills only the password

- **OTP / MFA** — if redirected to an MFA or mobile verification page after login (URL containing `mfa`, `auth-mfa`, `verification`, or `ap/cvf`), the scraper requests a code through `OtpManager` and waits up to `OTP_WAIT_TIMEOUT` seconds (default: 180 seconds, configurable in `constants.py`) for it to arrive from the dashboard OTP popup (or from a visible browser window if `HEADLESS = False`)

- **Unrecognized email ("new user") prompt** — if Amazon indicates the email isn't recognized (e.g. a "Create account" prompt or "We cannot find an account with that email address"), the scraper does **not** attempt to create an account. It immediately raises a `RuntimeError` ("Login Error - New user detected. Please use a registered email id and password.") which aborts the current sign-in attempt — the request fails fast with that message rather than pausing for manual resolution. Use an email/password pair for an **existing, already-verified** Amazon account instead.

After a successful login, the scraper automatically navigates back to the original target URL and resumes scraping. Login state lives in the shared `BrowserManager` context, which is a Chromium profile persisted on disk at `src/amazon_user_session/` (mounted as a volume in Docker) — later search/reviews runs (the two Playwright-driven endpoints that go through `BrowserManager`), including ones after a server or container restart, generally reuse it without re-authenticating. `/api/scrape` never touches `BrowserManager` at all — it uses a plain `requests.Session`, so this sign-in flow doesn't apply to it. A fresh sign-in (and possibly OTP verification) is only needed again if that directory is missing/deleted, isn't mounted, or Amazon invalidates the session server-side.

---

## 🔑 OTP & MFA Dashboard Popup

Because `HEADLESS` defaults to `True` (and Docker containers have no display at all), a visible browser window isn't available for manually typing in a one-time code. Instead, whenever the sign-in flow hits an OTP/MFA/delivery-method-choice screen, `OtpManager` parks the login coroutine on an `asyncio.Future` and exposes the pending request to the dashboard through a small polling API. The web dashboard polls these endpoints and shows a popup automatically — no manual configuration needed.

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/otp/status` | `GET` | Poll target — returns `{"waiting": bool, "error": str \| null}`. `waiting: true` means the login flow is currently blocked on a code. |
| `/api/otp/submit` | `POST` | Body: `{"otp": "123456"}`. Resolves the pending future with the code, unblocking the login flow. Returns `400` if no OTP request is currently pending. |
| `/api/otp/choice/status` | `GET` | Poll target for the OTP **delivery-method** chooser screen — returns `{"waiting": bool, "options": string[]}` (e.g. `["WhatsApp me at ...", "Text me at ..."]`). |
| `/api/otp/choice/submit` | `POST` | Body: `{"choice": "<one of the offered options, verbatim>"}`. Resolves the pending choice future. Returns `400` if the choice doesn't match one of the currently offered options. |

- If a submitted OTP is rejected by Amazon, the scraper calls `request_otp` again with an error message; `/api/otp/status` surfaces that message via its `error` field so the dashboard can show *why* it's asking again, up to `OTP_MAX_ATTEMPTS` (default: 3, configurable in `constants.py`) attempts.
- Both pollers are deliberately noisy at the HTTP level (they're hit on a short interval while waiting), so `PollingEndpointAccessFilter` strips `/api/otp/status` and `/api/otp/choice/status` requests out of the uvicorn access log to keep `logs/scraper.log` readable.
- If nobody submits a code within `OTP_WAIT_TIMEOUT` seconds (default: 180), the pending future is cancelled via `OtpManager.cancel()` / `cancel_choice()` so a stale request never blocks a future login attempt.

---

## 🪵 Logging

Logging is configured centrally in `utils/logger.py` using Python's `dictConfig`. Each module gets its own named logger:

```python
from src.utils.logger import get_logger
logger = get_logger("MY_MODULE")
```

- `urllib3` logs are suppressed below `WARNING` to reduce noise.

- Log level and format are controlled by the `LOG_LEVEL` and `ENV` environment variables.

- `setup_logging()` must be called once at startup (already done in `main.py`).

---

## 📦 Output Files

| File | Description |
|---|---|
| `output/source.html` | Raw HTML fetched from Amazon for the most recent `/api/scrape` call (overwritten every scrape, not per-ASIN) |
| `output/debug_otp_page.png` | Full-page screenshot saved automatically when an OTP/verification page can't be resolved, for debugging (overwritten on each occurrence) |
| `output/reviews/reviews_{ASIN}.csv` | All paginated reviews for that ASIN in CSV format |
| `output/reviews/reviews_{ASIN}.json` | All paginated reviews for that ASIN in JSON format |
| `output/searches/search_{query}.json` | All search result products for that query in JSON format |
| `logs/scraper.log` | Persistent log file (appended on each run) |

> **Note:** Product data from `/api/scrape` is **not** written to disk as JSON — it is returned directly as the API response. However, the raw HTML source page **is** saved to `output/source.html` on every scrape for debugging, overwriting whatever was there before. Review and search files are overwritten on each new scrape for the same ASIN or query. Search files use atomic `.tmp` → final file swaps to prevent partial writes.

---

## ⚠️ Disclaimer

This project is intended for **educational and personal use only**. Web scraping Amazon may violate their [Conditions of Use](https://www.amazon.in/gp/help/customer/display.html?nodeId=GLSBYFE9MGKKQXXM). Use responsibly and ensure you comply with applicable laws and platform policies.