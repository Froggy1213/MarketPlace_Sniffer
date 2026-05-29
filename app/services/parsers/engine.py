import traceback
import asyncio
import logging
import random
from typing import List, Dict, Type

# Добавили импорт TimeoutError специально из playwright
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

from .base import BaseParser, Platform, ItemData
from .rakuma import RakumaParser
from .rakuten import RakutenParser
from .paypay import PayPayParser
from .mercari import MercariParser
from .yahoo import YahooParser

# Logger instance for this module
logger = logging.getLogger(__name__)


# ============================================================================
# PARSER FACTORY
# ============================================================================

class ParserFactory:
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


# ============================================================================
# MAIN PARSING ENGINE
# ============================================================================

async def parse_multiple_urls(urls: List[str], max_items: int = 10) -> Dict[str, List[ItemData]]:

    results: Dict[str, List[ItemData]] = {}
    
    if not urls:
        return results

    shuffled_urls = list(urls)
    random.shuffle(shuffled_urls)

    logger.info(f"🚦 Starting browser engine for {len(urls)} URLs")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,  
            args=[
                '--disable-blink-features=AutomationControlled',  
                '--no-sandbox',  
                '--disable-gpu'  
            ]
        )
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080},
                locale='ja-JP',
                timezone_id='Asia/Tokyo'
            )

            await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            # Блокируем медиа для экономии трафика
            await context.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2}", lambda route: route.abort())

            for i, url in enumerate(shuffled_urls):
                logger.info(f"🔎 [{i + 1}/{len(urls)}] Parsing: {url}")
                page = await context.new_page()

                try:
                    logger.debug(f"🕸 Начинаю навигацию и парсинг URL: {url}")
                    parser = ParserFactory.get_parser(url)
                    
                    items = await parser.parse_page(url, page, max_items)
                    results[url] = items
                    
                    logger.info(f"✅ Успешно собрано {len(items)} товаров с {url}")
                    
                except PlaywrightTimeoutError:
                    # Специфичный отлов таймаутов (очень часто бывает на маркетплейсах)
                    logger.error(f"⏱ Таймаут при загрузке {url}. Страница слишком тяжелая или IP заблокирован.")
                    results[url] = []
                    
                except Exception as e:
                    # Кратко пишем ошибку в общий лог
                    logger.error(f"🐛 Критическая ошибка парсинга {url}: {str(e)}")
                    # Полный трейсбек прячем в debug, чтобы не мусорить в проде
                    logger.debug(traceback.format_exc())
                    results[url] = []
                    
                finally:
                    # Всегда закрываем вкладку
                    await page.close()

                # Throttling
                if i < len(shuffled_urls) - 1:
                    sleep_time = random.uniform(5, 12)
                    logger.info(f"💤 Throttling... Sleeping for {sleep_time:.1f}s")
                    await asyncio.sleep(sleep_time)

        finally:
            # Всегда закрываем браузер
            await browser.close()

    return results