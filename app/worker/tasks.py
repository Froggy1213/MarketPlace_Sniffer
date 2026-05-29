import asyncio
import logging
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter

from app.core.config import settings
from app.db.database import worker_engine as engine, worker_session_maker
from app.worker.celery_app import celery_app

from app.services.search_manager import fetch_and_prepare_notifications
from app.services.notification import process_notification_job
from app.services.users import downgrade_expired_pro_users

logger = logging.getLogger(__name__)

@celery_app.task(name="app.worker.tasks.parse_marketplaces")
def task_parse_marketplaces():
    async def wrapper():
        try:
            notifications = await fetch_and_prepare_notifications()
            for kwargs in notifications:
                task_send_notification.apply_async(kwargs=kwargs, queue='notifications')
            if notifications:
                logger.info(f"📤 [PARSER] Dispatched {len(notifications)} notifications to the queue.")
        finally:
            await engine.dispose() 
            
    asyncio.run(wrapper())

@celery_app.task(bind=True, name="app.worker.tasks.send_notification", max_retries=3)
def task_send_notification(self, **kwargs):
    async def wrapper():
        # Инициализируем бота один раз для этой задачи
        bot = Bot(token=settings.TELEGRAM_BOT_TOKEN.get_secret_value())
        
        try:
            # Открываем сессию БД один раз
            async with worker_session_maker() as session:
                await process_notification_job(session=session, bot=bot, **kwargs)
                
        except TelegramRetryAfter as e:
            logger.warning(f"⏳ [NOTIFIER] Telegram Rate Limit! Retrying in {e.retry_after} seconds...")
            self.retry(exc=e, countdown=e.retry_after)
        except TelegramAPIError as e:
            logger.error(f"❌ [NOTIFIER] Telegram API Error: {e}")
            self.retry(exc=e, countdown=10) 
        except Exception as e:
            logger.error(f"💥 [NOTIFIER] Critical Error sending {kwargs.get('market_id')}: {e}", exc_info=True)
            self.retry(exc=e, countdown=15) # Также ретраим обычные ошибки (например, локи БД)
        finally:
            # Корректно закрываем aiohttp сессию бота
            await bot.session.close()
            await engine.dispose()
            
    asyncio.run(wrapper())

@celery_app.task(name="app.worker.tasks.check_subscriptions")
def task_check_subscriptions():
    async def wrapper():
        try:
            logger.info("🔍 [BILLING] Checking for expired PRO subscriptions...")
            async with worker_session_maker() as session:
                count = await downgrade_expired_pro_users(session)
                if count > 0:
                    logger.info(f"✅ [BILLING] Successfully downgraded {count} users.")
        finally:
            await engine.dispose()
            
    asyncio.run(wrapper())