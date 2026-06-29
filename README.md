# 🛒 Amazon Product Scraper

A Python-based web scraper that extracts product details from Amazon India (`amazon.in`) — including title, images, price, ratings, reviews, description, and variants — and exposes the results via a **FastAPI REST API** with a built-in web dashboard UI.

---

## 📁 Project Structure

```
WEB-SCRAPING/
├── logs/
│   └── scraper.log              # Log file output (auto-generated)
├── output/
│   ├── source_{ASIN}.html       # Raw HTML response saved per ASIN for debugging (auto-generated)
│   ├── reviews/
│   │   ├── reviews_{ASIN}.csv   # Paginated reviews exported as CSV (auto-generated)
│   │   └── reviews_{ASIN}.json  # Paginated reviews exported as JSON (auto-generated)
│   └── searches/
│       └── search_{query}.json  # Search results exported as JSON (auto-generated)
├── src/
│   ├── amazon_user_session/     # Persistent Playwright browser sessions (auto-generated)
│   │   ├── reviews_{ASIN}/      # Per-ASIN session for review scraping
│   │   └── search_{query_slug}/ # Per-query session for catalog search
│   ├── classes/
│   │   ├── Product.py           # Pydantic product model
│   │   ├── Review.py            # Pydantic review model
│   │   ├── Scraper.py           # Core scraping logic (requests + Playwright)
│   │   ├── ScrapeFailReason.py  # Enum for scrape failure categories
│   │   ├── ScrapeRequest.py     # Pydantic request body model
│   │   ├── ScrapeResult.py      # Pydantic result wrapper model
│   │   ├── SearchRequest.py     # Pydantic search request body model
│   │   ├── SearchResult.py      # Pydantic search result model
│   │   └── Settings.py          # Environment-based settings (pydantic-settings)
│   ├── config/
│   │   ├── constants.py         # HTTP headers, cookies & directory constants
│   │   └── selectors.py         # BeautifulSoup CSS selectors
│   ├── static/
│   │   └── favicon.png          # Dashboard favicon
│   ├── templates/
│   │   └── index.html           # Web dashboard UI (TailwindCSS + glassmorphism)
│   ├── utils/
│   │   └── logger.py            # Centralized logging setup
│   ├── main.py                      # FastAPI app entry point (root-level)
├── .env                         # Local environment variables (git-ignored)
├── .gitignore
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
  - **Reviews** (on-page reviews from the product listing, captured inline during product scrape)
- **Search Products** powered by Playwright — searches Amazon by keyword, paginates up to **20 pages**, deduplicates results by ASIN, and saves output to `output/searches/search_{query}.json`. Each search result includes product title, price, direct product link, and estimated delivery days.
- **Product Reviews** powered by Playwright — paginates through review pages up to **10 pages (~100 reviews per product)**, detects CAPTCHAs and waits for manual resolution, deduplicates reviews across pages, and saves results to `output/reviews/reviews_{ASIN}.csv` and `output/reviews/reviews_{ASIN}.json`
- **Automatic Amazon sign-in** — if credentials are provided via `.env`, the scraper detects login/OTP pages and handles authentication automatically before resuming scraping. Supports both email+password and password-only flows, and pauses for OTP/MFA resolution if required.
- Persistent, isolated Playwright browser sessions stored per ASIN (`amazon_user_session/reviews_{ASIN}/`) and per search query (`amazon_user_session/search_{slug}/`) to preserve login cookies across runs without cross-contamination.
- **Atomic search file writes** — search progress is first written to a `.tmp` file and then atomically replaced, preventing partial or corrupt output on interruption.
- Saves raw HTML response for debugging (`output/source_{ASIN}.html`)
- Environment-aware logging — JSON logs in production, human-readable standard format in development
- Named loggers per module for clean, traceable log output
- REST API with FastAPI — interactive Swagger docs available at `/docs`
- **Built-in web dashboard** at `/`:
  - Glassmorphism dark UI (TailwindCSS + Font Awesome icons)
  - Three scrape modes toggled from the UI: **Product Details**, **Catalog Search**, and **Deep Reviews Scrape**
  - Animated laser-beam loading indicator and skeleton screen while scraping
  - Syntax-highlighted JSON output (color-coded keys, strings, numbers, booleans)
  - Clickable image URLs open in a full image preview modal
  - **Download CSV** button for paginated review results

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
| `playwright` | Browser automation for deep review pagination and catalog search |
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

This downloads the Chromium binary used by the deep reviews scraper and catalog search.

### 4. Configure environment variables

Copy `example.env` to `.env` and fill in your values:

```bash
cp example.env .env
```

| Variable | Default | Options / Notes |
|---|---|---|
| `ENV` | `development` | `development`, `production` |
| `LOG_LEVEL` | `DEBUG` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `AMAZON_EMAIL` | *(empty)* | Amazon India account email — **must be an already signed-in account** (see note below) |
| `AMAZON_PASSWORD` | *(empty)* | Amazon India account password — **must be an already signed-in account** (see note below) |
| `THRESHOLD_LIMIT` | `500` | Maximum number of reviews or search products to collect before stopping |

In `production`, logs are emitted as **JSON**. In `development`, logs use a human-readable **standard** format.

> **Note:** The `HEADLESS` flag (controls whether Playwright opens a visible browser window) is configured directly in `src/config/constants.py` (`HEADLESS = False`) and is **not** an environment variable. Change it there to `True` to run browsers invisibly on a headless server.

> **Note:** `AMAZON_EMAIL` and `AMAZON_PASSWORD` are optional. If omitted, the scraper will still work for sessions that are already authenticated. If a login page is detected and no credentials are provided, the scraper logs a warning and continues — but session-gated content may not be accessible.
>
> ⚠️ **Important — First-time accounts require manual setup:** Auto sign-in only works reliably with an account that has **previously been signed in** on this machine. If you use a brand-new or never-used email and password, Amazon will trigger a **mobile number verification step** (OTP sent to your registered phone) before allowing access. This step cannot be automated and must be completed manually in the browser window. Once you have completed the manual OTP verification at least once, the session is saved in `amazon_user_session/` and all future runs will sign in automatically without requiring OTP again.

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

## 🖥️ Web Dashboard

Navigate to `http://127.0.0.1:8000` in your browser. The dashboard provides three modes toggled from the top tab bar:

- **Product Details** tab — calls `/api/scrape` with a product URL and displays the full product JSON including title, images, price, ratings, description, variants, and on-page reviews.
- **Search Products** tab — calls `/api/search` with a keyword query, launches a visible Chromium browser on the server to paginate up to **20 search result pages**, and returns all collected products as JSON. Each result includes the product title, price, Amazon product link, and estimated delivery duration in days.
- **Product Reviews** tab — calls `/api/scrape/reviews` with a product URL, launches a visible Chromium browser on the server to paginate up to **10 review pages (~100 reviews)**, and returns all collected reviews as JSON. A **Download CSV** button appears once results are ready.
- Syntax-highlighted JSON output with clickable image URLs (opens a preview modal)
- A **Copy Payload** button to copy the raw JSON to clipboard

> **Note:** The Product Reviews and Search Products both open a real browser window on the machine running the server. If a CAPTCHA is encountered, the browser pauses for 25 seconds to allow manual resolution before continuing. If Amazon redirects to a login page and credentials are configured in `.env`, sign-in is handled automatically.

---

## 🌐 API Endpoints

### `GET /`

Serves the web dashboard UI (`templates/index.html`).

---

### `POST /api/scrape`

Scrapes product details from a given Amazon India product URL using `requests` + `BeautifulSoup`. Also captures any reviews visible on the product page itself.

**Request Body (JSON):**
```json
{
    "url": "https://www.amazon.in/dp/B0GL8FNY5G"
}
```

**Success Response — `200 OK`:**
```json
{
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
    ],
    "reviews": [
        {
            "review_number": 1,
            "reviewer_name": "Rahul S.",
            "review_date": "15 April 2025",
            "review_location": "India",
            "review_title": "Excellent phone, worth every rupee",
            "rating": 5.0,
            "review_body": "Battery life is outstanding and the camera quality is superb...",
            "review_helpful": "12 people found this helpful"
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

Launches a Playwright-controlled Chromium browser to search Amazon India by keyword and paginate through search result pages. Scraping stops after **20 pages** or when the total product count reaches the configured `THRESHOLD_LIMIT` — whichever comes first. Results are saved to `output/searches/search_{query}.json` on the server.

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
            "price": 549.0,
            "link": "https://www.amazon.in/dp/B0D1BNTCXM/",
            "delivery_duration_days": null
        }
    ]
}
```

**Search Result Fields:**

| Field | Type | Description |
|---|---|---|
| `total_products` | `int` | Total number of unique products collected across all pages |
| `title` | `string` | Product title as shown on the search result card |
| `price` | `float \| null` | Listed price in INR; `null` if not displayed on the card |
| `link` | `string` | Direct Amazon product URL (`https://www.amazon.in/dp/{ASIN}/`) |
| `delivery_duration_days` | `int \| null` | Estimated days until delivery, calculated from the delivery date shown on the card; `null` if not available |

> Products are deduplicated by ASIN across all pages. Results are also progressively saved to disk after each page using atomic writes, so partial results are preserved even if the scraper is interrupted.

---

### `POST /api/scrape/reviews`

Launches a Playwright-controlled Chromium browser to paginate through all review pages for the given product, collecting reviews up to **10 pages (~100 reviews)**. Reviews are also saved to `output/reviews/reviews_{ASIN}.csv` and `output/reviews/reviews_{ASIN}.json` on the server.

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

> This endpoint runs synchronously in a background thread. Expect longer response times depending on the total number of review pages. Scraping caps at 10 pages, yielding approximately 100 reviews per run (Amazon shows ~10 reviews per page).

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

| Feature | Page Limit | Item Limit |
|---|---|---|
| Deep Review Scraper | 10 pages | ~100 reviews |
| Catalog Search | 20 pages | Up to 20 pages products |

- Amazon displays approximately **10 reviews per page**, so 10 pages yields roughly **100 reviews** per run.
- The catalog search paginates through up to **20 result pages**. Each page typically contains 15–20 products, yielding approximately 300–400 unique products per search.
- Both scrapers also respect the `THRESHOLD_LIMIT` environment variable (default: `500`) as a hard upper bound on total items collected — pagination stops whichever limit is hit first.
- Products in search results are deduplicated by ASIN; reviews are deduplicated by a hash of `reviewer_name + date + title + rating`.

---

## 🗂️ How It Works

### Product Details (`/api/scrape`)

1. **URL validation** — `Scraper.check_amazon_url()` checks scheme (`http`/`https`) and domain (`amazon.in` or any subdomain).
2. **URL normalization** — `Scraper.normalize_url()` adds `www.` if missing and strips all query parameters.
3. **HTTP request** — A `requests.Session` with browser-like headers and cookies fetches the page HTML.
4. **Block detection** — The page title and body text are scanned for CAPTCHA and robot-check keywords. If found, a `BLOCKED` result is returned.
5. **Parsing** — `BeautifulSoup` with `html.parser` parses the response and each field is extracted via its own method with fallback strategies:
   - **Images:** finds all `<img alt="Product Image">` tags and upgrades thumbnail URLs to full-resolution by stripping the Amazon size suffix.
   - **Price:** searches `corePriceDisplay_desktop_feature_div` → `priceToPay` span → whole/fraction spans.
   - **Ratings:** tries `acrPopover` then `a-icon-alt`.
   - **Description:** tries `feature-bullets` span items first, then falls back to the `productDescription` div.
   - **Variants:** reads `inline-twister-row-*` divs with title/img-alt/swatch-span/text priority, falling back to the `desktop-twister-sort-filter-data` `a-state` JSON embedded in the page.
   - **Reviews:** collects all `[data-hook="review"]` blocks from the product page.
6. **Output** — `Product` is a Pydantic model; `.to_dict()` serializes it and FastAPI returns it as a JSON response. Raw HTML is saved to `output/source_{ASIN}.html` for debugging.

### Search Products (`/api/search`)

1. The search query is URL-encoded and navigated to `https://www.amazon.in/s?k={query}`.
2. Playwright launches a persistent Chromium context from a per-query session directory (`amazon_user_session/search_{slug}/`) with stealth patches applied.
3. Each page is scrolled to trigger lazy-loaded product cards, then parsed with `BeautifulSoup`.
4. Each result card is parsed for ASIN, title, price, product link, and estimated delivery days. Delivery days are calculated by parsing the delivery date text displayed on the card.
5. Results are filtered by relevance: stop-words are stripped from the query and each product title must contain the primary query token plus at least one secondary token. Accessory-type results (cases, covers, pouches) are automatically excluded unless the query explicitly targets them.
5. Products are deduplicated by ASIN across all pages.
6. After each page, progress is atomically written to `output/searches/search_{query}.json` (via a `.tmp` file swap) so partial results survive any interruption.
7. Pagination continues by clicking the "Next" button until no further pages are found, 20 pages are reached, or the total product count hits the configured threshold.

### Product Reviews (`/api/scrape/reviews`)

1. The ASIN is extracted from the product URL via regex.
2. Playwright launches a persistent Chromium context from a per-ASIN session directory (`amazon_user_session/reviews_{ASIN}/`) with stealth patches applied.
3. The browser navigates to `https://www.amazon.in/product-reviews/{ASIN}?reviewerType=all_reviews`.
4. If a login page is detected, the scraper automatically signs in using `AMAZON_EMAIL` and `AMAZON_PASSWORD` from `.env`. OTP/MFA pages trigger a configurable wait (`CAPTCHA_WAIT`) for manual resolution before continuing.
5. Each page is scrolled to trigger lazy-loaded content, then parsed with `BeautifulSoup`.
6. If a CAPTCHA is detected in the page content, the scraper pauses for 25 seconds for manual resolution.
7. Reviews are deduplicated using a hash of `reviewer_name + date + title + rating` to prevent duplicates across page reloads.
8. After each page, reviews are appended incrementally to `output/reviews/reviews_{ASIN}.csv` and `output/reviews/reviews_{ASIN}.json`.
9. Pagination continues by clicking the next-page control until no further pages are found, **10 pages** are reached, or the threshold limit is hit.

---

## 🔑 Auto Sign-in

When `AMAZON_EMAIL` and `AMAZON_PASSWORD` are set in `.env`, the scraper can automatically authenticate whenever Amazon redirects to a login page during Playwright-driven scraping (both review and catalog search sessions).

> ⚠️ **Auto sign-in only works with an already signed-in account.** If the email and password belong to an account that has never been used on this machine before, Amazon will require **mobile number verification** — it sends an OTP to the registered phone number before granting access. This verification step is fully manual: you must enter the OTP in the visible browser window yourself. The scraper cannot automate this step. Once the OTP is entered and login is complete for the first time, the session is saved to `amazon_user_session/` and all subsequent runs will authenticate automatically without requiring OTP again.

The sign-in flow handles:
- **Email + password** — fills email, clicks Continue, then fills password and submits
- **Password-only** — detects a pre-filled email page and fills only the password
- **OTP / MFA** — if redirected to an MFA or mobile verification page after login, the scraper pauses for `CAPTCHA_WAIT` seconds (default: 3 seconds, configurable in `constants.py`) to allow manual OTP entry in the browser window

After a successful login, the scraper automatically navigates back to the original target URL and resumes scraping. Login state is persisted in the session directory so subsequent runs for the same ASIN or query will not need to re-authenticate.

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
| `output/source_{ASIN}.html` | Raw HTML fetched from Amazon, saved per ASIN after each product scrape |
| `output/reviews/reviews_{ASIN}.csv` | All paginated reviews for that ASIN in CSV format |
| `output/reviews/reviews_{ASIN}.json` | All paginated reviews for that ASIN in JSON format |
| `output/searches/search_{query}.json` | All search result products for that query in JSON format |
| `logs/scraper.log` | Persistent log file (appended on each run) |

> **Note:** Product data from `/api/scrape` is **not** written to disk as JSON — it is returned directly as the API response. However, the raw HTML source page **is** saved to `output/source_{ASIN}.html` per scrape for debugging. Review and search files are overwritten on each new scrape for the same ASIN or query. Search files use atomic `.tmp` → final file swaps to prevent partial writes.

---

## ⚠️ Disclaimer

This project is intended for **educational and personal use only**. Web scraping Amazon may violate their [Conditions of Use](https://www.amazon.in/gp/help/customer/display.html?nodeId=GLSBYFE9MGKKQXXM). Use responsibly and ensure you comply with applicable laws and platform policies.