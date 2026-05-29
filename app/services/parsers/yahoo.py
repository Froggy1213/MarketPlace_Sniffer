import logging
from typing import Optional
from playwright.async_api import Locator
from .base import BaseParser, ItemData, Platform

logger = logging.getLogger(__name__)


class YahooParser(BaseParser):
    PLATFORM = Platform.YAHOO
    WAIT_SELECTOR = '.Product'
    ITEM_SELECTOR = '.Product'

    async def _extract_item(self, item: Locator) -> Optional[ItemData]:
        link_el = item.locator('.Product__titleLink').first
        if await link_el.count() == 0:
            return None

        url = await link_el.get_attribute("href")
        title = await link_el.get_attribute("data-auction-title") or await link_el.inner_text()
        market_id = url.split("/")[-1] if url else "unknown"

        price_el = item.locator('.Product__priceValue').first
        price_text = await price_el.inner_text() if await price_el.count() > 0 else "0"
        price = self._clean_price(price_text)

        image_url = None
        try:
            img = item.locator('img').first
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