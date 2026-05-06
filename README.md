# 🛒 Amazon Product Scraper

A Python-based web scraper that extracts product details from Amazon India (`amazon.in`) — including title, price, ratings, reviews, description, and variants — and saves the output as a structured JSON file.

---

## 📁 Project Structure

```
WEB-SCRAPING/
├── logs/
│   └── scraper.log              # Log file output (auto-generated)
├── output/
│   ├── product.json             # Scraped product data (auto-generated)
│   └── source.html              # Raw HTML response (auto-generated)
├── src/
│   ├── classes/
│   │   ├── Product.py           # Pydantic product model
│   │   ├── Scraper.py           # Core scraping logic
│   │   └── Settings.py          # Environment-based settings (pydantic-settings)
│   ├── config/
│   │   └── constants.py         # HTTP headers & directory constants
│   ├── utils/
│   │   └── logger.py            # Centralized logging setup
│   └── main.py                  # Entry point
├── example.env                  # Example env file for reference
├── .gitignore
└── README.md
```

---

## ✨ Features

- ✅ Validates that the URL belongs to `amazon.in`
- ✅ Scrapes the following product fields:
  - **Title**
  - **Price** (with symbol and fraction)
  - **Ratings** (out of 5)
  - **Review count**
  - **Description** (paragraph or bullet points)
  - **Variants** (Color, Size, Style, etc.)
- ✅ Saves raw HTML response for debugging (`output/source.html`)
- ✅ Exports clean JSON output (`output/product.json`)
- ✅ Environment-aware logging — JSON logs in production, standard in development

---

## 🔧 Requirements

- Python 3.10+
- Dependencies:

```
requests
beautifulsoup4
pydantic
pydantic-settings
python-json-logger
```

Install all dependencies:

```bash
pip install -r requirements.txt
```

---

## ⚙️ Configuration

Settings are controlled via environment variables:

| Variable    | Default       | Description                          |
|-------------|---------------|--------------------------------------|
| `LOG_LEVEL` | `DEBUG`       | Logging level (`DEBUG`, `INFO`, etc.) |
| `ENV`       | `development` | Environment (`development` / `production`) |

In `production`, logs are emitted as **JSON**. In `development`, logs use a human-readable **standard** format.

You can set these in a `.env` file or export them directly:

```bash
ENV=production
LOG_LEVEL=INFO
```

---

## 🚀 Usage

```bash
python src/main.py
```

You will be prompted to enter an Amazon India product URL:

```
Enter any amazon product link: https://www.amazon.in/dp/XXXXXXXXXX
```

### ✅ Valid URL Examples

```
https://www.amazon.in/dp/B09XYZ1234
https://amazon.in/gp/product/B09XYZ1234
```

### ❌ Invalid URL Examples

```
https://www.amazon.com/dp/B09XYZ1234   # Wrong domain
http://flipkart.com/product/xyz         # Not Amazon
```

---

## 📦 Output

### `output/product.json`

```json
{
    "title": "Product Name Here",
    "price": "₹1,499.00",
    "ratings": "4.2 out of 5 stars",
    "reviews": "3,512 ratings",
    "description": [
        "Feature one about the product",
        "Feature two about the product"
    ],
    "variants": [
        {
            "type": "Color",
            "options": ["Black", "White", "Blue"]
        },
        {
            "type": "Size",
            "options": ["Small", "Medium", "Large"]
        }
    ]
}
```

### `output/source.html`

The raw HTML fetched from Amazon, saved for inspection or debugging.

---

## 🪵 Logging

Logging is handled centrally via `utils/logger.py`. Each module gets its own named logger:

```python
from utils.logger import get_logger
logger = get_logger("MY_MODULE")
```

- `urllib3` logs are suppressed below `WARNING` to reduce noise.
- Log level and format are driven by the `LOG_LEVEL` and `ENV` environment variables.

---

## ⚠️ Disclaimer

This project is intended for **educational and personal use only**. Web scraping Amazon may violate their [Terms of Service](https://www.amazon.in/gp/help/customer/display.html?nodeId=508088). Use responsibly and ensure you comply with applicable laws and platform policies.