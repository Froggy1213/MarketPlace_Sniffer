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
from app.services.items import check_and_mark_item_sent
from app.core.config import settings
from aiogram import Bot

logger = logging.getLogger(__name__)


# ============================================================================
# IMAGE DOWNLOAD HELPER
# ============================================================================

async def download_image(url: str) -> bytes | None:
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
            logger.error(f"❌ Critical fallback error: {fallback_error}")


async def process_notification_job(
    user_id: int, task_id: int, market_id: str,
    platform: str, title: str, price: int, url: str, image_url: str | None = None
):
    """Дедуплицирует и отправляет сообщение пользователю."""
    is_new = await check_and_mark_item_sent(user_id, task_id, market_id)
    if not is_new:
        logger.debug(f"⏭️ Skipping duplicate: {market_id} for user {user_id}")
        return

    item = ItemData(
        market_id=market_id, 
        platform=platform,
        title=title, 
        price=price, 
        url=url, 
        image_url=image_url
    )
    await send_new_item_notification(item, user_id)