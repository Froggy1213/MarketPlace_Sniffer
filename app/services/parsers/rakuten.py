import logging
import re
from typing import Optional
from playwright.async_api import Locator
from .base import BaseParser, ItemData, Platform

logger = logging.getLogger(__name__)


class RakutenParser(BaseParser):
    PLATFORM = Platform.RAKUTEN
    WAIT_SELECTOR = '.searchresultitem'
    ITEM_SELECTOR = '.searchresultitem'

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