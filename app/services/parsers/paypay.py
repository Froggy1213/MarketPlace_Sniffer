import logging
import re
import asyncio
from typing import List, Optional
from playwright.async_api import Page, Locator
from .base import BaseParser, ItemData, Platform

logger = logging.getLogger(__name__)


class PayPayParser(BaseParser):
    PLATFORM = Platform.PAYPAY

    async def parse_page(self, url: str, page: Page, max_items: int) -> List[ItemData]:
        try:
            await self._goto_with_retry(url, page)
            await self._scroll_page(page)
            await asyncio.sleep(1.5)

            # PayPay (Yahoo Flea Market) имеет ссылки вида /item/
            item_elements = await page.locator('a[href*="/item/"]').all()
            results = []
            for item in item_elements:
                if len(results) >= max_items:
                    break
                try:
                    data = await self._extract_item(item)
                    if data:
                        results.append(data)
                except Exception as e:
                    logger.debug(f"PayPay extraction skipped: {e}")
            return results
        except Exception as e:
            logger.error(f"Error in PayPayParser: {e}")
            return []

    async def _extract_item(self, item: Locator) -> Optional[ItemData]:
        url = await item.get_attribute("href")
        if not url:
            return None
        if not url.startswith("http"):
            url = f"https://paypayfleamarket.yahoo.co.jp{url}"

        market_id = url.split("/")[-1]

        title, image_url = "PayPay Item", None
        try:
            img = item.locator('img').first
            if await img.count() > 0:
                title = await img.get_attribute("alt") or "PayPay Item"
                image_url = await img.get_attribute("src")
        except Exception:
            pass

        text = await item.inner_text()
        price_match = re.search(r'([0-9,]+)', text)
        price = self._clean_price(price_match.group(1)) if price_match else 0

        status = "sold" if re.search(r'(SOLD)', text, re.I) else "available"

        return ItemData(
            market_id=market_id, title=self._clean_text(title), price=price,
            url=url, platform=self.PLATFORM.value, image_url=image_url, status=status
        )