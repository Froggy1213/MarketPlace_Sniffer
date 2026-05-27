"""
Notification Service Module

This module handles sending notifications to users about newly found marketplace items.
It provides functionality to:
- Download images from URLs asynchronously
- Send formatted notifications with images or fallback to text-only
- Implement error handling with fallback notification mechanisms

The notification system sends alerts to Telegram users when items matching their
search criteria are found on Japanese marketplaces.
"""

import logging
import aiohttp
from aiogram.types import BufferedInputFile
from app.services.parsers.base import ItemData
from app.core.config import settings
from aiogram import Bot

# Logger instance for this module
logger = logging.getLogger(__name__)


# ============================================================================
# IMAGE DOWNLOAD HELPER
# ============================================================================

async def download_image(url: str) -> bytes | None:
    """
    Asynchronously downloads an image into memory before sending to Telegram.
    
    This function retrieves image bytes from a given URL with a 10-second timeout.
    The image is loaded entirely into memory (buffered) before being sent to the user,
    which is necessary for Telegram's API.
    
    Args:
        url (str): The URL of the image to download.
                   Empty strings are handled gracefully (returns None).
    
    Returns:
        bytes | None: 
            - bytes: Image data if download was successful
            - None: If URL is empty, download fails, or any exception occurs
    
    Workflow:
        1. Return None if URL is empty
        2. Create an aiohttp session
        3. Make HTTP GET request with 10-second timeout
        4. Check if response status is 200 (OK)
        5. Read response data into bytes
        6. Return bytes on success, None on any error
    
    Error Handling:
        - Network errors (timeout, connection failed)
        - HTTP errors (non-200 status codes)
        - Any other exceptions
        All errors are logged at debug level and return None silently.
    
    Note:
        Uses aiohttp for async HTTP requests to avoid blocking the event loop.
        Timeout is set to 10 seconds to prevent long waits for slow/unresponsive servers.
    """
    if not url:
        # Early return for empty URLs to avoid unnecessary network operations
        return None

    try:
        # Create an async HTTP session for the request
        async with aiohttp.ClientSession() as session:
            # Make a GET request with 10-second total timeout
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                # Check if the request was successful (HTTP 200)
                if response.status == 200:
                    # Read the entire response body into bytes
                    return await response.read()
    except Exception as e:
        # Log any errors at debug level (non-critical, expected for some URLs)
        logger.debug(f"Failed to download image {url}: {e}")
    # Return None if download failed for any reason
    return None


# ============================================================================
# NOTIFICATION SENDING
# ============================================================================

async def send_new_item_notification(item: ItemData, user_id: int):
    """
    Sends a formatted notification to a user about a newly found marketplace item.
    
    This function implements an intelligent notification system with multiple delivery strategies:
    1. Primary: Send with image if available
    2. Secondary: Send text-only message if primary fails
    3. Fallback: Attempt text-only delivery if photo sending fails
    
    The notification includes:
    - Item title
    - Price in yen
    - Marketplace/platform name
    - Clickable link to view the item
    - Product image (if available and successfully downloaded)
    
    Args:
        item (ItemData): The product data object containing:
            - title: Product name/title
            - price: Price in yen
            - platform: Marketplace name (e.g., 'mercari', 'yahoo')
            - url: Direct link to the product
            - image_url: URL of the product image (optional)
            - market_id: Unique identifier for deduplication
        
        user_id (int): Telegram user ID to send the notification to.
                      User IDs are verified by the database when the task was created.
    
    Notification Flow:
        1. Format the message with item details (HTML formatting)
        2. Initialize Telegram Bot with API token
        3. Attempt to download image from item.image_url
        4. If image downloaded: Send as photo with caption
        5. If no image or download failed: Send as text message
        6. If photo sending fails: Fallback to text-only message
        7. Log success or errors at appropriate levels
    
    Message Format:
        HTML-formatted message with:
        - Emoji indicators for visual hierarchy
        - Bold formatting for titles
        - Hyperlink to the product page
        - Platform information
    
    Error Handling Strategy:
        - Graceful degradation: Always deliver a notification
        - Primary: Try to send with image
        - Secondary: Fall back to text if image sending fails
        - All errors are logged for monitoring
        - User receives notification even if image delivery fails
    
    Security Notes:
        - Bot token is retrieved from secure settings (encrypted secret)
        - user_id is passed explicitly (should be verified by caller)
        - Each notification session creates and closes its own Bot instance
    
    Logging:
        - SUCCESS: Logged at INFO level with truncated item title
        - ERRORS: All errors logged at ERROR level with details
    """
    # Format the notification message with item details
    text = (
        f"🌟 <b>New Match!</b> [{item.platform.upper()}]\n\n"
        f"🏷 <b>{item.title}</b>\n"
        f"💰 <b>Price:</b> {item.price} ¥\n\n"
        f"🔗 <a href='{item.url}'>View Item</a>"
    )

    try:
        # Create a Bot instance with the secret token from configuration
        # Each instance is context-managed to ensure proper cleanup
        async with Bot(token=settings.TELEGRAM_BOT_TOKEN.get_secret_value()) as bot:
            # Initialize image_bytes as None (no image yet)
            image_bytes = None
            
            # Attempt to download the image if URL is provided
            if item.image_url:
                image_bytes = await download_image(item.image_url)

            # Send notification with image if image was successfully downloaded
            if image_bytes:
                # Create a BufferedInputFile from image bytes for Telegram API
                # Filename is based on market_id for identification
                photo = BufferedInputFile(image_bytes, filename=f"{item.market_id}.jpg")
                # Send as photo message (image with caption below)
                await bot.send_photo(
                    chat_id=user_id,
                    photo=photo,
                    caption=text,
                    parse_mode="HTML"
                )
            else:
                # Send as text-only message if no image available
                # disable_web_page_preview=False allows Telegram to show preview
                await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=False
                )

            # Log successful notification delivery
            logger.info(f"📨 Notification sent to user {user_id} for: {item.title[:20]}...")

    except Exception as e:
        # Primary send failed - attempt fallback text-only delivery
        logger.error(f"❌ Telegram send error for user {user_id}: {e}")
        
        try:
            # Create a new Bot instance for fallback attempt
            async with Bot(token=settings.TELEGRAM_BOT_TOKEN.get_secret_value()) as bot:
                # Send text-only message as last resort
                await bot.send_message(
                    chat_id=user_id, 
                    text=text, 
                    parse_mode="HTML"
                )
        except Exception as fallback_error:
            # Even fallback failed - log critical error
            # This means the user did not receive any notification
            logger.error(f"❌ Critical fallback error: {fallback_error}")