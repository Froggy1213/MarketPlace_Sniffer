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
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    return await response.read()
    except Exception as e:
        logger.debug(f"Failed to download image {url}: {e}")
    return None


# Было: async def send_new_item_notification(item: ItemData):
# Стало:
async def send_new_item_notification(item: ItemData, user_id: int):
    """Sends a notification to the user with an image (if available)."""

    text = (
        f"🌟 <b>New Match!</b> [{item.platform.upper()}]\n\n"
        f"🏷 <b>{item.title}</b>\n"
        f"💰 <b>Price:</b> {item.price} ¥\n\n"
        f"🔗 <a href='{item.url}'>View Item</a>"
    )

    try:
        async with Bot(token=settings.TELEGRAM_BOT_TOKEN.get_secret_value()) as bot:
            image_bytes = None
            if item.image_url:
                image_bytes = await download_image(item.image_url)

            if image_bytes:
                photo = BufferedInputFile(image_bytes, filename=f"{item.market_id}.jpg")
                await bot.send_photo(
                    chat_id=user_id,  # <--- Изменили здесь
                    photo=photo,
                    caption=text,
                    parse_mode="HTML"
                )
            else:
                await bot.send_message(
                    chat_id=user_id,  # <--- И здесь
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=False
                )

            logger.info(f"📨 Notification sent to user {user_id} for: {item.title[:20]}...")

    except Exception as e:
        logger.error(f"❌ Telegram send error for user {user_id}: {e}")
        try:
            async with Bot(token=settings.TELEGRAM_BOT_TOKEN.get_secret_value()) as bot:
                await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")  # <--- И здесь
        except Exception as fallback_error:
            logger.error(f"❌ Critical fallback error: {fallback_error}")