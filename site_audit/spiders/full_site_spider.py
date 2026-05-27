import os

import scrapy
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()

_START_URL = os.environ.get("AUDIT_START_URL", "https://example.com/")
_ALLOWED_DOMAIN = os.environ.get("AUDIT_ALLOWED_DOMAIN", "example.com")


class FullSiteSpider(scrapy.Spider):
    name = "full_site"
    allowed_domains = [_ALLOWED_DOMAIN]
    start_urls = [_START_URL]
    visited = set()

    def parse(self, response):
        if response.url in self.visited:
            return
        self.visited.add(response.url)

        title = response.css("title::text").get("").strip()
        h1 = response.css("h1::text").get()
        meta_desc = response.css("meta[name='description']::attr(content)").get("").strip()

        yield {
            "url": response.url,
            "status": response.status,
            "page_type": self._page_type(response.url),
            "title": title,
            "title_len": len(title),
            "h1": h1,
            "h1_count": 1 if h1 else 0,
            "meta_description": meta_desc or None,
            "meta_description_len": len(meta_desc),
            "canonical": response.css("link[rel='canonical']::attr(href)").get(),
        }

        for href in response.css("a::attr(href)").getall():
            # Skip non-HTTP URLs (mailto, javascript, etc.)
            if href and not href.startswith(('mailto:', 'javascript:', 'tel:', '#')):
                yield response.follow(href, callback=self.parse)

    def _page_type(self, url):
        if "/products/" in url:
            return "Product"
        if "/blogs/" in url or "/blog/" in url:
            return "Blog"
        if "/collections/" in url:
            return "Collection"
        return "Page"
