import logging
import aiohttp
from aiogram.types import BufferedInputFile
from app.services.parsers.base import ItemData
from app.core.config import settings
from aiogram import Bot

logger = logging.getLogger(__name__)

# Initialize the bot
bot = Bot(token=settings.BOT_TOKEN)


async def download_image(url: str) -> bytes | None:
    """Asynchronously downloads an image into memory before sending."""
    if not url:
        return None

    try:
        # Use aiohttp for fast file downloading
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    return await response.read()
    except Exception as e:
        logger.debug(f"Failed to download image {url}: {e}")
    return None


async def send_new_item_notification(item: ItemData):
    """Sends a notification to the user with an image (if available)."""

    # Build the HTML message text
    text = (
        f"🌟 <b>New find!</b> [{item.platform.upper()}]\n\n"
        f"🏷 <b>{item.title}</b>\n"
        f"💰 <b>Price:</b> {item.price} ¥\n\n"
        f"🔗 <a href='{item.url}'>View item</a>"
    )
    try:
        image_bytes = None
        if item.image_url:
            # Download the image to our server
            image_bytes = await download_image(item.image_url)
        if image_bytes:
            # Send the photo as an in-memory file
            photo = BufferedInputFile(image_bytes, filename=f"{item.market_id}.jpg")
            await bot.send_photo(
                chat_id=settings.ADMIN_ID,
                photo=photo,
                caption=text,
                parse_mode="HTML"
            )
        else:
            # Fallback: if there's no image or it failed to download, send text only
            await bot.send_message(
                chat_id=settings.ADMIN_ID,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=False
            )

        logger.info(f"📨 Notification sent: {item.title[:20]}...")

    except Exception as e:
        logger.error(f"❌ Telegram send error: {e}")
        # Hard fallback for unexpected API errors
        try:
            await bot.send_message(chat_id=settings.ADMIN_ID, text=text, parse_mode="HTML")
        except:
            pass