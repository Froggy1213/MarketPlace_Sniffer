"""
Base Parser Module

This module defines the abstract base class and data structures for all marketplace parsers.
It provides:
- Platform enumeration for supported Japanese marketplaces
- ItemData dataclass for standardized product representation
- BaseParser abstract base class with common parsing utilities

All marketplace-specific parsers (Mercari, Yahoo, Rakuma, etc.) inherit from BaseParser
and implement their own parse_page() method while leveraging shared utility functions.

This module uses Playwright for browser automation and async/await for non-blocking I/O.
"""

import re
import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from playwright.async_api import Page, Locator,  TimeoutError as PlaywrightTimeoutError

# Logger instance for this module
logger = logging.getLogger(__name__)


# ============================================================================
# PLATFORM ENUMERATION
# ============================================================================

class Platform(Enum):

    MERCARI = "mercari"
    YAHOO = "yahoo"
    RAKUMA = "rakuma"
    RAKUTEN = "rakuten"
    PAYPAY = "paypay"
    UNKNOWN = "unknown"


# ============================================================================
# PRODUCT DATA MODEL
# ============================================================================

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


# ============================================================================
# BASE PARSER CLASS
# ============================================================================

class BaseParser(ABC):
    PLATFORM: Platform = Platform.UNKNOWN
    WAIT_SELECTOR: Optional[str] = None
    ITEM_SELECTOR: str = ""

    def __init__(self, timeout: int = 30000, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries

    async def _goto_with_retry(self, url: str, page: Page) -> None:
        import asyncio
        # Iterate through retry attempts
        for attempt in range(self.max_retries):
            try:
                # Attempt to navigate to the URL
                # wait_until="domcontentloaded" means we wait for basic DOM to be ready,
                # not necessarily all images/resources (faster than "networkidle")
                await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
                # Success! Return immediately without retrying
                return
            except PlaywrightTimeoutError as e:
                # Check if this was the last attempt
                if attempt == self.max_retries - 1:
                    # This is the final failure - log it and re-raise
                    logger.warning(f"Timeout loading {url} after {self.max_retries} attempts: {e}")
                    raise
                # Not the last attempt - wait before retrying
                # Use exponential backoff: 2^attempt seconds (2, 4, 8, ...)
                await asyncio.sleep(2 ** attempt)

    def _clean_price(self, text: str) -> int:
        if not text:
            # Early return for empty/None input
            return 0
        # Search for numeric sequences with optional commas using regex
        match = re.search(r'([0-9,]+)', text)
        if match:
            # Extract the matched numeric string and remove commas
            clean = match.group(1).replace(',', '')
            # Only convert if the result is purely numeric
            return int(clean) if clean.isdigit() else 0
        # No numeric sequence found
        return 0

    def _clean_text(self, text: str) -> str:
        # Replace all consecutive whitespace with a single space, then strip edges
        return re.sub(r'\s+', ' ', text).strip()

    async def _scroll_page(self, page: Page):
        import asyncio
        try:
            # Scroll to 1/3 of page height to start loading top content
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
            # Brief pause to allow images/content to load
            await asyncio.sleep(0.5)
            # Scroll to 2/3 of page height to load middle/bottom content
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 1.5)")
        except Exception as e:
            # Log scroll errors at debug level (non-critical)
            logger.debug(f"Scroll failed: {e}")

    async def parse_page(self, url: str, page: Page, max_items: int) -> List[ItemData]:
        import asyncio
        try:
            await self._goto_with_retry(url, page)
            await self._scroll_page(page)
            await asyncio.sleep(1)

            if self.WAIT_SELECTOR:
                try:
                    await page.wait_for_selector(self.WAIT_SELECTOR, timeout=8000)
                except PlaywrightTimeoutError:
                    logger.warning(f"{self.PLATFORM.value}: Wait selector not found, attempting direct extraction.")
            else:
                try:
                    await page.wait_for_selector(self.ITEM_SELECTOR, timeout=8000)
                except PlaywrightTimeoutError:
                    logger.warning(f"{self.PLATFORM.value}: Items not found.")

            item_elements = await page.locator(self.ITEM_SELECTOR).all()
            results: list[ItemData] = []

            for item in item_elements:
                if len(results) >= max_items:
                    break
                try:
                    data = await self._extract_item(item)
                    if data:
                        results.append(data)
                except Exception as e:
                    logger.debug(f"{self.PLATFORM.value} extraction skipped: {e}")
                    continue

            return results
        except Exception as e:
            logger.error(f"Critical error in {self.__class__.__name__}: {e}", exc_info=True)
            return []

    @abstractmethod
    async def _extract_item(self, item: Locator) -> Optional[ItemData]:
        """Определяется в дочерних классах"""
        pass