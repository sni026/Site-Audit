# Site Audit

A Scrapy project for SEO/AEO site auditing. Three spiders cover different audit needs — from a quick spot-check of specific URLs through to a full structured-data audit with schema validation.

## Project structure

```
site_audit/
├── scrapy.cfg
├── urls.csv                  # URL list for schema_audit
└── site_audit/
    ├── settings.py
    └── spiders/
        ├── full_site_spider.py     # Full site crawl
        ├── url_list_spider.py      # Quick spot-check
        └── schema_audit_spider.py  # Targeted audit with schema detection
```

## Spiders

### `schema_audit` — targeted audit with schema detection

Audits a specific list of URLs. Accepts URLs inline or from a CSV/text file. Does not follow links.

**Output columns**

| Column | Description |
|---|---|
| `url` | Page URL |
| `status` | HTTP status code |
| `page_type` | Product / Blog / Collection / Page |
| `title` | `<title>` tag text |
| `title_len` | Character count of title |
| `meta_description` | Meta description content |
| `meta_description_len` | Character count of meta description |
| `h1` | First H1 text |
| `h1_count` | Number of H1 tags |
| `all_h1s` | All H1s joined by ` \| ` |
| `body_word_count` | Visible body word count (excludes scripts, styles, SVGs) |
| `schema_types` | All `@type` values found in JSON-LD, sorted and joined by ` \| ` |
| `has_product_schema` | `True` if Product schema present |
| `has_faqpage_schema` | `True` if FAQPage schema present |
| `has_article_schema` | `True` if Article schema present |
| `canonical` | Canonical URL if set |

**Usage**

```bash
# From a CSV file (url column or first column):
scrapy crawl schema_audit -a url_file=urls.csv -o output.csv

# From a plain text file (one URL per line):
scrapy crawl schema_audit -a url_file=urls.txt -o output.csv

# Inline comma-separated URLs:
scrapy crawl schema_audit -a urls="https://your-site.com/products/x,https://your-site.com/blogs/y" -o output.csv

# Falls back to start_urls if no argument is passed:
scrapy crawl schema_audit -o output.csv
```

---

### `full_site` — full site crawl

Crawls the entire domain by following every internal link from the homepage. Use this to get a broad inventory of all pages.

**Output columns:** `url`, `status`, `page_type`, `title`, `title_len`, `h1`, `h1_count`, `meta_description`, `meta_description_len`, `canonical`

```bash
scrapy crawl full_site -o output.csv
```

---

### `urllist` — quick spot-check

A lightweight spider for one-off checks. Edit the `start_urls` list directly in the file and run.

**Output columns:** `url`, `status`, `title`, `h1`, `meta_description`, `canonical`

```bash
scrapy crawl urllist -o output.csv
```

---

## Setup

**Requirements:** Python 3.9+

```bash
# Clone and enter the project
cd site_audit

# Install Scrapy and inject python-dotenv into its environment
pipx install scrapy
pipx inject scrapy python-dotenv

# Configure your target site
cp .env.example .env
# Edit .env and set AUDIT_START_URL and AUDIT_ALLOWED_DOMAIN

# Run a spider
scrapy crawl schema_audit -a url_file=urls.csv -o output.csv
```

## Configuration

Copy `.env.example` to `.env` and set the two variables:

```
AUDIT_START_URL=https://your-site.com/
AUDIT_ALLOWED_DOMAIN=your-site.com
```

`.env` is gitignored and never committed. `.env.example` is the committed template.

## URL list format

`schema_audit` accepts CSV files with a `url` or `URL` header, or with URLs in the first column (no header). It also accepts plain text files with one URL per line — lines starting with `#` are treated as comments and skipped.

Example `urls.csv`:
```
url
https://your-site.com/products/some-product
https://your-site.com/collections/some-collection
https://your-site.com/blogs/some-post
```

## Output formats

Scrapy supports multiple output formats via the `-o` flag:

```bash
-o output.csv       # CSV
-o output.json      # JSON
-o output.jsonl     # JSON Lines (one object per line)
```
