import asyncio
import logging
import sys
from aiogram import Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.services.parser_service import parse_multiple_urls
from app.services.storage import save_new_items, get_all_searches
from app.services.notification import send_new_item_notification, bot
from app.bot.handlers import router 

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

async def check_updates_job():
    """Фоновая задача проверки обновлений"""
    logger.info("⏰ Начало проверки...")
    
    try:
        # 1. Получаем ссылки из БАЗЫ ДАННЫХ
        searches = await get_all_searches()
        if not searches:
            logger.info("📭 База ссылок пуста. Жду команды /add")
            return

        urls = [s.url for s in searches]
        
        # 2. Парсим
        results_dict = await parse_multiple_urls(urls, max_items=10)
        
        all_found_items = []
        for url, items in results_dict.items():
            all_found_items.extend(items)
            
        logger.info(f"🔎 Найдено {len(all_found_items)} товаров. Фильтрую...")

        # 3. Фильтруем и сохраняем
        new_items = await save_new_items(all_found_items)
        
        if not new_items:
            return

        # 4. Уведомляем
        logger.info(f"🚀 {len(new_items)} новых лотов! Шлю в ТГ.")
        for item in new_items:
            await send_new_item_notification(item)
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"❌ Ошибка цикла обновления: {e}", exc_info=True)

async def main():
    """Запуск всего"""
    logger.info("🤖 Бот запускается...")

    # 1. Настройка Telegram (Dispatcher)
    dp = Dispatcher()
    dp.include_router(router) # Подключаем наши команды (/add, /list...)

    # 2. Настройка Планировщика
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_updates_job, 'interval', minutes=45)
    scheduler.start()
    
    # 3. Удаляем вебхуки и запускаем поллинг (слушаем команды)
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем две задачи параллельно:
    # - polling (слушает команды от тебя в ТГ)
    # - scheduler (работает в фоне внутри процесса)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")