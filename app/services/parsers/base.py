import re
import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)


class Platform(Enum):
    MERCARI = "mercari"
    YAHOO = "yahoo"
    RAKUMA = "rakuma"
    RAKUTEN = "rakuten"
    PAYPAY = "paypay"
    UNKNOWN = "unknown"


@dataclass
class ItemData:
    market_id: str
    title: str
    price: int
    url: str
    platform: str
    image_url: Optional[str] = None
    status: str = "available"

    def to_dict(self) -> Dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


class BaseParser(ABC):
    PLATFORM: Platform = Platform.UNKNOWN

    def __init__(self, timeout: int = 30000, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries

    async def _goto_with_retry(self, url: str, page: Page) -> None:
        """Navigates to URL with retry logic."""
        import asyncio
        for attempt in range(self.max_retries):
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
                return
            except PlaywrightTimeoutError as e:
                if attempt == self.max_retries - 1:
                    logger.warning(f"Timeout loading {url} after {self.max_retries} attempts: {e}")
                    raise
                await asyncio.sleep(2 ** attempt)

    def _clean_price(self, text: str) -> int:
        if not text: return 0
        match = re.search(r'([0-9,]+)', text)
        if match:
            clean = match.group(1).replace(',', '')
            return int(clean) if clean.isdigit() else 0
        return 0

    def _clean_text(self, text: str) -> str:
        return re.sub(r'\s+', ' ', text).strip()

    async def _scroll_page(self, page: Page):
        import asyncio
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
            await asyncio.sleep(0.5)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 1.5)")
        except Exception as e:
            logger.debug(f"Scroll failed: {e}")

    @abstractmethod
    async def parse_page(self, url: str, page: Page, max_items: int) -> List[ItemData]:
        """Contract for all marketplace plugins."""
        pass