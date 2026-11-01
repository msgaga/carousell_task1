from datetime import datetime, timezone
from html import unescape
from pathlib import Path
import csv
import re
import time

import requests

# 1. Settings
SITES = {
    "LuxLexicon":       "https://luxlexicon.com",
    "Carousell Luxury": "https://carousellluxury.com",
}
PAGE_SIZE = 250                   # Shopify's maximum number of products per page
PAUSE_SECONDS = 3                 # wait between requests so we don't overload the sites
MAX_RETRIES = 3                   # retries per page if the site rate-limits us
OUTPUT_DIR = Path(__file__).parent / "data"
HEADERS = {"User-Agent": "Mozilla/5.0 (one-off inventory snapshot for a take-home assessment)"}


# 2. Download one page of the Shopify products feed, waiting and retrying if rate-limited
def fetch_page(base_url: str, page: int) -> list:
    url = f"{base_url}/products.json"
    params = {"limit": PAGE_SIZE, "page": page}
    for attempt in range(1, MAX_RETRIES + 1):
        response = requests.get(url, params=params, headers=HEADERS, timeout=30)
        if response.status_code == 429:                       # 429 = too many requests
            wait = int(response.headers.get("Retry-After", 60))
            print(f"  rate-limited, waiting {wait}s (attempt {attempt}/{MAX_RETRIES})")
            time.sleep(wait)
            continue
        response.raise_for_status()                           # stop on any other error
        return response.json()["products"]
    raise RuntimeError(f"Gave up on {url} page {page} after {MAX_RETRIES} attempts")


# 3. Turn the HTML product description into plain text
def html_to_text(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")                # remove <tags>
    return re.sub(r"\s+", " ", unescape(text)).strip()        # "&amp;" -> "&", squash spaces


# 4. Turn one product from the feed into one flat CSV row
def flatten(site: str, base_url: str, product: dict) -> dict:
    variant = product["variants"][0] if product["variants"] else {}   # one unique item = one variant
    tags = product.get("tags", [])
    return {
        "site":             site,
        "product_id":       product["id"],
        "title":            product["title"],
        "vendor":           product["vendor"],
        "product_type":     product["product_type"],
        "price":            variant.get("price"),
        "compare_at_price": variant.get("compare_at_price"),
        "available":        variant.get("available"),
        "sku":              variant.get("sku"),
        "variant_count":    len(product["variants"]),
        "tags":             tags if isinstance(tags, str) else ", ".join(tags),
        "description":      html_to_text(product.get("body_html")),
        "url":              f"{base_url}/products/{product['handle']}",
        "created_at":       product.get("created_at"),
        "published_at":     product.get("published_at"),
        "updated_at":       product.get("updated_at"),
    }


# 5. Read one site's feed page by page until a page comes back empty
def scrape_site(site: str, base_url: str) -> list:
    rows = []
    page = 1
    while True:
        products = fetch_page(base_url, page)
        if not products:                                      # empty page = end of catalogue
            break
        rows.extend(flatten(site, base_url, p) for p in products)
        print(f"  page {page}: {len(products)} products (running total {len(rows)})")
        page += 1
        time.sleep(PAUSE_SECONDS)
    return rows


# 6. Save rows to CSV (utf-8-sig so accents like Hermès display correctly)
def save_csv(rows: list, path: Path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


# 7. Main logic
def run_scrape():
    OUTPUT_DIR.mkdir(exist_ok=True)
    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    for site, base_url in SITES.items():
        print(f"Scraping {site} ({base_url}) ...")
        rows = scrape_site(site, base_url)
        for row in rows:
            row["scraped_at"] = scraped_at

        path = OUTPUT_DIR / f"raw_{site.lower().replace(' ', '')}.csv"
        save_csv(rows, path)
        in_stock = sum(1 for r in rows if r["available"])
        print(f"Saved {len(rows)} products ({in_stock} in stock, {len(rows) - in_stock} sold) to {path}\n")


if __name__ == "__main__":
    run_scrape()
