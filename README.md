# 🛒 Amazon Product Scraper

A Python-based web scraper that extracts product details from Amazon India (`amazon.in`) — including title, price, ratings, reviews, description, and variants — and exposes the results via a **FastAPI REST API**.

---

## 📁 Project Structure

```
WEB-SCRAPING/
├── logs/
│   └── scraper.log              # Log file output (auto-generated)
├── output/
│   └── source.html              # Raw HTML response saved for debugging (auto-generated)
├── src/
│   ├── classes/
│   │   ├── Product.py           # Pydantic product model
│   │   ├── Scraper.py           # Core scraping logic
│   │   ├── ScrapeRequest.py     # Pydantic request body model
│   │   └── Settings.py          # Environment-based settings (pydantic-settings)
│   ├── config/
│   │   ├── constants.py         # HTTP headers & directory constants
│   │   └── selectors.py         # BeautifulSoup CSS selectors
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

- Validates that the URL belongs to `amazon.in`
- Scrapes the following product fields:
  - **Title**
  - **Price** (integer part + fraction, cleaned and parsed as float)
  - **Ratings** (out of 5)
  - **Review count**
  - **Description** (paragraph or feature bullet points, whichever is available)
  - **Variants** (Color, Size, Style, etc.) — with multi-strategy extraction including a-state JSON fallback
- Saves raw HTML response for debugging (`output/source.html`)
- Environment-aware logging — JSON logs in production, human-readable standard format in development
- Named loggers per module for clean, traceable log output
- REST API with FastAPI — interactive docs available at `/docs`

---

## 🔧 Requirements

- Python 3.12
- [Pipenv](https://pipenv.pypa.io/en/latest/)

### Dependencies (from `Pipfile`)

| Package | Purpose |
|---|---|
| `requests` | HTTP requests |
| `beautifulsoup4` | HTML parsing |
| `pydantic` | Product data model & validation |
| `pydantic-settings` | Environment-based settings |
| `python-json-logger` | JSON log formatter for production |
| `fastapi` | REST API framework |
| `uvicorn` | ASGI server to run FastAPI |

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

### 3. Configure environment variables

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

---

## 🌐 API Endpoints

### `GET /`

Returns a simple HTML welcome page.

**Response:**
```html
<h2>Amazon Web-Scraper</h2>
<p>Welcome to home page!!</p>
```

---

### `POST /api/scrape`

Scrapes product details from a given Amazon India URL.

**Request Body (JSON):**
```json
{
    "url": "https://www.amazon.in/Samsung-Storage-Privacy-Creative-Snapdragon/dp/B0GL8FNY5G/ref=pd_sbs_d_sccl_1_1/523-0876978-0970865?pd_rd_w=l8J0r&content-id=amzn1.sym.d1406b44-aa69-47e4-9270-f613e12d52dc&pf_rd_p=d1406b44-aa69-47e4-9270-f613e12d52dc&pf_rd_r=KVGE0ATT2KXHC21KGJFK&pd_rd_wg=6Z2l0&pd_rd_r=a32fd6c0-1af1-4be1-97ec-850ec1a58421&pd_rd_i=B0GL8FNY5G&th=1"
}
```

**Success Response — `200 OK`:**
```json
{
    "title": "Samsung Galaxy S26 Ultra 5G (Black, 12GB RAM, 256GB Storage) with Built-in Privacy Display, AI Phone, Photo Assist, Creative Studio, 200MP Camera, 5000mAh Battery and Snapdragon 8 Elite Gen 5",
    "price": 130999.0,
    "ratings": 4.5,
    "reviews_count": 158,
    "description": "Built-in Privacy Display - Say hi to world's first Privacy Display on mobile. With this new layer of privacy, one can customize its screen with multiple viewability settings to ensure your everyday moments remain truly yours. Experience complete control with defense grade Knox security, on device protection and enjoy fast, reliable and secure payment anywhere with Samsung Wallet. Agentic AI Experience - Enjoy the pinnacle of mobile AI innovation with the easiest and effortless AI phone built to simplify everyday interactions and inspire confidence as the all-new Galaxy AI becomes truly intuitive and adaptive. The new Now Nudge intelligently reduces the steps and offers real-time suggestions. Find exactly what you are looking in just one quick search with Finder feature on Home screen. Add to it, the new One UI 8.5 personalizes your Galaxy in just a tap. 200MP High Resolution Camera - Capture bright, detailed videos even at night with the brightest camera system and enhanced noise reduction solution. Now, easily edit your photos with Photo Assist or create personalized stickers from photos in a simple tap with Creative Studio, get the best end to end Camera experience. Snapdragon 8 Elite Gen 5 for Galaxy - Play graphic heavy games for long without ever worrying about your device at it now comes with the most powerful, customized processor and a newly designed Vapor Chamber. Galaxy S26 Ultra has Super Fast charging 3.0 supporting up to 60W charging speed and Super Fast Wireless charging supporting up to 25W charging speed, indeed ultra fast charging. Ultra Modern, Sleek Design - A balanced design crafted with a new ambient island camera design and an Armor Aluminum frame fitted with Corning Gorilla Glass, and with stunning galaxy inspired colors, the Galaxy S26 Ultra is our slimmest Ultra yet.",
    "variants": [
        {
            "type": "Color",
            "options": [
                "Black",
                "Cobalt Violet",
                "Sky Blue",
                "White"
            ]
        },
        {
            "type": "Size",
            "options": [
                "12GB + 256GB",
                "12GB + 512GB"
            ]
        },
        {
            "type": "Style",
            "options": [
                "Other Offers",
                "With exchange bonus or No cost EMI"
            ]
        }
    ]
}
```

**Error Responses:**

| Status | Reason |
|---|---|
| `400 Bad Request` | URL is not from `amazon.in` |
| `422 Unprocessable Entity` | Page was blocked or product data could not be extracted |
| `500 Internal Server Error` | Unexpected scraper error |

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
        "url": "https://www.amazon.in/Samsung-Storage-Privacy-Creative-Snapdragon/dp/B0GL8FNY5G/ref=pd_sbs_d_sccl_1_1/523-0876978-0970865?pd_rd_w=l8J0r&content-id=amzn1.sym.d1406b44-aa69-47e4-9270-f613e12d52dc&pf_rd_p=d1406b44-aa69-47e4-9270-f613e12d52dc&pf_rd_r=KVGE0ATT2KXHC21KGJFK&pd_rd_wg=6Z2l0&pd_rd_r=a32fd6c0-1af1-4be1-97ec-850ec1a58421&pd_rd_i=B0GL8FNY5G&th=1"
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

https://www.amazon.in/CREATIVE-QUBE-Engineered-Prime-Desk/dp/B0F5QLS6SB/?_encoding=UTF8&pd_rd_w=OAhqy
```

## ❌ Invalid URL Examples

```
https://www.amazon.com/dp/B09XYZ1234   # Wrong domain (.com not .in)

http://flipkart.com/product/xyz         # Not Amazon

ftp://www.amazon.in/dp/B0DSKL9MQ8      # Invalid scheme
```

---

## 🗂️ How It Works

1. **URL validation** — `Scraper.check_amazon_url()` checks scheme (`http`/`https`) and domain (`amazon.in` or subdomains).
2. **HTTP request** — A `requests.Session` with browser-like headers fetches the page HTML.
3. **Parsing** — `BeautifulSoup` with the `html.parser` backend parses the response.
4. **Field extraction** — Each field has its own method with fallback strategies:
   - Price: searches `corePriceDisplay_desktop_feature_div` → `priceToPay` span → whole/fraction spans.
   - Ratings: tries `acrPopover` then `a-icon-alt`.
   - Description: tries `productDescription` div, then builds from `feature-bullets`.
   - Variants: reads `inline-twister-row-*` divs with title/img-alt/swatch-span/text priority, falling back to the `a-state` JSON embedded in the page.
5. **Output** — `Product` is a Pydantic model; `.to_dict()` serializes it and FastAPI returns it as a JSON response.

---

## 🪵 Logging

Logging is configured centrally in `utils/logger.py` using Python's `dictConfig`. Each module gets its own named logger:

```python
from utils.logger import get_logger
logger = get_logger("MY_MODULE")
```

- `urllib3` logs are suppressed below `WARNING` to reduce noise.
- Log level and format are controlled by the `LOG_LEVEL` and `ENV` environment variables.
- `setup_logging()` must be called once at startup (already done in `main.py`).

---

## 📦 Output Files

| File | Description |
|---|---|
| `output/source.html` | Raw HTML fetched from Amazon, saved for debugging |
| `logs/scraper.log` | Persistent log file (appended on each run) |

> **Note:** Product data is **not** written to disk. It is returned directly as the API response.

---

## ⚠️ Disclaimer

This project is intended for **educational and personal use only**. Web scraping Amazon may violate their [Terms of Service](https://www.amazon.in/gp/help/customer/display.html?nodeId=GLSBYFE9MGKKQXXM). Use responsibly and ensure you comply with applicable laws and platform policies.