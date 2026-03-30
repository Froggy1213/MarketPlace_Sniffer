import logging
import re
from typing import List, Optional
from playwright.async_api import Page, Locator, TimeoutError as PlaywrightTimeoutError
from .base import BaseParser, ItemData, Platform

logger = logging.getLogger(__name__)


class RakumaSelectors:
    """CSS selectors for Rakuma (fril.jp)."""
    CONTAINER = '.item'  # Главный контейнер карточки товара
    LINK = 'a'
    SOLD_BADGE = '.item-soldout'  # Плашка продано


class RakumaParser(BaseParser):
    PLATFORM = Platform.RAKUMA

    async def parse_page(self, url: str, page: Page, max_items: int) -> List[ItemData]:
        import asyncio

        try:
            await self._goto_with_retry(url, page)
            await self._scroll_page(page)
            await asyncio.sleep(1)  # Даем React/Vue отрендерить страницу

            try:
                await page.wait_for_selector(RakumaSelectors.CONTAINER, timeout=8000)
            except PlaywrightTimeoutError:
                logger.warning("Rakuma: Item container not found. Maybe no results?")
                return []

            item_elements = await page.locator(RakumaSelectors.CONTAINER).all()
            results: list[ItemData] = []

            for item in item_elements:
                if len(results) >= max_items:
                    break

                try:
                    data = await self._extract_item(item)
                    if data:
                        results.append(data)
                except Exception as e:
                    logger.debug(f"Rakuma extraction skipped: {e}")
                    continue

            return results
        except Exception as e:
            logger.error(f"Critical error in RakumaParser: {e}", exc_info=True)
            return []

    async def _extract_item(self, item: Locator) -> Optional[ItemData]:
        link_el = item.locator(RakumaSelectors.LINK).first
        if await link_el.count() == 0:
            return None

        link = await link_el.get_attribute("href")
        if not link:
            return None

        market_id = link.split("/")[-1]

        title, image_url = "No Title", None
        try:
            img = item.locator('img').first
            if await img.count() > 0:
                title = await img.get_attribute("alt") or "No Title"
                image_url = await img.get_attribute("src")
        except Exception:
            pass

        # Если картинка не отдала alt-текст, берем текст со всей карточки
        text = await item.inner_text()
        if title == "No Title" or len(title) < 2:
            lines = [line for line in text.split('\n') if '¥' not in line and len(line) > 2]
            title = lines[0] if lines else "Rakuma Item"

        price_match = re.search(r'(?:¥|kb)\s*([0-9,]+)', text)
        price = self._clean_price(price_match.group(1)) if price_match else 0

        sold_el = item.locator(RakumaSelectors.SOLD_BADGE).first
        status = "sold" if await sold_el.count() > 0 or re.search(r'(SOLD|売り切れ)', text, re.I) else "available"

        return ItemData(
            market_id=market_id,
            title=self._clean_text(title),
            price=price,
            url=link,  # У Rakuma абсолютные ссылки вида https://item.fril.jp/...
            platform=self.PLATFORM.value,
            image_url=image_url,
            status=status
        )