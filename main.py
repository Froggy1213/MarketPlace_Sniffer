import asyncio
import logging
import sys
from aiogram import Dispatcher
from app.services.notification import bot
from app.bot.handlers import router

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """
    Application entry point.
    Initializes and starts the Telegram bot polling.
    """
    logger.info("🤖 Starting Telegram Bot...")

    dp = Dispatcher()
    dp.include_router(router)

    # Remove webhook to safely start polling
    await bot.delete_webhook(drop_pending_updates=True)

    try:
        # Start listening for Telegram updates
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("Bot session closed safely.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by system or user.")