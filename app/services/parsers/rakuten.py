import logging
import re
import asyncio
from typing import List, Optional
from playwright.async_api import Page, Locator
from .base import BaseParser, ItemData, Platform

logger = logging.getLogger(__name__)


class RakutenParser(BaseParser):
    PLATFORM = Platform.RAKUTEN

    async def parse_page(self, url: str, page: Page, max_items: int) -> List[ItemData]:
        try:
            await self._goto_with_retry(url, page)
            await self._scroll_page(page)
            await asyncio.sleep(1.5)

            # Ищем карточки товаров. У Rakuten они обычно в классе .searchresultitem
            item_elements = await page.locator('.searchresultitem, div[class*="searchresult"]').all()
            results = []

            for item in item_elements:
                if len(results) >= max_items:
                    break
                try:
                    data = await self._extract_item(item)
                    if data:
                        results.append(data)
                except Exception as e:
                    logger.debug(f"Rakuten extraction skipped: {e}")
                    continue
            return results
        except Exception as e:
            logger.error(f"Error in RakutenParser: {e}")
            return []

    async def _extract_item(self, item: Locator) -> Optional[ItemData]:
        link_el = item.locator('a').first
        if await link_el.count() == 0:
            return None
        url = await link_el.get_attribute("href")
        if not url:
            return None

        market_id = url.split("?")[0].strip("/")[-15:]  # Хэш или ID из ссылки
        title = await link_el.get_attribute("title") or await link_el.inner_text()

        text = await item.inner_text()
        price_match = re.search(r'([0-9,]+)円', text)
        price = self._clean_price(price_match.group(1)) if price_match else 0

        image_url = None
        try:
            img = item.locator('img').first
            if await img.count() > 0:
                image_url = await img.get_attribute("src")
        except Exception:
            pass

        return ItemData(
            market_id=market_id, title=self._clean_text(title), price=price,
            url=url, platform=self.PLATFORM.value, image_url=image_url
        )