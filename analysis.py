from pathlib import Path

import pandas as pd

from clean import AGE_BANDS, DATA_DIR, PRICE_BANDS, SITE_FILES

# 1. Settings
OUTPUT_DIR = Path(__file__).parent / "output"
LL = "LuxLexicon"
CL = "Carousell Luxury"
TOP_BRANDS = 10                   # brand tables show the top 10
MIN_ITEMS_TO_COMPARE = 5          # a brand + category needs 5+ items on BOTH sites to compare prices

BAND_ORDER      = [label for _, label in PRICE_BANDS]     # <1k, 1k-3k ... 20k+
CONDITION_ORDER = ["Brand New", "Like New", "Very Good", "Good", "Fair", "Unknown"]
AGE_ORDER       = [label for _, label in AGE_BANDS] + ["Unknown"]     # 0-1 mo ... 13+ mo
CONTEMPORARY_BRANDS = ["Gucci", "Saint Laurent", "Celine", "Bottega Veneta", "Loewe", "Balenciaga", "Prada", "Miu Miu"]

pd.set_option("display.width", 200)


# 2. Load both clean files and keep only items currently for sale
def load_in_stock() -> pd.DataFrame:
    files = [DATA_DIR / f"clean_{name}.csv" for name in SITE_FILES]
    df = pd.concat([pd.read_csv(file) for file in files], ignore_index=True)
    return df[df["available"]]


# 3. Helper: add a copy of every row labelled "All sites", so tables also show the overall figure
def add_all_sites(df: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([df, df.assign(site="All sites")], ignore_index=True)


# 4. Helper: listings and value per group, with each group's % share within its own site
def share_table(df: pd.DataFrame, column: str) -> pd.DataFrame:
    table = df.groupby(["site", column])["price_sgd"].agg(listings="count", value_sgd="sum")
    site_totals = table.groupby(level="site").transform("sum")
    table["listing_share_%"] = (table["listings"] / site_totals["listings"] * 100).round(1)
    table["value_share_%"] = (table["value_sgd"] / site_totals["value_sgd"] * 100).round(1)
    return table.sort_values(["site", "value_sgd"], ascending=[True, False])


# 5. Headline KPIs: listings, total value and price statistics per site
def headline_kpis(df: pd.DataFrame) -> pd.DataFrame:
    prices = add_all_sites(df).groupby("site")["price_sgd"]
    return prices.agg(listings="count", total_value="sum", median="median",
                      mean="mean", min="min", max="max").round(0)


# 6. Price distribution: % of each site's listings in each price band
def price_band_mix(df: pd.DataFrame) -> pd.DataFrame:
    data = add_all_sites(df)
    shares = pd.crosstab(data["price_band"], data["site"], normalize="columns") * 100   # % within each site
    return shares.reindex(BAND_ORDER).round(1)


# 7. Median price per category or brand, one column per site
def median_price_by(df: pd.DataFrame, column: str) -> pd.DataFrame:
    data = add_all_sites(df)
    return data.pivot_table(index=column, columns="site", values="price_sgd", aggfunc="median").round(0)


# 8. Brand split: top brands per site by inventory value
def brand_split(df: pd.DataFrame) -> pd.DataFrame:
    return share_table(df, "brand").groupby(level="site").head(TOP_BRANDS)


# 9. Brand overlap: is each brand on both sites, or only one?
def brand_overlap(df: pd.DataFrame) -> pd.DataFrame:
    counts = pd.crosstab(df["brand"], df["site"])                      # items per brand per site
    counts["listed_on"] = counts.apply(lambda row: "Both" if row.all() else row.idxmax() + " only", axis=1)
    return counts.sort_values(["listed_on", LL], ascending=[True, False])


# 10. Condition mix per site, with the median price of each grade
def condition_mix(df: pd.DataFrame) -> pd.DataFrame:
    table = share_table(df, "condition")
    table["median_price"] = df.groupby(["site", "condition"])["price_sgd"].median().round(0)
    return table.reindex(CONDITION_ORDER, level="condition")


# 11. Site comparison: same brand + category on both sites, compare median prices
def site_price_comparison(df: pd.DataFrame) -> pd.DataFrame:
    stats = df.groupby(["brand", "category", "site"])["price_sgd"].agg(["count", "median"]).unstack("site")
    stats.columns = [f"{site} {stat}" for stat, site in stats.columns]   # e.g. "LuxLexicon median"
    enough = (stats[f"{LL} count"] >= MIN_ITEMS_TO_COMPARE) & (stats[f"{CL} count"] >= MIN_ITEMS_TO_COMPARE)
    table = stats[enough].copy()
    table["LL vs CL median %"] = (table[f"{LL} median"] / table[f"{CL} median"] - 1) * 100
    return table.round(0).sort_values(f"{LL} count", ascending=False)


# 12. Stock ageing: share of listings per age band, and how many of them are marked down
def stock_ageing(df: pd.DataFrame) -> pd.DataFrame:
    table = share_table(df, "age_band")
    marked_down = df["compare_at_price"].notna()                      # a markdown price is set
    table["marked_down_%"] = (marked_down.groupby([df["site"], df["age_band"]]).mean() * 100).round(1)
    return table.reindex(AGE_ORDER, level="age_band")


# 13. Contemporary brands: listings per brand and site, with a total row (supports takeaway #2)
def contemporary_listings(df: pd.DataFrame) -> pd.DataFrame:
    contemporary = df[df["brand"].isin(CONTEMPORARY_BRANDS)]
    return pd.crosstab(contemporary["brand"], contemporary["site"], margins=True, margins_name="Total")


# 14. One brand's bags: items and median price per condition, per site (supports takeaway #4)
def bag_price_by_condition(df: pd.DataFrame, brand: str) -> pd.DataFrame:
    bags = df[(df["brand"] == brand) & (df["category"] == "Bags")]
    table = bags.groupby(["condition", "site"])["price_sgd"].agg(["count", "median"]).unstack("site")
    table.columns = [f"{site} {stat}" for stat, site in table.columns]   # e.g. "LuxLexicon median"
    return table.reindex(CONDITION_ORDER).dropna(how="all")


# 15. Speed of sale by condition: median months in stock and % marked down (supports takeaway #4)
def condition_speed(df: pd.DataFrame) -> pd.DataFrame:
    data = df.assign(marked_down=df["compare_at_price"].notna())
    table = data.groupby(["site", "condition"]).agg(listings=("price_sgd", "size"),
                                                    median_months_in_stock=("months_in_stock", "median"),
                                                    marked_down_pct=("marked_down", "mean"))
    table["marked_down_pct"] = (table["marked_down_pct"] * 100).round(1)
    return table.reindex(CONDITION_ORDER, level="condition")


# 16. Main logic: build every table, print it and save it to output/
def run_analysis():
    df = load_in_stock()
    top_brand_names = df["brand"].value_counts().head(TOP_BRANDS).index

    tables = {
        "1_kpis":                      headline_kpis(df),
        "2a_price_bands":              price_band_mix(df),
        "2b_median_price_by_category": median_price_by(df, "category"),
        "2c_median_price_by_brand":    median_price_by(df[df["brand"].isin(top_brand_names)], "brand"),
        "3a_brand_split":              brand_split(df),
        "3b_brand_overlap":            brand_overlap(df),
        "4_category_split":            share_table(df, "category"),
        "5_condition_mix":             condition_mix(df),
        "6_site_price_comparison":     site_price_comparison(df),
        "7_stock_ageing":              stock_ageing(df),
        "8_contemporary_brands":       contemporary_listings(df),
        "9a_chanel_bags_by_condition": bag_price_by_condition(df, "Chanel"),
        "9b_hermes_bags_by_condition": bag_price_by_condition(df, "Hermès"),
        "9c_condition_speed":          condition_speed(df),
    }

    OUTPUT_DIR.mkdir(exist_ok=True)
    for name, table in tables.items():
        table.to_csv(OUTPUT_DIR / f"{name}.csv", encoding="utf-8-sig")
        print(f"\n=== {name} ===\n{table.to_string()}")

    print(f"\nDone. {len(tables)} tables saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    run_analysis()
