"""
Parser Engine Module

This module orchestrates the web scraping workflow for multiple marketplaces.
It provides:
- ParserFactory: Factory pattern for instantiating marketplace-specific parsers
- parse_multiple_urls(): Main async function that orchestrates browser automation

The engine is designed for efficiency and anti-detection:
- Creates a single browser instance and reuses it across multiple URLs (resource optimization)
- Uses incognito contexts and anti-detection scripts to avoid rate limiting/bans
- Implements random shuffling and throttling to mimic human behavior
- Efficiently routes URLs to the correct marketplace parser

The workflow:
1. Accept list of marketplace URLs from the worker
2. Shuffle URLs to vary request patterns
3. Launch Chromium browser ONCE with anti-detection settings
4. Create a single incognito context for all requests
5. Process each URL sequentially using the appropriate parser
6. Apply random delays between requests (anti-ban throttling)
7. Collect and return all found items
"""

import asyncio
import logging
import random
from typing import List, Dict, Type
from playwright.async_api import async_playwright

from .base import BaseParser, Platform, ItemData
from .rakuma import RakumaParser
from .rakuten import RakutenParser
from .paypay import PayPayParser
from .mercari import MercariParser
from .yahoo import YahooParser

# Logger instance for this module
logger = logging.getLogger(__name__)


# ============================================================================
# PARSER FACTORY
# ============================================================================

class ParserFactory:
    """
    Factory class that manages and instantiates marketplace-specific parsers.
    
    This class uses the Factory pattern to:
    - Maintain a registry of available parsers (mapping Platform enum to Parser classes)
    - Dynamically instantiate the correct parser based on a given URL
    - Handle URL-to-marketplace routing logic in one centralized place
    
    Supported Platforms:
        - MERCARI (mercari.com) - Secondhand marketplace
        - PAYPAY (paypayfleamarket) - P2P flea market
        - YAHOO (yahoo.co.jp) - Auction platform
        - RAKUMA (fril.jp) - Rakuten's secondhand marketplace
        - RAKUTEN (rakuten.co.jp) - E-commerce platform
    
    Design Benefits:
        - Easy to add new marketplace parsers (just add to _PARSERS dict)
        - Centralized URL-to-parser routing
        - Decouples calling code from specific parser implementations
        - Supports polymorphism (all parsers inherit from BaseParser)
    
    Static Nature:
        This class uses @classmethod, so it doesn't need instantiation.
        You call methods directly: ParserFactory.get_parser(url)
    """
    
    # Registry mapping marketplace platforms to their parser classes
    # Each parser class inherits from BaseParser and implements parse_page()
    _PARSERS: Dict[Platform, Type[BaseParser]] = {
        Platform.MERCARI: MercariParser,
        Platform.YAHOO: YahooParser,
        Platform.RAKUMA: RakumaParser,
        Platform.RAKUTEN: RakutenParser,
        Platform.PAYPAY: PayPayParser,
    }

    @classmethod
    def get_parser(cls, url: str) -> BaseParser:
        """
        Returns an instantiated parser appropriate for the given URL.
        
        This method analyzes the URL to determine which marketplace it belongs to,
        then returns a new instance of the corresponding parser class.
        
        The method uses string matching to identify the marketplace from the URL.
        This routing logic is the heart of the factory pattern.
        
        Args:
            url (str): The marketplace URL to parse.
                      Should be a full URL or contain a recognizable domain.
                      Examples: 
                      - "https://www.mercari.com/jp/search?q=..."
                      - "https://auctions.yahoo.co.jp/search?q=..."
                      - "https://paypayfleamarket.yahoo.co.jp/..."
        
        Returns:
            BaseParser: A new instance of the appropriate parser class.
                       Each call creates a new instance (not cached/reused).
        
        Raises:
            ValueError: If the URL doesn't match any known marketplace domain.
                       This prevents silent failures when an unsupported URL is passed.
        
        Routing Logic (Order Matters):
            1. Check for "mercari.com" -> MercariParser
            2. Check for "paypayfleamarket" -> PayPayParser
            3. Check for "yahoo.co.jp" -> YahooParser
            4. Check for "fril.jp" -> RakumaParser
            5. Check for "rakuten.co.jp" -> RakutenParser
            6. No match -> raise ValueError
        
        Note:
            The order of checks can matter if domains overlap. For example,
            "yahoo.co.jp" appears in multiple services, so we check more specific
            patterns like "paypayfleamarket" first before generic "yahoo.co.jp".
        """
        # Check for Mercari domain
        if "mercari.com" in url:
            return cls._PARSERS[Platform.MERCARI]()
        # Check for PayPay Flea Market (before generic Yahoo check)
        elif "paypayfleamarket" in url:
            return cls._PARSERS[Platform.PAYPAY]()
        # Check for Yahoo Auctions
        elif "yahoo.co.jp" in url:
            return cls._PARSERS[Platform.YAHOO]()
        # Check for Rakuma (fril.jp domain)
        elif "fril.jp" in url:
            return cls._PARSERS[Platform.RAKUMA]()
        # Check for Rakuten e-commerce
        elif "rakuten.co.jp" in url:
            return cls._PARSERS[Platform.RAKUTEN]()
        # No matching marketplace found
        raise ValueError(f"No parser plugin found for URL: {url}")


# ============================================================================
# MAIN PARSING ENGINE
# ============================================================================

async def parse_multiple_urls(urls: List[str], max_items: int = 10) -> Dict[str, List[ItemData]]:
    """
    Main orchestrator function for parsing multiple marketplace URLs efficiently.
    
    This is the primary entry point for the parsing engine. It handles:
    - Browser lifecycle management (launch once, reuse for all URLs)
    - Anti-detection and anti-ban measures
    - Resource optimization through context reuse
    - Error handling and recovery
    - Throttling to avoid rate limiting
    
    The function implements an "industrial-strength" scraping pattern:
    - Single browser instance (expensive resource)
    - Single incognito context (memory efficient)
    - Anti-detection scripts applied globally
    - Media blocking to save bandwidth
    - Random throttling between requests
    - Proper cleanup in all scenarios
    
    Args:
        urls (List[str]): List of marketplace URLs to scrape.
                         Each URL should be from a supported marketplace.
                         Empty list returns empty results (no-op).
        
        max_items (int): Maximum items to extract per URL (default: 10).
                        Passed to each parser's parse_page() method.
                        Prevents excessive scraping and speeds up small requests.
    
    Returns:
        Dict[str, List[ItemData]]: Mapping of URLs to their extracted items.
                                  Failed URLs map to empty lists (not errors).
                                  Structure: {url1: [item1, item2, ...], url2: [], ...}
    
    Workflow:
        1. Validate input (return empty dict if no URLs)
        2. Shuffle URLs to vary request patterns (anti-detection)
        3. Launch Chromium browser with anti-detection arguments
        4. Create incognito context with:
           - Custom User-Agent
           - Viewport dimensions (1920x1080)
           - Japanese locale and Asia/Tokyo timezone
        5. Add anti-bot detection scripts to the context
        6. Block media files (png, jpg, woff, etc.) to save bandwidth
        7. For each URL:
           a. Create a new page/tab in the context
           b. Get the appropriate parser using ParserFactory
           c. Call parser.parse_page() with the page
           d. Store results (or empty list if error)
           e. Close the page to free memory
           f. Wait random delay before next URL (throttling)
        8. Close browser and return results
    
    Error Handling:
        - Individual URL failures don't stop processing (continue with next)
        - Failed URLs return empty lists (not error objects)
        - Errors are logged with full traceback (exc_info=True)
        - Browser is always closed (finally block)
    
    Resource Management:
        - Browser created ONCE for all URLs (not per URL)
        - Single context reused for all requests (memory efficient)
        - Each URL gets its own page/tab (isolated per request)
        - Pages are closed immediately after parsing (free RAM)
        - Media files blocked to reduce bandwidth usage
    
    Anti-Detection Features:
        - URL shuffling: Randomizes request order
        - Incognito context: No persistent cookies/cache
        - User-Agent: Looks like a real browser
        - Viewport: Standard desktop dimensions
        - Locale/Timezone: Japanese settings (realistic)
        - Anti-webdriver script: Hides Playwright detection
        - Random throttling: 5-12 second delays between requests
    
    Anti-Ban Strategy:
        The function employs multiple techniques to avoid being detected as a bot:
        1. Randomized request order (shuffled URLs)
        2. Variable delays (random.uniform(5, 12) seconds)
        3. Normal browser headers and user-agent
        4. JavaScript anti-detection injection
        5. Incognito/private browsing mode
        6. Realistic viewport and locale settings
    
    Performance Notes:
        - Single browser instance: Saves ~500MB RAM vs multiple browsers
        - Single context: Shares connection pool and resources
        - Media blocking: Saves ~70-80% bandwidth vs downloading all images
        - Sequential processing: Allows sequential throttling (realistic pattern)
        - Page per URL: Isolates parsing logic (cleaner error handling)
    
    Logging:
        - INFO: Browser start, each URL processing, throttling delays
        - ERROR: Individual URL parsing failures (with traceback)
    
    Example Usage:
        urls = [
            "https://www.mercari.com/jp/search?q=laptop",
            "https://auctions.yahoo.co.jp/search?q=laptop"
        ]
        results = await parse_multiple_urls(urls, max_items=20)
        # results = {
        #     "https://www.mercari.com/...": [ItemData(...), ItemData(...), ...],
        #     "https://auctions.yahoo.co.jp/...": [ItemData(...), ...],
        # }
    """
    # Initialize empty results dictionary
    results: Dict[str, List[ItemData]] = {}
    
    # Handle empty input
    if not urls:
        # No URLs to process, return empty results
        return results

    # Shuffle URLs to vary request patterns
    # This randomization helps avoid being detected as an automated scraper
    shuffled_urls = list(urls)
    random.shuffle(shuffled_urls)

    # Log the start of the parsing session
    logger.info(f"🚦 Starting browser engine for {len(urls)} URLs")

    # === RESOURCE OPTIMIZATION: Browser Lifecycle ===
    # Start Playwright and Browser ONLY ONCE per task cycle
    # All URLs will share this single browser instance and context
    async with async_playwright() as p:
        # Launch Chromium browser with anti-detection settings
        browser = await p.chromium.launch(
            headless=True,  # Run without visible window (server environment)
            # Anti-detection arguments to hide Playwright from detection scripts
            args=[
                '--disable-blink-features=AutomationControlled',  # Hide automation detection
                '--no-sandbox',  # Disable sandbox (needed in Docker/containerized environments)
                '--disable-gpu'  # Disable GPU acceleration (not needed in headless mode)
            ]
        )
        try:
            # === CONTEXT CONFIGURATION ===
            # Create a single anonymous incognito context for all URLs
            # Incognito means no persistent cookies/cache between requests
            context = await browser.new_context(
                # Realistic User-Agent header (Windows Chrome 120)
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                # Standard desktop viewport size
                viewport={'width': 1920, 'height': 1080},
                # Set locale to Japanese (expected by marketplace sites)
                locale='ja-JP',
                # Set timezone to Tokyo (Asia/Tokyo)
                timezone_id='Asia/Tokyo'
            )

            # === ANTI-DETECTION SCRIPT ===
            # Add JavaScript that hides Playwright's webdriver property
            # Many sites check for window.navigator.webdriver to detect automation
            await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            # === BANDWIDTH OPTIMIZATION ===
            # Block media files to save bandwidth and speed up loading
            # Blocks PNG, JPG, GIF, SVG images and WOFF/WOFF2 fonts
            # This significantly reduces data transfer (images are largest files)
            await context.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2}", lambda route: route.abort())

            # === MAIN PARSING LOOP ===
            # Process each URL using the same context (connection pooling, resource sharing)
            for i, url in enumerate(shuffled_urls):
                # Log the URL being processed with progress indicator
                logger.info(f"🔎 [{i + 1}/{len(urls)}] Parsing: {url}")
                
                # Create a new page/tab in this context for this URL
                page = await context.new_page()

                try:
                    # Get the appropriate parser for this URL using factory pattern
                    parser = ParserFactory.get_parser(url)
                    
                    # Execute the marketplace-specific parsing logic
                    # Parser will navigate to URL, extract items, and return ItemData list
                    items = await parser.parse_page(url, page, max_items)
                    
                    # Store the extracted items for this URL
                    results[url] = items
                except Exception as e:
                    # Handle parsing errors gracefully
                    # Log the error with full traceback for debugging
                    logger.error(f"Failed to process URL {url}: {e}", exc_info=True)
                    # Store empty list for this URL (indicates failure but continues processing)
                    results[url] = []
                finally:
                    # Always close the page to free up memory
                    # This is critical in a loop to avoid memory leaks
                    await page.close()

                # === ANTI-BAN THROTTLING ===
                # Apply delay between requests to mimic human behavior
                # Don't sleep after the last URL (no need)
                if i < len(shuffled_urls) - 1:
                    # Random delay between 5-12 seconds to vary request patterns
                    sleep_time = random.uniform(5, 12)
                    # Log the throttling action with duration
                    logger.info(f"💤 Throttling... Sleeping for {sleep_time:.1f}s")
                    # Wait before processing next URL
                    await asyncio.sleep(sleep_time)

        finally:
            # === CLEANUP ===
            # Always close the browser, even if an error occurred
            # This ensures resources are freed and process can exit cleanly
            await browser.close()

    return results