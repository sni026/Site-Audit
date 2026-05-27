import scrapy

class UrlListSpider(scrapy.Spider):
    name = "urllist"

    start_urls = [
        # Add your URLs here, e.g.:
        # "https://your-site.com/some-page",
        # "https://your-site.com/another-page",
    ]

    def parse(self, response):
        yield {
            "url": response.url,
            "status": response.status,
            "title": response.css("title::text").get(),
            "h1": response.css("h1::text").get(),
            "meta_description": response.css("meta[name='description']::attr(content)").get(),
            "canonical": response.css("link[rel='canonical']::attr(href)").get(),
        }