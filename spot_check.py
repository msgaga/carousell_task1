from html import unescape
from pathlib import Path
import re
import time

import pandas as pd
import requests

from scrape import HEADERS, PAUSE_SECONDS

# 1. Settings
DATA_DIR = Path(__file__).parent / "data"
SITE_FILES = ["luxlexicon", "carousellluxury"]
SAMPLE_SIZE = 10                  # items checked per site
RANDOM_SEED = 42                  # fixed seed, so the same sample is picked every time
CHECKS = ["page_live", "name_ok", "brand_ok", "price_ok", "condition_ok"]


# 2. Download a product page and return its visible text in lowercase (None if the page is gone)
def page_text(url: str) -> str | None:
    response = requests.get(url, headers=HEADERS, timeout=30)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    text = unescape(re.sub(r"<[^>]+>", " ", response.text))   # remove <tags>, decode "&amp;"
    return " ".join(text.split()).lower()


# 3. Check whether each recorded value appears on the page (True = found)
def check_row(row: pd.Series, text: str) -> dict:
    price = float(row["price_sgd"])
    return {
        "name_ok":      " ".join(row["product_name"].split()).lower() in text,
        "brand_ok":     row["brand"].lower() in text,
        "price_ok":     f"{price:,.2f}" in text or f"{price:,.0f}" in text,     # "3,500.00" or "3,500"
        "condition_ok": row["condition"] == "Unknown" or row["condition"].lower() in text,
    }


# 4. Main logic: check a random in-stock sample per site and save the results
def run_spot_check():
    results = []
    for name in SITE_FILES:
        clean = pd.read_csv(DATA_DIR / f"clean_{name}.csv", dtype=str, keep_default_na=False)
        sample = clean[clean["available"].str.upper() == "TRUE"].sample(SAMPLE_SIZE, random_state=RANDOM_SEED)
        for _, row in sample.iterrows():
            text = page_text(row["url"])
            checks = check_row(row, text) if text else {}
            results.append({"site": row["site"], "product_name": row["product_name"], "brand": row["brand"],
                            "price_sgd": row["price_sgd"], "condition": row["condition"], "url": row["url"],
                            "page_live": text is not None, **checks})
            time.sleep(PAUSE_SECONDS)

    report = pd.DataFrame(results)
    report.to_csv(DATA_DIR / "spot_check.csv", index=False, encoding="utf-8-sig")
    print(report.groupby("site")[CHECKS].sum().to_string())

    failed = report[~report[CHECKS].fillna(False).all(axis=1)]
    print(f"\nRows with any failed check: {len(failed)}")
    if len(failed):
        print(failed[["site", "product_name", "url"] + CHECKS].to_string(index=False))


if __name__ == "__main__":
    run_spot_check()
