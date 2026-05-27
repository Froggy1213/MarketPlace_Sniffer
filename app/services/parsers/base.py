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
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

# Logger instance for this module
logger = logging.getLogger(__name__)


# ============================================================================
# PLATFORM ENUMERATION
# ============================================================================

class Platform(Enum):
    """
    Enumeration of supported Japanese marketplace platforms.
    
    Each platform has a lowercase identifier string that matches the parser module name.
    This enum is used for:
    - Identifying which marketplace a product came from
    - Routing parsing tasks to the correct parser
    - Displaying marketplace name in user notifications
    
    Supported platforms:
        - MERCARI: Mercari (secondhand marketplace)
        - YAHOO: Yahoo Auctions (auction platform)
        - RAKUMA: Rakuma (Rakuten's secondhand marketplace)
        - RAKUTEN: Rakuten (e-commerce platform)
        - PAYPAY: PayPay Flea Market (P2P marketplace)
        - UNKNOWN: Fallback for unrecognized sources
    """
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
    """
    Standardized data structure for marketplace products.
    
    This dataclass represents a single product found during web scraping.
    It normalizes data across different marketplace formats into a consistent structure.
    
    All marketplace parsers must extract and return ItemData objects.
    The dataclass is frozen (immutable) for data integrity.
    
    Required Attributes:
        market_id (str): Unique identifier for this product within its marketplace.
                        This is critical for deduplication - prevents saving the same
                        product multiple times if scraped again.
                        Format varies by marketplace (e.g., numeric ID, alphanumeric code).
        
        title (str): Product name/title extracted from the marketplace.
                    Must be cleaned of HTML tags, extra whitespace, and special chars.
                    Displayed to users in notifications.
        
        price (int): Product price in Japanese Yen (¥).
                    Must be an integer (no decimals).
                    Extracted by removing commas and currency symbols.
        
        url (str): Direct link to the product page on the marketplace.
                  Must be a complete, working URL that users can click to view the item.
                  Should not be redirect URLs or shortened links.
        
        platform (str): Name of the source marketplace (e.g., "mercari", "yahoo").
                       Should match Platform enum values for consistency.
                       Displayed in user notifications with emoji (e.g., "[MERCARI]").
    
    Optional Attributes:
        image_url (Optional[str]): URL to the product image, if available.
                                  Defaults to None if no image found.
                                  Downloaded and sent with notifications if present.
                                  Should be the highest quality image available.
        
        status (str): Current availability status of the product.
                     Defaults to "available" for newly scraped items.
                     Could be "sold", "pending", "archived" etc. if marketplace provides this info.
                     Used for filtering and analytics.
    
    Methods:
        to_dict() -> Dict: Converts the ItemData instance to a dictionary, 
                          excluding None values for database storage.
                          Filters out optional fields not present in this specific item.
    
    Usage:
        Each marketplace parser's parse_page() method should yield or collect ItemData
        objects and return them as a List[ItemData]. These are then stored in the
        database and used to send notifications to subscribed users.
    """
    market_id: str
    title: str
    price: int
    url: str
    platform: str
    image_url: Optional[str] = None
    status: str = "available"

    def to_dict(self) -> Dict:
        """
        Converts ItemData to a dictionary, excluding None values.
        
        This method is used when storing items in the database to avoid
        storing NULL values for optional fields like image_url.
        
        Returns:
            Dict: Dictionary with all non-None attributes as key-value pairs.
                  Example: {'market_id': '12345', 'title': 'Laptop', 'price': 50000, ...}
        """
        return {k: v for k, v in asdict(self).items() if v is not None}


# ============================================================================
# BASE PARSER CLASS
# ============================================================================

class BaseParser(ABC):
    """
    Abstract base class for all marketplace parsers.
    
    This class defines the interface and provides common utility methods that all
    marketplace-specific parsers inherit. Each marketplace (Mercari, Yahoo, etc.)
    creates a subclass that implements the abstract parse_page() method.
    
    The BaseParser provides:
    - Navigation with automatic retry and exponential backoff
    - Text and price cleaning utilities
    - Page scrolling for dynamic content loading
    - Timeout and retry configuration
    
    Attributes:
        PLATFORM (Platform): Marketplace platform identifier.
                            Should be overridden in subclasses (e.g., Platform.MERCARI).
                            Defaults to Platform.UNKNOWN.
        
        timeout (int): Page load timeout in milliseconds (default: 30000 = 30 seconds).
                      Used for Playwright page.goto() calls.
                      Increased if marketplaces are slow to load.
        
        max_retries (int): Maximum number of retry attempts for page navigation.
                          Default: 3 attempts before giving up.
                          Uses exponential backoff between retries (2^attempt seconds).
    
    Subclasses must implement:
        - parse_page(url, page, max_items): Parse a marketplace listing page
          and return List[ItemData] of found products.
    """
    
    PLATFORM: Platform = Platform.UNKNOWN

    def __init__(self, timeout: int = 30000, max_retries: int = 3):
        """
        Initialize parser with timeout and retry configuration.
        
        Args:
            timeout (int): Milliseconds to wait for page load. Default 30000 (30 seconds).
            max_retries (int): Number of retry attempts on failure. Default 3.
        """
        self.timeout = timeout
        self.max_retries = max_retries

    async def _goto_with_retry(self, url: str, page: Page) -> None:
        """
        Navigates to a URL with automatic retry logic and exponential backoff.
        
        This method is resilient to network issues and temporary server errors.
        It automatically retries failed requests with increasing delays between attempts.
        
        Retry Strategy (Exponential Backoff):
            - Attempt 0: First try (no delay)
            - Attempt 1: Retry after 2^1 = 2 seconds
            - Attempt 2: Retry after 2^2 = 4 seconds
            - Attempt 3 (if max_retries=3): Final retry after 2^3 = 8 seconds
        
        Args:
            url (str): The URL to navigate to
            page (Page): Playwright Page object to use for navigation
        
        Raises:
            PlaywrightTimeoutError: If all retry attempts are exhausted and page fails to load.
                                   This exception is logged as a warning before raising.
        
        Behavior:
            1. Loops through retry attempts (0 to max_retries-1)
            2. Attempts page.goto() with domcontentloaded wait condition
            3. Returns immediately on success
            4. On failure: waits exponentially before retrying
            5. On final failure: logs warning and re-raises the exception
        
        Implementation Notes:
            - Uses "domcontentloaded" wait condition for faster loading
            - Logs are only generated on final timeout (not on intermediate retries)
            - Each attempt shares the same Playwright page object
            - Does NOT retry on other exception types (only PlaywrightTimeoutError)
        """
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
        """
        Extracts and converts price text to integer.
        
        This utility handles various price formats found across Japanese marketplaces:
        - "¥10,000" -> 10000
        - "10,000円" -> 10000
        - "10000" -> 10000
        - "" -> 0 (empty string)
        - "Price not available" -> 0 (no numeric content)
        
        The method:
        1. Returns 0 for empty/None input
        2. Uses regex to find the first numeric sequence with optional commas
        3. Removes all commas (separators used in Japanese formatting)
        4. Converts to integer
        5. Returns 0 if conversion fails
        
        Args:
            text (str): Raw price text from the marketplace HTML.
                       Can contain currency symbols, commas, whitespace.
        
        Returns:
            int: Cleaned price in yen. Returns 0 if extraction fails or text is empty.
        
        Implementation:
            - Regex pattern: r'([0-9,]+)' finds the first number (with optional commas)
            - Removes commas: replace(',', '')
            - Validates result is numeric before converting to int
        
        Note:
            This method always returns an integer (never raises ValueError).
            Invalid prices are defaulted to 0 rather than failing.
        """
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
        """
        Cleans and normalizes text by removing excess whitespace.
        
        This utility handles text extraction from HTML which often includes:
        - Multiple spaces
        - Line breaks (\n, \r)
        - Tabs
        - HTML rendering artifacts
        
        The method:
        1. Replaces all consecutive whitespace (spaces, tabs, newlines) with a single space
        2. Strips leading and trailing whitespace
        3. Returns the normalized string
        
        Example:
            Input:  "  Product Name  \n  Long Title   \t Extra  "
            Output: "Product Name Long Title Extra"
        
        Args:
            text (str): Raw text extracted from HTML elements
        
        Returns:
            str: Cleaned text with normalized whitespace
        
        Regex Pattern:
            r'\s+' matches one or more whitespace characters (space, tab, newline, etc.)
            re.sub() replaces all matches with a single space
            .strip() removes leading/trailing whitespace
        
        Usage:
            Used to clean product titles, descriptions, and other text fields
            extracted from marketplace HTML.
        """
        # Replace all consecutive whitespace with a single space, then strip edges
        return re.sub(r'\s+', ' ', text).strip()

    async def _scroll_page(self, page: Page):
        """
        Scrolls the page to trigger lazy-loading of dynamic content.
        
        Many modern marketplaces use lazy-loading: images and items only load
        when they scroll into view. This method simulates user scrolling to
        trigger content loading before parsing.
        
        Scroll Strategy:
            1. Scroll to 1/3 of page height (top portion)
            2. Wait 0.5 seconds for content to load
            3. Scroll to 2/3 of page height (middle/bottom portion)
            4. This helps load most content without scrolling to absolute bottom
        
        Args:
            page (Page): Playwright Page object to scroll
        
        Error Handling:
            - Any scroll errors are logged at debug level and silently ignored
            - Parsing continues even if scrolling fails
            - This is non-critical (content might already be loaded)
        
        Implementation Notes:
            - Uses page.evaluate() to run JavaScript scrolling commands
            - Timing is conservative (0.5 sec) to ensure content loads
            - Does not scroll to absolute bottom (saves time and bandwidth)
            - Errors are caught and logged but not re-raised
        
        Note:
            This method does NOT wait for specific elements to load.
            It only waits a fixed 0.5 seconds which is a best-effort approach.
        """
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

    @abstractmethod
    async def parse_page(self, url: str, page: Page, max_items: int) -> List[ItemData]:
        """
        Abstract method that must be implemented by all marketplace-specific parsers.
        
        This is the main parsing method. Each marketplace parser subclass must
        implement this method with marketplace-specific parsing logic.
        
        The method should:
        1. Navigate to the marketplace URL (using self._goto_with_retry())
        2. Wait for and scroll the page to load dynamic content (using self._scroll_page())
        3. Extract product information from the HTML/DOM
        4. Create ItemData objects for each product found
        5. Stop when max_items is reached or page is fully scraped
        6. Return the list of ItemData objects
        
        Args:
            url (str): The marketplace URL/search page to scrape.
                      Usually a search results page with filtering applied.
            
            page (Page): Playwright Page object (browser tab).
                        Already initialized and ready for navigation.
                        Can use page.locator(), page.evaluate(), etc.
            
            max_items (int): Maximum number of items to extract from this page.
                           Prevents excessive scraping and speeds up smaller requests.
                           Parsers should stop parsing once this limit is reached.
        
        Returns:
            List[ItemData]: List of product data objects extracted from the page.
                          Each item must be a properly populated ItemData instance.
                          Empty list is valid if no products found.
        
        Raises:
            Exception: Subclasses may raise various exceptions (timeout, parsing errors, etc).
                      These should be logged and handled by the calling worker task.
        
        Contract:
            - Must use self._clean_price() to clean prices
            - Must use self._clean_text() to clean titles
            - Should use self._goto_with_retry() for navigation
            - Should use self._scroll_page() for dynamic content
            - Must return only ItemData instances in valid state
        
        Example Structure (for subclass implementation):
            async def parse_page(self, url: str, page: Page, max_items: int):
                await self._goto_with_retry(url, page)
                await self._scroll_page(page)
                items = []
                # Extract items from page...
                return items[:max_items]
        """
        pass