import logging
import re
from typing import Optional
from playwright.async_api import Locator
from .base import BaseParser, ItemData, Platform

logger = logging.getLogger(__name__)


class RakumaParser(BaseParser):
    PLATFORM = Platform.RAKUMA
    WAIT_SELECTOR = '.item'
    ITEM_SELECTOR = '.item'

    async def _extract_item(self, item: Locator) -> Optional[ItemData]:
        link_el = item.locator('a').first
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

        text = await item.inner_text()
        if title == "No Title" or len(title) < 2:
            lines = [line for line in text.split('\n') if '¥' not in line and len(line) > 2]
            title = lines[0] if lines else "Rakuma Item"

        price_match = re.search(r'(?:¥|kb)\s*([0-9,]+)', text)
        price = self._clean_price(price_match.group(1)) if price_match else 0

        sold_el = item.locator('.item-soldout').first
        status = "sold" if await sold_el.count() > 0 or re.search(r'(SOLD|売り切れ)', text, re.I) else "available"

        return ItemData(
            market_id=market_id,
            title=self._clean_text(title),
            price=price,
            url=link,
            platform=self.PLATFORM.value,
            image_url=image_url,
            status=status
        )