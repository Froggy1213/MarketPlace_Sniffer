import html
import logging

import aiohttp
from aiogram import Bot
from aiogram.types import BufferedInputFile
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FoundItem
from app.services.items import check_and_mark_item_sent
from app.services.parsers.base import ItemData

logger = logging.getLogger(__name__)


async def download_image(url: str) -> bytes | None:
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


async def send_new_item_notification(bot: Bot, item: ItemData, user_id: int) -> None:
    safe_title = html.escape(item.title)
    safe_url = html.escape(item.url, quote=True)
    platform_label = html.escape(item.platform.upper())

    text = (
        f"🌟 <b>New Match!</b> [{platform_label}]\n\n"
        f"🏷 <b>{safe_title}</b>\n"
        f"💰 <b>Price:</b> {item.price} ¥\n\n"
        f"🔗 <a href='{safe_url}'>View Item</a>"
    )

    try:
        image_bytes = await download_image(item.image_url) if item.image_url else None

        if image_bytes:
            photo = BufferedInputFile(image_bytes, filename=f"{item.market_id}.jpg")
            await bot.send_photo(chat_id=user_id, photo=photo, caption=text, parse_mode="HTML")
        else:
            await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")

        logger.info(f"📨 Notification sent to user {user_id} for: {item.title[:20]}...")

    except Exception as e:
        logger.error(f"❌ Telegram send error for user {user_id}: {e}")
        try:
            await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")
        except Exception as fallback_error:
            logger.error(f"❌ Critical fallback error: {fallback_error}")
            raise fallback_error from e


async def process_notification_job(
    session: AsyncSession,
    bot: Bot,
    user_id: int,
    task_id: int,
    market_id: str,
    platform: str,
    title: str,
    price: int,
    url: str,
    image_url: str | None = None,
) -> None:
    is_new = await check_and_mark_item_sent(session, user_id, task_id, market_id)
    if not is_new:
        logger.debug(f"⏭️ Skipping duplicate: {market_id} for user {user_id}")
        return

    item = ItemData(
        market_id=market_id,
        platform=platform,
        title=title,
        price=price,
        url=url,
        image_url=image_url,
    )

    try:
        await send_new_item_notification(bot, item, user_id)
    except Exception as e:
        logger.error(f"Failed to send to {user_id}, rolling back DB record: {e}")
        await session.execute(
            delete(FoundItem).where(
                FoundItem.user_id == user_id,
                FoundItem.market_id == market_id,
            )
        )
        await session.commit()
        raise
