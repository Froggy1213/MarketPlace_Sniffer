import re
import logging
from typing import List, Optional
from playwright.async_api import Page, Locator, TimeoutError as PlaywrightTimeoutError
from .base import BaseParser, ItemData, Platform

logger = logging.getLogger(__name__)


class MercariSelectors:
    """Centralized CSS selectors for easy maintenance."""
    GRID = 'div[id="item-grid"], [data-testid="item-grid"]'
    ITEM_LINK = 'a[href*="/item/m"]'


class MercariParser(BaseParser):
    PLATFORM = Platform.MERCARI

    async def parse_page(self, url: str, page: Page, max_items: int) -> List[ItemData]:
        import asyncio

        try:
            await self._goto_with_retry(url, page)
            await self._scroll_page(page)
            await asyncio.sleep(1)  # Render delay

            try:
                await page.wait_for_selector(MercariSelectors.GRID, timeout=8000)
            except PlaywrightTimeoutError:
                logger.warning("Mercari: Grid not found, attempting direct link extraction.")

            item_elements = await page.locator(MercariSelectors.ITEM_LINK).all()
            results = []

            for item in item_elements:
                if len(results) >= max_items:
                    break  # Strict limit enforcement

                try:
                    data = await self._extract_item(item)
                    if data:
                        results.append(data)
                except Exception as e:
                    logger.debug(f"Mercari extraction skipped: {e}")
                    continue

            return results
        except Exception as e:
            logger.error(f"Critical error in MercariParser: {e}", exc_info=True)
            return []

    async def _extract_item(self, item: Locator) -> Optional[ItemData]:
        link = await item.get_attribute("href")
        if not link: return None

        full_url = f"https://jp.mercari.com{link}"
        market_id = link.split("/")[-1]

        title, image_url = "No Title", None
        try:
            img = item.locator('img').first
            if await img.count() > 0:
                title = await img.get_attribute("alt") or await item.get_attribute("aria-label") or "No Title"
                image_url = await img.get_attribute("src")
        except Exception:
            pass

        text = await item.inner_text()
        if title == "No Title" or len(title) < 2:
            lines = [l for l in text.split('\n') if '¥' not in l and len(l) > 3]
            title = lines[0] if lines else "Mercari Item"

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