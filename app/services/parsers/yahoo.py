import logging
from typing import List, Optional
from playwright.async_api import Page, Locator, TimeoutError as PlaywrightTimeoutError
from .base import BaseParser, ItemData, Platform

logger = logging.getLogger(__name__)


class YahooSelectors:
    CONTAINER = '.Product'
    LINK = '.Product__titleLink'
    PRICE = '.Product__priceValue'
    IMAGE = 'img'


class YahooParser(BaseParser):
    PLATFORM = Platform.YAHOO

    async def parse_page(self, url: str, page: Page, max_items: int) -> List[ItemData]:
        import asyncio

        try:
            await self._goto_with_retry(url, page)
            await self._scroll_page(page)
            await asyncio.sleep(1)

            try:
                await page.wait_for_selector(YahooSelectors.CONTAINER, timeout=8000)
            except PlaywrightTimeoutError:
                logger.warning("Yahoo: Product container not found.")
                return []

            item_elements = await page.locator(YahooSelectors.CONTAINER).all()
            results = []

            for item in item_elements:
                if len(results) >= max_items:
                    break

                try:
                    data = await self._extract_item(item)
                    if data:
                        results.append(data)
                except Exception as e:
                    logger.debug(f"Yahoo extraction skipped: {e}")
                    continue

            return results
        except Exception as e:
            logger.error(f"Critical error in YahooParser: {e}", exc_info=True)
            return []

    async def _extract_item(self, item: Locator) -> Optional[ItemData]:
        link_el = item.locator(YahooSelectors.LINK).first
        if await link_el.count() == 0: return None

        url = await link_el.get_attribute("href")
        title = await link_el.get_attribute("data-auction-title") or await link_el.inner_text()
        market_id = url.split("/")[-1] if url else "unknown"

        price_el = item.locator(YahooSelectors.PRICE).first
        price_text = await price_el.inner_text() if await price_el.count() > 0 else "0"
        price = self._clean_price(price_text)

        image_url = None
        try:
            img = item.locator(YahooSelectors.IMAGE).first
            if await img.count() > 0:
                image_url = await img.get_attribute('src')
        except Exception:
            pass

        return ItemData(
            market_id=market_id,
            title=self._clean_text(title),
            price=price,
            url=url or "",
            platform=self.PLATFORM.value,
            image_url=image_url
        )