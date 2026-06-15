# 🛒 Amazon Product Scraper

A Python-based web scraper that extracts product details from Amazon India (`amazon.in`) — including title, images, price, ratings, reviews, description, and variants — and exposes the results via a **FastAPI REST API** with a built-in web dashboard UI.

---

## 📁 Project Structure

```
WEB-SCRAPING/
├── amazon_user_session/         # Persistent Playwright browser session (auto-generated)
├── logs/
│   └── scraper.log              # Log file output (auto-generated)
├── output/
│   ├── source.html              # Raw HTML response saved for debugging (auto-generated)
│   ├── reviews_{ASIN}.csv       # Paginated reviews exported as CSV (auto-generated)
│   └── reviews_{ASIN}.json      # Paginated reviews exported as JSON (auto-generated)
├── src/
│   ├── classes/
│   │   ├── Product.py           # Pydantic product model
│   │   ├── Review.py            # Pydantic review model
│   │   ├── Scraper.py           # Core scraping logic (requests + Playwright)
│   │   ├── ScrapeFailReason.py  # Enum for scrape failure categories
│   │   ├── ScrapeRequest.py     # Pydantic request body model
│   │   ├── ScrapeResult.py      # Pydantic result wrapper model
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
│   └── main.py                  # FastAPI app entry point
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
- **Deep review scraper** powered by Playwright — paginates through all review pages, detects CAPTCHAs and waits for manual resolution, deduplicates reviews across pages, and saves results to `output/reviews_{ASIN}.csv` and `output/reviews_{ASIN}.json`
- Persistent Playwright browser session stored in `amazon_user_session/` to preserve login cookies across runs
- Saves raw HTML response for debugging (`output/source.html`)
- Environment-aware logging — JSON logs in production, human-readable standard format in development
- Named loggers per module for clean, traceable log output
- REST API with FastAPI — interactive Swagger docs available at `/docs`
- **Built-in web dashboard** at `/`:
  - Glassmorphism dark UI (TailwindCSS)
  - Two scrape modes toggled from the UI: **Product Details** and **Deep Reviews Scrape**
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
| `playwright` | Browser automation for deep review pagination |
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

This downloads the Chromium binary used by the deep reviews scraper.

### 4. Configure environment variables

Copy `example.env` to `.env` and fill in your values:

```bash
cp example.env .env
```

`.env` example:

```env
ENV=development
LOG_LEVEL=DEBUG
```

| Variable | Default | Options |
|---|---|---|
| `ENV` | `development` | `development`, `production` |
| `LOG_LEVEL` | `DEBUG` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |

In `production`, logs are emitted as **JSON**. In `development`, logs use a human-readable **standard** format.

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

Navigate to `http://127.0.0.1:8000` in your browser. The dashboard provides:

- A URL input field shared across both scrape modes
- **Product Details** tab — calls `/api/scrape` and displays the full product JSON
- **Deep Reviews Scrape** tab — calls `/api/scrape/reviews`, launches a visible Chromium browser on the server to paginate review pages, and returns all collected reviews as JSON. A **Download CSV** button appears once results are ready.
- Syntax-highlighted JSON output with clickable image URLs (opens a preview modal)
- A **Copy Payload** button to copy the raw JSON to clipboard

> **Note:** The deep review scraper opens a real browser window on the machine running the server. If a CAPTCHA is encountered, the browser pauses for 25 seconds to allow manual resolution before continuing.

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

### `POST /api/scrape/reviews`

Launches a Playwright-controlled Chromium browser to paginate through all review pages for the given product, collecting every review until no further pagination is found. Reviews are also saved to `output/reviews_{ASIN}.csv` and `output/reviews_{ASIN}.json` on the server.

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
    "reviews_count": 142,
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

> This endpoint runs synchronously in a background thread. Expect longer response times depending on the total number of review pages.

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

## 🗂️ How It Works

### Product Scrape (`/api/scrape`)

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
6. **Output** — `Product` is a Pydantic model; `.to_dict()` serializes it and FastAPI returns it as a JSON response. Raw HTML is saved to `output/source.html` for debugging.

### Deep Review Scrape (`/api/scrape/reviews`)

1. The ASIN is extracted from the product URL via regex.
2. Playwright launches a persistent Chromium context from `amazon_user_session/` (preserving session cookies across runs) with stealth patches applied.
3. The browser navigates to `https://www.amazon.in/product-reviews/{ASIN}?reviewerType=all_reviews`.
4. Each page is scrolled to trigger lazy-loaded content, then parsed with `BeautifulSoup`.
5. If a CAPTCHA is detected in the page content, the scraper pauses for 25 seconds for manual resolution.
6. Reviews are deduplicated using a hash of `reviewer_name + date + title + rating` to prevent duplicates across page reloads.
7. After each page, the scraper looks for a pagination control (`li.a-last a`, `a:has-text('Next page')`, etc.). If found, it clicks through and repeats; otherwise it stops.
8. All collected reviews are appended incrementally to `output/reviews_{ASIN}.csv` and `output/reviews_{ASIN}.json` and returned in the API response.

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
| `output/source.html` | Raw HTML fetched from Amazon, saved after each product scrape |
| `output/reviews_{ASIN}.csv` | All paginated reviews for that ASIN in CSV format |
| `output/reviews_{ASIN}.json` | All paginated reviews for that ASIN in JSON format |
| `logs/scraper.log` | Persistent log file (appended on each run) |

> **Note:** Product data is **not** written to disk — it is returned directly as the API response. Review files are overwritten on each new deep scrape for the same ASIN.

---

## ⚠️ Disclaimer

This project is intended for **educational and personal use only**. Web scraping Amazon may violate their [Conditions of Use](https://www.amazon.in/gp/help/customer/display.html?nodeId=GLSBYFE9MGKKQXXM). Use responsibly and ensure you comply with applicable laws and platform policies.