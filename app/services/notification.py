import logging
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.core.config import settings
from app.services.parser_service import ItemData

logger = logging.getLogger(__name__)

# Инициализируем бота один раз
bot = Bot(token=settings.TELEGRAM_BOT_TOKEN.get_secret_value())

async def send_new_item_notification(item: ItemData):
    """
    Отправляет уведомление о новом товаре в Telegram.
    """
    try:
        # 1. Готовим текст сообщения (HTML)
        text = (
            f"<b>🔥 NEW ITEM FOUND!</b>\n\n"
            f"📦 <b>{item.title}</b>\n"
            f"💰 Price: <b>¥{item.price:,}</b>\n"
            f"🏪 Platform: #{item.platform}\n"
        )

        # 2. Готовим кнопку-ссылку
        # Важно: используем именованные аргументы (text=..., url=...)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Купить сейчас", url=item.url)]
        ])

        # 3. Отправляем
        if item.image_url:
            try:
                # ПРОСТОЕ РЕШЕНИЕ: Передаем ссылку строкой
                await bot.send_photo(
                    chat_id=settings.ADMIN_ID,
                    photo=item.image_url, 
                    caption=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard
                )
            except Exception as img_err:
                # Если картинка битая или недоступна, шлем просто текст
                logger.warning(f"Не удалось отправить фото ({img_err}), шлю текст.")
                await bot.send_message(
                    chat_id=settings.ADMIN_ID,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard
                )
        else:
            # Если картинки нет изначально
            await bot.send_message(
                chat_id=settings.ADMIN_ID,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
            
        logger.info(f"📨 Уведомление отправлено: {item.title[:20]}...")

    except Exception as e:
        logger.error(f"❌ Ошибка отправки в Telegram: {e}")