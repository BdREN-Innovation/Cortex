import asyncio

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode


async def main():
    browser_config = BrowserConfig(
        browser_type="chromium",
        headless=True,
        user_agent="CortexEngine/0.1 (+https://github.com/BdREN-Innovation/Cortex)",
    )

    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        check_robots_txt=True,
        page_timeout=20000,
        wait_until="domcontentloaded",
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url="https://bdren.net.bd/",
            config=run_config,
        )

        print("SUCCESS:", result.success)
        print("STATUS:", result.status_code)
        print("FINAL URL:", result.url)
        print("HTML LENGTH:", len(result.html or ""))

        print("\nINTERNAL LINKS:")
        for link in result.links.get("internal", [])[:10]:
            print(link.get("href"))

        print("\nIMAGES:")
        for image in result.media.get("images", [])[:10]:
            print(image.get("src"))

        print("\nERROR:", result.error_message)


if __name__ == "__main__":
    asyncio.run(main())