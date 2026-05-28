import asyncio
import logging
from aiogram import Bot, Dispatcher
from app.core.config import settings
from app.bot.handlers import main_router
from app.bot.middlewares.db import DatabaseMiddleware 

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

async def main():
    logger.info("🤖 Starting Telegram Bot...")

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN.get_secret_value())
    dp = Dispatcher()

    # ДОБАВЛЕНО: Регистрация middleware перед роутерами
    dp.update.middleware(DatabaseMiddleware())

    # Register the FSM and command handlers
    dp.include_router(main_router)

    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Bot crashed: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Bot stopped manually.")