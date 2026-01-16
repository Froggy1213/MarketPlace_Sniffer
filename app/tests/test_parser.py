import asyncio
import logging
import re
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
    seller: Optional[str] = None
    condition: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Конвертация в словарь с фильтрацией None"""
        return {k: v for k, v in asdict(self).items() if v is not None}

class ParserError(Exception):
    """Базовая ошибка парсера"""
    pass

class BaseParser(ABC):
    """Базовый класс с общими настройками и методами"""
    
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
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None

    @asynccontextmanager
    async def _browser_context(self):
        """Контекстный менеджер для браузера"""
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu'
                ]
            )
            
            context = await self._browser.new_context(
                user_agent=self.user_agent,
                viewport={'width': 1920, 'height': 1080},
                locale='ja-JP',
                timezone_id='Asia/Tokyo',
                extra_http_headers={
                    'Accept-Language': 'ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7'
                }
            )
            
            # Блокируем ненужные ресурсы
            await context.route(
                "**/*.{png,jpg,jpeg,gif,svg,woff,woff2,mp4,webm}",
                lambda route: route.abort()
            )
            
            self._page = await context.new_page()
            
            # Скрываем признаки автоматизации
            await self._page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = {runtime: {}};
            """)
            
            yield self._page
            
        finally:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()

    async def _goto_with_retry(self, url: str, page: Page) -> None:
        """Переход на страницу с повторными попытками"""
        for attempt in range(self.max_retries):
            try:
                logger.info(f"{self.PLATFORM.value}: Попытка {attempt + 1}/{self.max_retries}")
                await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
                return
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise ParserError(f"Не удалось загрузить страницу после {self.max_retries} попыток: {e}")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

    def _clean_price(self, text: str) -> int:
        """Универсальная очистка цены"""
        if not text:
            return 0
        clean = re.sub(r'[^\d]', '', text)
        return int(clean) if clean.isdigit() else 0

    def _clean_text(self, text: str) -> str:
        """Очистка текста от лишних символов"""
        return re.sub(r'\s+', ' ', text).strip()

    async def _scroll_page(self, page: Page) -> None:
        """Скроллинг для загрузки контента"""
        try:
            await page.evaluate("""
                async () => {
                    await new Promise((resolve) => {
                        let totalHeight = 0;
                        const distance = 100;
                        const timer = setInterval(() => {
                            window.scrollBy(0, distance);
                            totalHeight += distance;
                            if(totalHeight >= document.body.scrollHeight / 2){
                                clearInterval(timer);
                                resolve();
                            }
                        }, 100);
                    });
                }
            """)
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"Ошибка при скроллинге: {e}")

    @abstractmethod
    async def _parse_items(self, page: Page, max_items: int) -> List[ItemData]:
        """Метод парсинга, специфичный для каждой платформы"""
        pass

    async def parse(self, search_url: str, max_items: int = 10) -> List[ItemData]:
        """Главный метод парсинга"""
        logger.info(f"🚀 {self.PLATFORM.value.upper()}: Начинаю парсинг {search_url}")
        
        async with self._browser_context() as page:
            try:
                await self._goto_with_retry(search_url, page)
                await self._scroll_page(page)
                
                items = await self._parse_items(page, max_items)
                logger.info(f"✅ {self.PLATFORM.value.upper()}: Успешно обработано {len(items)} товаров")
                return items
                
            except Exception as e:
                logger.error(f"❌ {self.PLATFORM.value.upper()}: Критическая ошибка - {e}", exc_info=True)
                raise ParserError(f"Ошибка парсинга {self.PLATFORM.value}: {e}")

# --- MERCARI PARSER ---
class MercariParser(BaseParser):
    PLATFORM = Platform.MERCARI
    
    async def _parse_items(self, page: Page, max_items: int) -> List[ItemData]:
        try:
            await page.wait_for_selector(
                'div[id="item-grid"], [data-testid="item-grid"]',
                timeout=10000
            )
        except Exception:
            logger.warning("Mercari: Сетка не найдена")
            return []

        item_elements = await page.locator('a[href^="/item/m"]').all()
        logger.info(f"Mercari: Найдено {len(item_elements)} элементов")
        
        results = []
        for item in item_elements[:max_items]:
            try:
                item_data = await self._extract_mercari_item(item)
                if item_data:
                    results.append(item_data)
            except Exception as e:
                logger.debug(f"Ошибка обработки элемента Mercari: {e}")
                continue
        
        return results
    
    async def _extract_mercari_item(self, item) -> Optional[ItemData]:
        """Извлечение данных товара Mercari"""
        link = await item.get_attribute("href")
        if not link:
            return None
        
        full_url = f"https://jp.mercari.com{link}"
        market_id = link.split("/")[-1]
        text = await item.inner_text()
        
        # Извлечение цены
        price_match = re.search(r'¥\s*([0-9,]+)', text)
        price = self._clean_price(price_match.group(1)) if price_match else 0
        
        # Извлечение названия
        lines = [l for l in text.split('\n') if len(l) > 2 and '¥' not in l]
        title = self._clean_text(lines[0]) if lines else "Без названия"
        
        # Проверка статуса
        status = "sold" if re.search(r'(SOLD|売り切れ|完売)', text, re.I) else "available"
        
        # Попытка получить изображение
        image_url = None
        try:
            img = await item.locator('img').first
            if img:
                image_url = await img.get_attribute('src')
        except Exception:
            pass
        
        return ItemData(
            market_id=market_id,
            title=title,
            price=price,
            url=full_url,
            platform=self.PLATFORM.value,
            image_url=image_url,
            status=status
        )

# --- YAHOO AUCTIONS PARSER ---
class YahooParser(BaseParser):
    PLATFORM = Platform.YAHOO
    
    async def _parse_items(self, page: Page, max_items: int) -> List[ItemData]:
        try:
            await page.wait_for_selector('.Product, [class*="Product"]', timeout=10000)
        except Exception:
            logger.warning("Yahoo: Товары не найдены")
            return []
        
        item_elements = await page.locator('.Product').all()
        logger.info(f"Yahoo: Найдено {len(item_elements)} элементов")
        
        results = []
        for item in item_elements[:max_items]:
            try:
                item_data = await self._extract_yahoo_item(item)
                if item_data:
                    results.append(item_data)
            except Exception as e:
                logger.debug(f"Ошибка обработки элемента Yahoo: {e}")
                continue
        
        return results
    
    async def _extract_yahoo_item(self, item) -> Optional[ItemData]:
        """Извлечение данных товара Yahoo Auctions"""
        # Ссылка
        link_el = item.locator('.Product__titleLink, a[href*="/auction/"]')
        if await link_el.count() == 0:
            return None
        
        url = await link_el.first.get_attribute("href")
        if not url:
            return None
        
        # Название
        title_text = await link_el.first.get_attribute("data-auction-title")
        if not title_text:
            title_text = await link_el.first.inner_text()
        title = self._clean_text(title_text)
        
        # ID аукциона
        market_id = url.split("/")[-1] if "/" in url else "unknown"
        
        # Цена
        price_el = item.locator('.Product__priceValue, [class*="price"]')
        price_text = "0"
        if await price_el.count() > 0:
            price_text = await price_el.first.inner_text()
        price = self._clean_price(price_text)
        
        # Статус аукциона
        status = "available"
        try:
            status_text = await item.inner_text()
            if re.search(r'(終了|完売)', status_text):
                status = "ended"
        except Exception:
            pass
        
        return ItemData(
            market_id=market_id,
            title=title,
            price=price,
            url=url,
            platform=self.PLATFORM.value,
            status=status
        )

# --- FACTORY & DISPATCHER ---
class ParserFactory:
    """Фабрика для создания парсеров"""
    
    _PARSERS: Dict[Platform, Type[BaseParser]] = {
        Platform.MERCARI: MercariParser,
        Platform.YAHOO: YahooParser,
    }
    
    @classmethod
    def detect_platform(cls, url: str) -> Platform:
        """Определение платформы по URL"""
        url_lower = url.lower()
        if "mercari.com" in url_lower:
            return Platform.MERCARI
        elif "yahoo.co.jp" in url_lower:
            return Platform.YAHOO
        return Platform.UNKNOWN
    
    @classmethod
    def create_parser(cls, url: str, **kwargs) -> BaseParser:
        """Создание парсера для URL"""
        platform = cls.detect_platform(url)
        
        if platform == Platform.UNKNOWN:
            raise ValueError(f"Неподдерживаемая платформа: {url}")
        
        parser_class = cls._PARSERS[platform]
        return parser_class(**kwargs)

async def parse_url(url: str, max_items: int = 10, **parser_kwargs) -> List[Dict]:
    """
    Универсальная функция парсинга для любого поддерживаемого URL
    
    Args:
        url: URL страницы для парсинга
        max_items: Максимальное количество товаров
        **parser_kwargs: Дополнительные параметры для парсера (headless, timeout и т.д.)
    
    Returns:
        Список словарей с данными товаров
    
    Raises:
        ValueError: Если платформа не поддерживается
        ParserError: Если произошла ошибка парсинга
    """
    parser = ParserFactory.create_parser(url, **parser_kwargs)
    items = await parser.parse(url, max_items=max_items)
    return [item.to_dict() for item in items]

async def parse_multiple_urls(urls: List[str], max_items: int = 10) -> Dict[str, List[Dict]]:
    """
    Парсинг нескольких URL параллельно
    
    Args:
        urls: Список URL для парсинга
        max_items: Максимальное количество товаров с каждого URL
    
    Returns:
        Словарь {url: [товары]}
    """
    tasks = [parse_url(url, max_items) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    output = {}
    for url, result in zip(urls, results):
        if isinstance(result, Exception):
            logger.error(f"Ошибка парсинга {url}: {result}")
            output[url] = []
        else:
            output[url] = result
    
    return output

# --- ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ ---
async def main():
    """Примеры использования парсера"""
    
    # Пример 1: Парсинг одного URL
    mercari_url = "https://jp.mercari.com/search?keyword=nintendo+switch"
    items = await parse_url(mercari_url, max_items=5)
    
    print("\n=== MERCARI RESULTS ===")
    for item in items:
        print(f"📦 {item['title'][:50]}...")
        print(f"💰 ¥{item['price']:,}")
        print(f"🔗 {item['url']}\n")
    
    # Пример 2: Парсинг нескольких URL параллельно
    urls = [
        "https://jp.mercari.com/search?keyword=iphone",
        "https://auctions.yahoo.co.jp/search/search?p=iphone"
    ]
    
    all_results = await parse_multiple_urls(urls, max_items=3)
    
    print("\n=== MULTI-URL RESULTS ===")
    for url, items in all_results.items():
        print(f"\n{url}: {len(items)} товаров")

if __name__ == "__main__":
    asyncio.run(main())