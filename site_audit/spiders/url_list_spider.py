import scrapy

class UrlListSpider(scrapy.Spider):
    name = "urllist"

    start_urls = [
        "https://happyvalley.co.nz/collections/mgo-manuka-honey",
        "https://happyvalley.co.nz/products/manuka-honey-umf-15"
        # add as many URLs as you need
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