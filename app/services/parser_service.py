import asyncio
import logging
import re
import random
from typing import List, Dict, Optional, Type
from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Browser, Page, Playwright
from enum import Enum

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Platform(Enum):
    """Поддерживаемые платформы"""
    MERCARI = "mercari"
    YAHOO = "yahoo"
    UNKNOWN = "unknown"

@dataclass
class ItemData:
    """Универсальная структура товара"""
    market_id: str
    title: str
    price: int
    url: str
    platform: str
    image_url: Optional[str] = None
    status: str = "available"
    
    def to_dict(self) -> Dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

class ParserError(Exception):
    pass

class BaseParser(ABC):
    PLATFORM: Platform = Platform.UNKNOWN
    
    def __init__(self, headless: bool = True, timeout: int = 30000, max_retries: int = 3):
        self.headless = headless
        self.timeout = timeout
        self.max_retries = max_retries
        self.user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

    @asynccontextmanager
    async def _browser_context(self):
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-gpu']
        )
        try:
            context = await browser.new_context(
                user_agent=self.user_agent,
                viewport={'width': 1920, 'height': 1080},
                locale='ja-JP',
                timezone_id='Asia/Tokyo'
            )
            # Блокируем картинки и шрифты для скорости
            await context.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2}", lambda route: route.abort())
            
            page = await context.new_page()
            
            # Маскировка под человека
            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            yield page
        finally:
            await browser.close()
            await playwright.stop()

    async def _goto_with_retry(self, url: str, page: Page) -> None:
        for attempt in range(self.max_retries):
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
                return
            except Exception as e:
                if attempt == self.max_retries - 1:
                    logger.warning(f"Ошибка загрузки {url}: {e}")
                    raise
                await asyncio.sleep(2 ** attempt)

    def _clean_price(self, text: str) -> int:
        if not text: return 0
        # Берем только первую группу цифр, чтобы отсечь доставку/налоги
        # Пример: "1,000円 (税込)" -> "1000"
        match = re.search(r'([0-9,]+)', text)
        if match:
            clean = match.group(1).replace(',', '')
            return int(clean) if clean.isdigit() else 0
        return 0

    def _clean_text(self, text: str) -> str:
        return re.sub(r'\s+', ' ', text).strip()

    async def _scroll_page(self, page: Page):
        """Ленивый скролл для подгрузки элементов"""
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
            await asyncio.sleep(0.5)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 1.5)")
        except:
            pass

    @abstractmethod
    async def _parse_items(self, page: Page, max_items: int) -> List[ItemData]:
        pass

    async def parse(self, search_url: str, max_items: int = 10) -> List[ItemData]:
        async with self._browser_context() as page:
            try:
                await self._goto_with_retry(search_url, page)
                await self._scroll_page(page)
                # Небольшая пауза для JS
                await asyncio.sleep(1) 
                return await self._parse_items(page, max_items)
            except Exception as e:
                logger.error(f"Ошибка парсинга {self.PLATFORM.value}: {e}")
                return []

# --- MERCARI PARSER ---
class MercariParser(BaseParser):
    PLATFORM = Platform.MERCARI
    
    async def _parse_items(self, page: Page, max_items: int) -> List[ItemData]:
        try:
            await page.wait_for_selector('div[id="item-grid"], [data-testid="item-grid"]', timeout=8000)
        except:
            logger.warning("Mercari: Сетка не найдена")
            # Не падаем, пробуем искать ссылки так
        
        item_elements = await page.locator('a[href*="/item/m"]').all()
        results = []
        
        for item in item_elements[:max_items]:
            try:
                data = await self._extract_mercari_item(item)
                if data: results.append(data)
            except Exception:
                continue
        return results
    
    async def _extract_mercari_item(self, item) -> Optional[ItemData]:
        link = await item.get_attribute("href")
        if not link: return None
        
        full_url = f"https://jp.mercari.com{link}"
        market_id = link.split("/")[-1]
        
        # 1. Пытаемся найти картинку и взять название из alt (самый надежный способ)
        title = "No Title"
        image_url = None
        try:
            img = item.locator('img').first
            if await img.count() > 0:
                title = await img.get_attribute("alt") or await item.get_attribute("aria-label") or "No Title"
                image_url = await img.get_attribute("src")
        except:
            pass

        # 2. Если название всё еще плохое, берем текст
        text = await item.inner_text()
        if title == "No Title" or len(title) < 2:
            # Исключаем строки с ценой
            lines = [l for l in text.split('\n') if '¥' not in l and len(l) > 3]
            title = lines[0] if lines else "Mercari Item"

        # 3. Парсим цену
        price_match = re.search(r'(?:¥|kb)\s*([0-9,]+)', text)
        price = self._clean_price(price_match.group(1)) if price_match else 0
        
        status = "sold" if re.search(r'(SOLD|売り切れ)', text, re.I) else "available"
        
        return ItemData(
            market_id=market_id,
            title=self._clean_text(title),
            price=price,
            url=full_url,
            platform=self.PLATFORM.value,
            image_url=image_url,
            status=status
        )

# --- YAHOO PARSER ---
class YahooParser(BaseParser):
    PLATFORM = Platform.YAHOO
    
    async def _parse_items(self, page: Page, max_items: int) -> List[ItemData]:
        try:
            await page.wait_for_selector('.Product', timeout=8000)
        except:
            return []
        
        item_elements = await page.locator('.Product').all()
        results = []
        
        for item in item_elements[:max_items]:
            try:
                data = await self._extract_yahoo_item(item)
                if data: results.append(data)
            except Exception:
                continue
        return results
    
    async def _extract_yahoo_item(self, item) -> Optional[ItemData]:
        link_el = item.locator('.Product__titleLink').first
        if await link_el.count() == 0: return None
        
        url = await link_el.get_attribute("href")
        title = await link_el.get_attribute("data-auction-title") or await link_el.inner_text()
        
        market_id = url.split("/")[-1] if url else "unknown"
        
        # Исправляем склейку цен. Берем только .Product__priceValue
        price_el = item.locator('.Product__priceValue').first
        price_text = await price_el.inner_text() if await price_el.count() > 0 else "0"
        price = self._clean_price(price_text)
        
        # Картинка
        image_url = None
        try:
            img = item.locator('img').first
            image_url = await img.get_attribute('src')
        except:
            pass

        return ItemData(
            market_id=market_id,
            title=self._clean_text(title),
            price=price,
            url=url or "",
            platform=self.PLATFORM.value,
            image_url=image_url
        )

# --- FACTORY & DISPATCHER ---
class ParserFactory:
    _PARSERS: Dict[Platform, Type[BaseParser]] = {
        Platform.MERCARI: MercariParser,
        Platform.YAHOO: YahooParser,
    }
    
    @classmethod
    def create_parser(cls, url: str) -> BaseParser:
        if "mercari.com" in url: return cls._PARSERS[Platform.MERCARI]()
        elif "yahoo.co.jp" in url: return cls._PARSERS[Platform.YAHOO]()
        raise ValueError(f"Unknown platform: {url}")

async def parse_url(url: str, max_items: int = 10) -> List[ItemData]:
    """Парсинг одного URL"""
    try:
        parser = ParserFactory.create_parser(url)
        return await parser.parse(url, max_items=max_items)
    except Exception as e:
        logger.error(f"Ошибка создания парсера для {url}: {e}")
        return []

async def parse_multiple_urls(urls: List[str], max_items: int = 10) -> Dict[str, List[ItemData]]:
    """
    БЕЗОПАСНЫЙ парсинг списка URL (последовательно с паузами)
    """
    results = {}
    
    # Перемешиваем, чтобы ломать паттерны поведения
    shuffled_urls = list(urls)
    random.shuffle(shuffled_urls)
    
    logger.info(f"🚦 Начинаю обработку {len(urls)} ссылок (режим Anti-Ban)")

    for i, url in enumerate(shuffled_urls):
        try:
            logger.info(f"🔎 [{i+1}/{len(urls)}] Парсинг: {url}")
            items = await parse_url(url, max_items)
            results[url] = items
            
            # Если это не последняя ссылка, спим
            if i < len(shuffled_urls) - 1:
                sleep_time = random.uniform(5, 12) # Пауза 5-12 секунд
                logger.info(f"💤 Жду {sleep_time:.1f} сек...")
                await asyncio.sleep(sleep_time)
                
        except Exception as e:
            logger.error(f"Сбой на ссылке {url}: {e}")
            results[url] = []
            
    return results

if __name__ == "__main__":
    # Тест
    async def main():
        print("Тестируем безопасный парсинг...")
        test_urls = [
            "https://jp.mercari.com/search?keyword=GameBoy",
            "https://auctions.yahoo.co.jp/search/search?p=Nintendo"
        ]
        res = await parse_multiple_urls(test_urls, max_items=3)
        for url, items in res.items():
            print(f"\nURL: {url}")
            for item in items:
                print(f"- {item.title} | {item.price} yen")

    asyncio.run(main())