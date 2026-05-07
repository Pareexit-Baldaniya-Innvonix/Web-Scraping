# 🛒 Amazon Product Scraper

A Python-based web scraper that extracts product details from Amazon India (`amazon.in`) — including title, price, ratings, reviews, description, and variants — and prints the output as structured JSON to stdout.

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
│   │   └── Settings.py          # Environment-based settings (pydantic-settings)
│   ├── config/
│   │   ├── constants.py         # HTTP headers & directory constants
│   │   └── selectors.py         # BeautifulSoup CSS selectors
│   ├── utils/
│   │   └── logger.py            # Centralized logging setup
│   └── main.py                  # Entry point
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

```bash
pipenv run python src/main.py
```

You will be prompted to enter an Amazon India product URL:

```
Enter any amazon product link:
```

### ✅ Valid URL Examples

```
https://www.amazon.in/dp/B0DSKL9MQ8

https://www.amazon.in/CREATIVE-QUBE-Engineered-Prime-Desk/dp/B0F5QLS6SB/?_encoding=UTF8&pd_rd_w=OAhqy&content-id=amzn1.sym.a0f68b74-8e6e-4593-a797-bc3c5271cf5d&pf_rd_p=a0f68b74-8e6e-4593-a797-bc3c5271cf5d&pf_rd_r=1ZNXE77SBGDKN6CNEEQM&pd_rd_wg=bbAYz&pd_rd_r=7d76f586-b838-4eb4-86f3-24c3a85eeadf&th=1
```

### ❌ Invalid URL Examples

```
https://www.amazon.com/dp/B09XYZ1234   # Wrong domain (.com not .in)

http://flipkart.com/product/xyz         # Not Amazon

ftp://www.amazon.in/dp/B0DSKL9MQ8      # Invalid scheme
```

---

## 📦 Output

### stdout — Structured JSON

The scraped product data is printed directly to stdout as formatted JSON:

```json
{
    "title": "75cm Height Engineered Wood Ergonomic Prime Desk for Office Workstation for 2 | Laptop Desk, Gaming Setup, Work from Home, Hostel, Reception, Counter Table | Easy DIY Assembly- White",
    "price": 2499.99,
    "ratings": 4.2,
    "reviews_count": 35,
    "description": "𝗗𝗜𝗬 𝗘𝗮𝘀𝘆 𝗔𝘀𝘀𝗲𝗺𝗯𝗹𝘆: Includes manual + all fittings. Easy setup in 15-30 mins using basic tools. Installation video available on YouTube 𝗠𝗼𝗱𝗲𝗿𝗻 𝗘𝗿𝗴𝗼𝗻𝗼𝗺𝗶𝗰 𝗗𝗲𝘀𝗸: Crafted from high-quality engineered wood with glossy laminated finish; smooth, scratch-resistant, and easy to clean surface ensures long-lasting durability. With dimensions 100L x 50W x 75H CM, Perfect for home, office, hostel, salon, hotel reception, or compact spaces. 𝐒𝐜𝐫𝐚𝐭𝐜𝐡- 𝐑𝐞𝐬𝐢𝐬𝐭𝐚𝐧𝐜𝐞 𝐒𝐮𝐫𝐟𝐚𝐜𝐞: Designed to withstand daily wear and tear, the desk features a scratch-resistant surface that maintains its elegant appearance over time. Elegant design with clean lines, ideal for small rooms, study areas, or work-from-home setups without compromising style or utility. 𝗦𝗺𝗮𝗿𝘁 𝗘𝗱𝗴𝗲-𝗕𝗮𝗻𝗱𝗲𝗱 𝗗𝗲𝘀𝗶𝗴𝗻: All visible and hidden edges are fully edge-banded, protecting against moisture absorption, chipping, and peeling while giving a premium look from every angle. 𝗤𝗨𝗔𝗟𝗜𝗧𝗬 𝗔𝗦𝗦𝗨𝗥𝗔𝗡𝗖𝗘: We provide 1 Year limited warranty against manufacturing defects. Our carefully designed packaging with Bubble Wrap, Foam Sheets And 5-Ply Carton to prevent transit Damage and sides ensures your piece arrives in pristine condition, free from any damage.",
    "variants": [
        {
            "type": "Number Of Items",
            "options": [
                "1",
                "3"
            ]
        }
    ]
}
```

> **Note:** `product.json` is **not** written to disk by default. The JSON output is printed to stdout only. `output/source.html` is the only file auto-saved.

### `output/source.html`

The raw HTML fetched from Amazon is saved here for inspection and debugging.

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

## 🗂️ How It Works

1. **URL validation** — `Scraper.check_amazon_url()` checks scheme (`http`/`https`) and domain (`amazon.in` or subdomains).
2. **HTTP request** — A `requests.Session` with browser-like headers fetches the page HTML.
3. **Parsing** — `BeautifulSoup` with the `html.parser` backend parses the response.
4. **Field extraction** — Each field has its own method with fallback strategies:
   - Price: searches `corePriceDisplay_desktop_feature_div` → `priceToPay` span → whole/fraction spans.
   - Ratings: tries `acrPopover` then `a-icon-alt`.
   - Description: tries `productDescription` div, then builds from `feature-bullets`.
   - Variants: reads `inline-twister-row-*` divs with title/img-alt/swatch-span/text priority, falling back to the `a-state` JSON embedded in the page.
5. **Output** — `Product` is a Pydantic model; `.to_dict()` serializes it and `json.dumps` prints it to stdout.

---

## ⚠️ Disclaimer

This project is intended for **educational and personal use only**. Web scraping Amazon may violate their [Terms of Service](https://www.amazon.in/gp/help/customer/display.html?nodeId=GLSBYFE9MGKKQXXM). Use responsibly and ensure you comply with applicable laws and platform policies.