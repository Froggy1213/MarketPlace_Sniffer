# app/services/parsers/mercari.py
import re
import logging
from typing import Optional
from playwright.async_api import Locator
from .base import BaseParser, ItemData, Platform

logger = logging.getLogger(__name__)

class MercariParser(BaseParser):
    PLATFORM = Platform.MERCARI
    WAIT_SELECTOR = 'div[id="item-grid"], [data-testid="item-grid"]'
    ITEM_SELECTOR = 'a[href*="/item/m"]'

    async def _extract_item(self, item: Locator) -> Optional[ItemData]:
        link = await item.get_attribute("href")
        if not link:
            return None

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
            lines = [line for line in text.split('\n') if '¥' not in line and len(line) > 3]
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