import csv
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import scrapy
from dotenv import load_dotenv

load_dotenv()

_START_URL = os.environ.get("AUDIT_START_URL", "https://example.com/")
_ALLOWED_DOMAIN = os.environ.get("AUDIT_ALLOWED_DOMAIN", "example.com")


class SchemaAuditSpider(scrapy.Spider):
    name = "schema_audit"
    allowed_domains = [_ALLOWED_DOMAIN]

    custom_settings = {
        "ROBOTSTXT_OBEY": True,
        "COOKIES_ENABLED": False,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "DOWNLOAD_DELAY": 1,
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en",
        },
    }

    start_urls = [_START_URL]

    schema_types_to_check = ("Product", "FAQPage", "Article")
    def __init__(self, urls=None, url_file=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.audit_urls = self._load_urls(urls=urls, url_file=url_file)

    async def start(self):
        for url in self.audit_urls:
            yield scrapy.Request(
                url,
                callback=self.parse,
                headers={
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                },
            )

    def parse(self, response):
        title = self._first_text(response.css("title::text").get())
        meta_description = self._meta_description(response)
        h1s = self._clean_list(response.css("h1::text").getall())
        body_text = self._body_text(response)
        word_count = self._word_count(body_text)
        schema_types = self._schema_types(response)
        schema_flags = {
            f"has_{schema_type.lower()}_schema": schema_type in schema_types
            for schema_type in self.schema_types_to_check
        }

        yield {
            "url": response.url,
            "status": response.status,
            "page_type": self._page_type(response.url),
            "title": title,
            "title_len": len(title),
            "meta_description": meta_description,
            "meta_description_len": len(meta_description),
            "h1": h1s[0] if h1s else "",
            "h1_count": len(h1s),
            "all_h1s": " | ".join(h1s),
            "body_word_count": word_count,
            "schema_types": " | ".join(sorted(schema_types)),
            **schema_flags,
            "canonical": response.css("link[rel='canonical']::attr(href)").get(
                default=""
            ),
        }

    def _load_urls(self, urls=None, url_file=None):
        if urls:
            return [url.strip() for url in urls.split(",") if url.strip()]

        if url_file:
            path = Path(url_file).expanduser()
            if not path.exists():
                raise ValueError(f"URL file does not exist: {path}")
            if path.suffix.lower() == ".csv":
                return self._load_urls_from_csv(path)
            return [
                line.strip()
                for line in path.read_text(encoding="utf-8-sig").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]

        return self.start_urls

    def _load_urls_from_csv(self, path):
        urls = []
        with path.open(newline="", encoding="utf-8-sig") as handle:
            sample = handle.read(2048)
            handle.seek(0)
            try:
                has_header = csv.Sniffer().has_header(sample)
            except csv.Error:
                has_header = False
            if has_header:
                reader = csv.DictReader(handle)
                for row in reader:
                    url = (
                        row.get("url")
                        or row.get("URL")
                        or next(iter(row.values()), "")
                    )
                    if url:
                        urls.append(url.strip())
            else:
                reader = csv.reader(handle)
                for row in reader:
                    if row:
                        urls.append(row[0].strip())
        return [url for url in urls if url]

    def _meta_description(self, response):
        description = response.xpath(
            "//meta[translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            "'abcdefghijklmnopqrstuvwxyz')='description']/@content"
        ).get()
        return self._first_text(description)

    def _body_text(self, response):
        text_nodes = response.xpath(
            "//body//*[not(self::script) and not(self::style) and "
            "not(self::noscript) and not(self::template) and not(self::svg)]"
            "/text()[normalize-space()]"
        ).getall()
        return self._first_text(" ".join(text_nodes))

    def _word_count(self, text):
        return len(re.findall(r"\b[\w'-]+\b", text))

    def _schema_types(self, response):
        schema_types = set()
        source = response.text

        for schema_type in self.schema_types_to_check:
            if re.search(rf'"@type"\s*:\s*"{schema_type}"', source):
                schema_types.add(schema_type)

        for script in response.css("script[type='application/ld+json']::text").getall():
            try:
                data = json.loads(script)
            except json.JSONDecodeError:
                continue
            schema_types.update(self._extract_schema_types(data))

        return schema_types

    def _extract_schema_types(self, value):
        found = set()
        if isinstance(value, dict):
            schema_type = value.get("@type")
            if isinstance(schema_type, str):
                found.add(schema_type)
            elif isinstance(schema_type, list):
                found.update(str(item) for item in schema_type)
            for child in value.values():
                found.update(self._extract_schema_types(child))
        elif isinstance(value, list):
            for child in value:
                found.update(self._extract_schema_types(child))
        return found

    def _page_type(self, url):
        path = urlparse(url).path
        if "/products/" in path:
            return "Product"
        if "/blogs/" in path or "/blog/" in path:
            return "Blog"
        if "/collections/" in path:
            return "Collection"
        return "Page"

    def _clean_list(self, values):
        return [cleaned for value in values if (cleaned := self._first_text(value))]

    def _first_text(self, value):
        if not value:
            return ""
        return re.sub(r"\s+", " ", value).strip()

