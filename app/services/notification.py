import logging
import aiohttp
from aiogram.types import BufferedInputFile
from app.services.parsers.base import ItemData
from app.core.config import settings
from aiogram import Bot

logger = logging.getLogger(__name__)


async def download_image(url: str) -> bytes | None:
    """Asynchronously downloads an image into memory before sending."""
    if not url:
        return None

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    return await response.read()
    except Exception as e:
        logger.debug(f"Failed to download image {url}: {e}")
    return None


async def send_new_item_notification(item: ItemData):
    """Sends a notification to the user with an image (if available)."""

    text = (
        f"🌟 <b>New Match!</b> [{item.platform.upper()}]\n\n"
        f"🏷 <b>{item.title}</b>\n"
        f"💰 <b>Price:</b> {item.price} ¥\n\n"
        f"🔗 <a href='{item.url}'>View Item</a>"
    )

    try:
        # Initialize the bot INSIDE the function using a context manager.
        # Upon exiting the 'async with' block, the bot will automatically close its aiohttp session.
        async with Bot(token=settings.TELEGRAM_BOT_TOKEN.get_secret_value()) as bot:
            image_bytes = None
            if item.image_url:
                image_bytes = await download_image(item.image_url)

            if image_bytes:
                photo = BufferedInputFile(image_bytes, filename=f"{item.market_id}.jpg")
                await bot.send_photo(
                    chat_id=settings.ADMIN_ID,
                    photo=photo,
                    caption=text,
                    parse_mode="HTML"
                )
            else:
                await bot.send_message(
                    chat_id=settings.ADMIN_ID,
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=False
                )

            logger.info(f"📨 Notification sent: {item.title[:20]}...")

    except Exception as e:
        logger.error(f"❌ Telegram send error: {e}")
        # Fallback in case of image attachment issues or other API errors
        try:
            async with Bot(token=settings.TELEGRAM_BOT_TOKEN.get_secret_value()) as bot:
                await bot.send_message(chat_id=settings.ADMIN_ID, text=text, parse_mode="HTML")
        except Exception as fallback_error:
            logger.error(f"❌ Critical fallback error: {fallback_error}")