"""
schema_gap_checker.py — Step 2: Per-URL schema verification

For each URL in a CSV or text file:
  1. Fetches the page (mirrors what Google Rich Results Test reads)
  2. Extracts every @type from JSON-LD <script> blocks
  3. Compares against the required schema list for that page type
  4. Writes one row per URL to schema_gap_report.csv

Usage
-----
  python3 schema_gap_checker.py url.csv
  python3 schema_gap_checker.py url.csv --output my_report.csv
  python3 schema_gap_checker.py url.csv --delay 2 --force-page-type Product

Edit REQUIRED_SCHEMAS below to match the client's required schema list.
Edit SCHEMA_ALIASES to treat equivalent types as the same (e.g. BlogPosting → Article).
"""

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Configuration — edit these to match the client's requirements
# ---------------------------------------------------------------------------

REQUIRED_SCHEMAS: dict[str, set[str]] = {
    "Homepage":   {"Organization", "WebSite"},
    "Product":    {"Product", "BreadcrumbList"},
    "Blog":       {"Article", "BreadcrumbList"},
    "Collection": {"BreadcrumbList"},
    "Page":       {"BreadcrumbList"},
}

# Types that count as an alias for a required type
SCHEMA_ALIASES: dict[str, str] = {
    "BlogPosting":  "Article",
    "NewsArticle":  "Article",
    "TechArticle":  "Article",
    "LocalBusiness": "Organization",
    "Corporation":  "Organization",
}

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; SchemaGapChecker/1.0; "
        "+https://github.com/your-org/site-audit)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Cache-Control": "no-cache",
}

OUTPUT_FIELDS = [
    "url",
    "http_status",
    "page_type",
    "schemas_found",
    "schemas_required",
    "schemas_missing",
    "schemas_extra",
    "gap_count",
    "schema_status",
    "has_microdata",
    "has_rdfa",
    "canonical",
    "notes",
]


# ---------------------------------------------------------------------------
# HTML parser — extracts JSON-LD blocks, canonical, microdata/RDFa signals
# ---------------------------------------------------------------------------

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._in_jsonld = False
        self.jsonld_blocks: list[str] = []
        self._current_script: list[str] = []
        self.canonical: str = ""
        self.has_microdata: bool = False
        self.has_rdfa: bool = False

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        if tag == "script" and attr_dict.get("type") == "application/ld+json":
            self._in_jsonld = True
            self._current_script = []
        if tag == "link" and attr_dict.get("rel") == "canonical" and not self.canonical:
            self.canonical = attr_dict.get("href", "")
        if "itemtype" in attr_dict:
            self.has_microdata = True
        if "typeof" in attr_dict:
            self.has_rdfa = True

    def handle_endtag(self, tag):
        if tag == "script" and self._in_jsonld:
            self.jsonld_blocks.append("".join(self._current_script))
            self._in_jsonld = False
            self._current_script = []

    def handle_data(self, data):
        if self._in_jsonld:
            self._current_script.append(data)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def fetch_page(url: str, timeout: int = 15) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=REQUEST_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = _charset(resp.headers.get_content_charset())
            return resp.status, resp.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except Exception as exc:
        return 0, str(exc)


def _charset(raw: str | None) -> str:
    if raw:
        return raw
    return "utf-8"


def walk_types(node) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        raw = node.get("@type")
        if isinstance(raw, str):
            found.add(raw)
        elif isinstance(raw, list):
            found.update(str(t) for t in raw if t)
        for child in node.values():
            found.update(walk_types(child))
    elif isinstance(node, list):
        for item in node:
            found.update(walk_types(item))
    return found


def extract_schema_types(jsonld_blocks: list[str]) -> set[str]:
    found: set[str] = set()
    for block in jsonld_blocks:
        try:
            data = json.loads(block)
        except (json.JSONDecodeError, ValueError):
            continue
        found.update(walk_types(data))
    return found


def normalise(types: set[str]) -> set[str]:
    return {SCHEMA_ALIASES.get(t, t) for t in types}


def detect_page_type(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    if not path:
        return "Homepage"
    if "/products/" in path:
        return "Product"
    if any(seg in path for seg in ("/blogs/", "/blog/", "/articles/", "/news/")):
        return "Blog"
    if any(seg in path for seg in ("/collections/", "/category/", "/categories/")):
        return "Collection"
    return "Page"


def analyse_url(url: str, force_page_type: str | None, delay: float) -> dict:
    status, html = fetch_page(url)

    row: dict = {f: "" for f in OUTPUT_FIELDS}
    row["url"] = url
    row["http_status"] = status

    page_type = force_page_type or detect_page_type(url)
    row["page_type"] = page_type

    if not html or status == 0:
        required = REQUIRED_SCHEMAS.get(page_type, set())
        row["schemas_required"] = _join(sorted(required))
        row["schemas_missing"] = _join(sorted(required))
        row["gap_count"] = len(required)
        row["schema_status"] = "ERROR"
        row["notes"] = f"Fetch failed (status {status})"
        time.sleep(delay)
        return row

    parser = PageParser()
    parser.feed(html)

    found_raw = extract_schema_types(parser.jsonld_blocks)
    found_norm = normalise(found_raw)
    required = REQUIRED_SCHEMAS.get(page_type, set())
    missing = required - found_norm
    extra = found_norm - required

    row["schemas_found"] = _join(sorted(found_raw))
    row["schemas_required"] = _join(sorted(required))
    row["schemas_missing"] = _join(sorted(missing))
    row["schemas_extra"] = _join(sorted(extra))
    row["gap_count"] = len(missing)
    row["schema_status"] = "PASS" if not missing else "FAIL"
    row["has_microdata"] = parser.has_microdata
    row["has_rdfa"] = parser.has_rdfa
    row["canonical"] = parser.canonical

    notes = []
    if parser.has_microdata:
        notes.append("microdata present")
    if parser.has_rdfa:
        notes.append("RDFa present")
    row["notes"] = "; ".join(notes)

    time.sleep(delay)
    return row


# ---------------------------------------------------------------------------
# URL loading
# ---------------------------------------------------------------------------

def load_urls(path: Path) -> list[str]:
    if path.suffix.lower() == ".csv":
        return _load_csv(path)
    return _load_text(path)


def _load_csv(path: Path) -> list[str]:
    urls = []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(2048)
        fh.seek(0)
        try:
            has_header = csv.Sniffer().has_header(sample)
        except csv.Error:
            has_header = False
        if has_header:
            reader = csv.DictReader(fh)
            for row in reader:
                url = (
                    row.get("url")
                    or row.get("URL")
                    or row.get("Address")
                    or next(iter(row.values()), "")
                )
                if url:
                    urls.append(url.strip())
        else:
            reader = csv.reader(fh)
            for row in reader:
                if row:
                    val = row[0].strip()
                    if val.lower().startswith("http"):
                        urls.append(val)
    return [u for u in urls if u]


def _load_text(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _join(items) -> str:
    return " | ".join(str(i) for i in items)


def _print_row_summary(row: dict, idx: int, total: int) -> None:
    status_icon = {"PASS": "✓", "FAIL": "✗", "ERROR": "!"}.get(
        str(row["schema_status"]), "?"
    )
    missing = row["schemas_missing"] or "—"
    print(
        f"  [{idx}/{total}] {status_icon} {row['schema_status']:5}  "
        f"{row['page_type']:12}  {row['url']}"
    )
    if row["schema_status"] == "FAIL":
        print(f"            missing: {missing}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Schema gap checker — compares detected schemas against required list."
    )
    parser.add_argument("input", help="CSV or .txt file with URLs to check")
    parser.add_argument(
        "--output", default="schema_gap_report.csv", help="Output CSV path"
    )
    parser.add_argument(
        "--delay", type=float, default=1.5, help="Seconds to wait between requests"
    )
    parser.add_argument(
        "--force-page-type",
        dest="force_page_type",
        default=None,
        help="Override page-type detection (e.g. Product, Blog, Collection)",
    )
    args = parser.parse_args()

    input_path = Path(args.input).expanduser()
    if not input_path.exists():
        sys.exit(f"Error: input file not found: {input_path}")

    urls = load_urls(input_path)
    if not urls:
        sys.exit("Error: no URLs found in input file.")

    total = len(urls)
    print(f"Schema Gap Checker — {total} URL(s) to check")
    print(f"Output: {args.output}\n")

    output_path = Path(args.output)
    results: list[dict] = []

    with output_path.open("w", newline="", encoding="utf-8") as out_fh:
        writer = csv.DictWriter(out_fh, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()

        for i, url in enumerate(urls, 1):
            row = analyse_url(url, args.force_page_type, args.delay)
            _print_row_summary(row, i, total)
            writer.writerow(row)
            results.append(row)

    # Summary
    passes = sum(1 for r in results if r["schema_status"] == "PASS")
    fails  = sum(1 for r in results if r["schema_status"] == "FAIL")
    errors = sum(1 for r in results if r["schema_status"] == "ERROR")
    print(f"\nDone. PASS: {passes}  FAIL: {fails}  ERROR: {errors}")
    print(f"Report saved to: {output_path.resolve()}")


if __name__ == "__main__":
    main()
