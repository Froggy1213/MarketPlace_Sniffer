import asyncio
import logging
import random
from typing import List, Dict, Type
from playwright.async_api import async_playwright

from .base import BaseParser, Platform, ItemData
from .rakuma import RakumaParser
from .rakuten import RakutenParser
from .paypay import PayPayParser
from .mercari import MercariParser
from .yahoo import YahooParser

logger = logging.getLogger(__name__)


class ParserFactory:
    """Registry for all available marketplace parsers."""
    _PARSERS: Dict[Platform, Type[BaseParser]] = {
        Platform.MERCARI: MercariParser,
        Platform.YAHOO: YahooParser,
        Platform.RAKUMA: RakumaParser,
        Platform.RAKUTEN: RakutenParser,
        Platform.PAYPAY: PayPayParser,
    }

    @classmethod
    def get_parser(cls, url: str) -> BaseParser:
        if "mercari.com" in url:
            return cls._PARSERS[Platform.MERCARI]()
        elif "paypayfleamarket" in url:
            return cls._PARSERS[Platform.PAYPAY]()
        elif "yahoo.co.jp" in url:
            return cls._PARSERS[Platform.YAHOO]()
        elif "fril.jp" in url:
            return cls._PARSERS[Platform.RAKUMA]()
        elif "rakuten.co.jp" in url:
            return cls._PARSERS[Platform.RAKUTEN]()
        raise ValueError(f"No parser plugin found for URL: {url}")


async def parse_multiple_urls(urls: List[str], max_items: int = 10) -> Dict[str, List[ItemData]]:
    """
    Optimized Entrypoint: Launches Chromium ONCE and reuses the context
    to parse multiple URLs sequentially. Includes anti-ban delays.
    """
    results: Dict[str, List[ItemData]] = {}
    if not urls:
        return results

    shuffled_urls = list(urls)
    random.shuffle(shuffled_urls)

    logger.info(f"🚦 Starting browser engine for {len(urls)} URLs")

    # Resource Optimization: Start Playwright and Browser ONLY ONCE per task cycle
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-gpu']
        )
        try:
            # Create a single anonymous incognito context
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080},
                locale='ja-JP',
                timezone_id='Asia/Tokyo'
            )

            # Anti-ban stealth script applied to all pages in this context
            await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            # Block media to save bandwidth
            await context.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2}", lambda route: route.abort())

            # Loop through URLs using the same context
            for i, url in enumerate(shuffled_urls):
                logger.info(f"🔎 [{i + 1}/{len(urls)}] Parsing: {url}")
                page = await context.new_page()

                try:
                    parser = ParserFactory.get_parser(url)
                    # Pass the ready-to-use page to the specific plugin
                    items = await parser.parse_page(url, page, max_items)
                    results[url] = items
                except Exception as e:
                    logger.error(f"Failed to process URL {url}: {e}", exc_info=True)
                    results[url] = []
                finally:
                    await page.close()  # Always close the tab to free RAM

                # Apply Anti-Ban Throttling
                if i < len(shuffled_urls) - 1:
                    sleep_time = random.uniform(5, 12)
                    logger.info(f"💤 Throttling... Sleeping for {sleep_time:.1f}s")
                    await asyncio.sleep(sleep_time)

        finally:
            await browser.close()

    return results