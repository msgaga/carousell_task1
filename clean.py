from pathlib import Path
import re

import pandas as pd

# 1. Settings
DATA_DIR = Path(__file__).parent / "data"
SITE_FILES = ["luxlexicon", "carousellluxury"]

BRAND_FIXES = {                   # misspelled or inconsistent brand names on the sites
    "ALAïA":              "Alaïa",
    "Faure Le page":      "Faure Le Page",
    "Gucci X Balenciaga": "Gucci x Balenciaga",
    "See By Chole":       "See By Chloé",
    "Lab Diamond":        "Unbranded (lab-grown diamond)",
    "St Louis":           "Saint-Louis",
}
SITE_CATEGORIES = [               # category names the sites write in their descriptions
    "Small Leather Goods", "Bags", "Accessories", "Apparel", "Jewellery", "Watches", "Tableware", "Shoes",
]
TYPE_KEYWORDS = {                 # fallback only: product_type keyword -> category, checked in this order
    "Accessories":         ["accessory", "charm", "scarf", "twilly", "belt", "strap"],
    "Bags":                ["bag", "tote", "clutch", "backpack", "pouch", "wallet on chain", "luggage"],
    "Small Leather Goods": ["wallet", "card holder", "coin purse"],
    "Jewellery":           ["ring", "bracelet", "necklace", "earring", "pendant", "brooch"],
    "Watches":             ["watch"],
    "Tableware":           ["tray", "plate", "bowl", "cup", "homeware", "tableware"],
}
SHOE_KEYWORDS = ["sandal", "sneaker", "heel", "loafer", "boot", "flat", "mule", "pump", "shoe"]
NOT_BAG_TYPES = ["ring", "necklace", "bracelet", "wallet", "scarf", "belt", "strap", "change tray"]  # never "Bags"
CONDITION_PATTERN = r"\b(brand new|like new|excellent|very good|good|fair|poor)\b"   # "very good" before "good"
PRICE_BANDS = [                   # (upper limit in SGD, label)
    (1000,         "<1k"),
    (3000,         "1k-3k"),
    (5000,         "3k-5k"),
    (10000,        "5k-10k"),
    (20000,        "10k-20k"),
    (float("inf"), "20k+"),
]
AGE_BANDS = [                     # (upper limit in months in stock, label)
    (1,            "0-1 mo"),
    (3,            "2-3 mo"),
    (6,            "4-6 mo"),
    (12,           "7-12 mo"),
    (float("inf"), "13+ mo"),
]


# 2. Brand: fix spelling, and roll collaborations up to the main brand
#    e.g. "Louis Vuitton x Yayoi Kusama" -> "Louis Vuitton"
def clean_brand(vendor: str) -> str:
    name = BRAND_FIXES.get(vendor, vendor).strip()
    return name.split(" x ")[0]


# 3. Read the category and product type the site wrote in the description (blank if not found)
def read_description(site: str, description: str) -> tuple[str, str]:
    if site == "LuxLexicon":
        parts = description.split(" | ")            # "Model | Category | Type | Material | ..."
        if len(parts) >= 3:
            return parts[1], parts[2]
        return "", ""
    for category in SITE_CATEGORIES:                # Carousell Luxury: "Bags Chanel Classic ..."
        if description.startswith(category):
            return category, ""
    return "", ""


# 4. Fallback: guess the category from the product type, e.g. "Ring" -> "Jewellery"
def category_from_type(product_type: str) -> str:
    text = product_type.lower()
    for category, keywords in TYPE_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return category
    return "Other"


# 5. Correct clear misfiles in the site's category; otherwise the site's label is kept
#    (brand conventions stay, e.g. Hermès files "Constance To Go" under Small Leather Goods)
def correct_category(category: str, product_type: str) -> str:
    text = product_type.lower()
    is_bag = text.endswith("bag") or text == "backpack"
    if is_bag and category in ("Accessories", "Jewellery"):        # e.g. a vanity bag filed as Jewellery
        return "Bags"
    if not is_bag and any(word in text for word in SHOE_KEYWORDS):   # footwear gets its own category
        return "Shoes"
    if category == "Bags" and text in NOT_BAG_TYPES:                  # e.g. a ring filed as Bags
        return category_from_type(product_type)
    return category


# 6. Condition grade from the description, e.g. "Very Good Condition" -> "Very Good"
def find_condition(description: str) -> str:
    match = re.search(CONDITION_PATTERN, description.lower())
    return match.group(1).title() if match else "Unknown"


# 7. Price band, e.g. 4120 -> "3k-5k"
def price_band(price: float) -> str:
    for upper_limit, label in PRICE_BANDS:
        if price < upper_limit:
            return label


# 8. Months in stock, from the intake year-month coded in the SKU: "CL2604-..." = Apr 2026
#    (Shopify's created date isn't used: 527 LuxLexicon products were re-created on one day in Jan 2026)
def months_in_stock(sku: str, snapshot: str) -> int | None:
    match = re.match(r"^[A-Z]+(\d{2})(\d{2})-", sku)
    if not match or not 1 <= int(match.group(2)) <= 12:
        return None                                 # SKU without a date code
    year, month = 2000 + int(match.group(1)), int(match.group(2))
    return (int(snapshot[:4]) - year) * 12 + (int(snapshot[5:7]) - month)


# 9. Age band, e.g. 5 months -> "4-6 mo"
def age_band(months: int | None) -> str:
    if months is None:
        return "Unknown"
    for upper_limit, label in AGE_BANDS:
        if months <= upper_limit:
            return label


# 10. Turn one raw row into one clean row: required fields first, then helper fields
def clean_row(row: pd.Series) -> dict:
    site_category, description_type = read_description(row["site"], row["description"])
    product_type = row["product_type"] or description_type or "Other"
    category = site_category or category_from_type(product_type)
    category = correct_category("Other" if category == "Others" else category, product_type)
    price = float(row["price"])
    compare_at = float(row["compare_at_price"] or 0)   # Shopify shows a markdown only if above the price
    months = months_in_stock(row["sku"], row["scraped_at"])
    return {
        # Required fields, in the order the task lists them
        "site":             row["site"],
        "product_name":     " ".join(row["title"].split()),
        "brand":            clean_brand(row["vendor"]),
        "category":         category,
        "product_type":     product_type,
        "price_sgd":        price,
        "condition":        find_condition(row["description"]),
        "url":              row["url"],
        # Helper fields, most used in the analysis first
        "available":        row["available"] == "True",
        "price_band":       price_band(price),
        "age_band":         age_band(months),
        "months_in_stock":  "" if months is None else months,
        "sku":              row["sku"],
        "compare_at_price": compare_at if compare_at > price else "",
        "listed_date":      row["created_at"][:10],
        "product_id":       row["product_id"],
    }


# 11. Main logic: clean each site into its own CSV, then save both together in one Excel file
def run_clean():
    tables = []
    for name in SITE_FILES:
        raw = pd.read_csv(DATA_DIR / f"raw_{name}.csv", dtype=str, keep_default_na=False)
        clean = pd.DataFrame([clean_row(row) for _, row in raw.iterrows()])
        path = DATA_DIR / f"clean_{name}.csv"
        clean.to_csv(path, index=False, encoding="utf-8-sig")
        tables.append(clean)

        print(f"=== {clean['site'][0]}: {len(clean)} rows ({clean['available'].sum()} in stock) -> {path}")
        print("Category:", clean["category"].value_counts().to_dict())
        print("Condition:", clean["condition"].value_counts().to_dict())
        print("Price band:", clean["price_band"].value_counts().to_dict())
        print("Age band:", clean["age_band"].value_counts().to_dict(), "\n")

    combined = pd.concat(tables, ignore_index=True)    # product_id stays text so Excel doesn't round it
    path = DATA_DIR / "clean_combined.xlsx"
    combined.to_excel(path, index=False, sheet_name="Clean_Combined")
    print(f"=== Combined: {len(combined)} rows -> {path}")


if __name__ == "__main__":
    run_clean()
