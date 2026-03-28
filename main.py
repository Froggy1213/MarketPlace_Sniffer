import asyncio
import logging
from aiogram import Bot, Dispatcher
from app.core.config import settings
from app.bot.handlers import router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("🤖 Starting Telegram Bot...")

    # Initialize Bot and Dispatcher directly in the main entry point
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN.get_secret_value())
    dp = Dispatcher()

    # Register the FSM and command handlers
    dp.include_router(router)

    try:
        # Start long-polling
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Bot crashed: {e}")
    finally:
        # Graceful shutdown
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Bot stopped manually.")