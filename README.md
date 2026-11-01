# Luxury Inventory Snapshot: LuxLexicon vs Carousell Luxury

Take-home assessment for the Operations Automation Associate role at Carousell Group.
This is a one-off snapshot of the luxury inventory listed on [luxlexicon.com](https://luxlexicon.com) and [carousellluxury.com](https://carousellluxury.com), taken on **29 Oct 2026 at 03:08 UTC**.

**Dashboard:** [Google Sheet](https://docs.google.com/spreadsheets/d/1Dge7bCUUnohqB3CdN8ctenDlLOL_nnA0KkByZe09QMw/edit?usp=sharing). The key takeaways are at the top of the Dashboard tab; the methodology, assumptions and limitations are on the Methodology tab.

## How it works

| Step | Script | What it does | Output |
|---|---|---|---|
| 1 | `scrape.py` | Reads each site's public Shopify product feed (`/products.json`), page by page, with polite pauses and rate-limit retries | `data/raw_*.csv` |
| 2 | `clean.py` | Standardises brand, category (with clear misfiles corrected), condition, price band and stock age; one row per listing, with the required fields first | `data/clean_*.csv`, `data/clean_combined.xlsx` |
| 3 | `spot_check.py` | Checks 10 random in-stock items per site against the live product pages | `data/spot_check.csv` |
| 4 | `analysis.py` | Computes every dashboard table (the answer key for the Google Sheet formulas) and every figure quoted in the key takeaways | `output/1_*.csv` to `7_*.csv` (dashboard sections 1–7), `output/8_*.csv` and `9*_*.csv` (takeaway figures) |

## Run it

The repo includes the raw snapshot from 29 Oct 2026 (`data/raw_*.csv`). To reproduce the dashboard numbers from it, skip the scrape:

```bash
pip install -r requirements.txt
python clean.py
python analysis.py
```

`clean.py` recreates the clean files in `data/`, and `analysis.py` writes the answer-key tables to `output/`.

- `python spot_check.py` compares 10 random items per site with the live product pages. Items sold since the snapshot will show as no longer live.
- `python scrape.py` takes a new snapshot of the live sites. It overwrites `data/raw_*.csv`, so the numbers will differ from the dashboard.

## Folder structure

```
scrape.py, clean.py, spot_check.py, analysis.py   the pipeline (run in this order)
data/      raw snapshot from 29 Oct 2026; clean files are created here by clean.py
output/    analysis tables, created by analysis.py
```
