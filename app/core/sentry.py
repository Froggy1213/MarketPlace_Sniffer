
import os
import logging
import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration

logger = logging.getLogger(__name__)

def setup_sentry():
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        logger.warning("⚠️ SENTRY_DSN не найден. Мониторинг ошибок отключен.")
        return

    sentry_sdk.init(
        dsn=dsn,
        # Отправляем 100% ошибок, но только 20% трейсов производительности (чтобы не спамить лимиты бесплатного тарифа)
        traces_sample_rate=0.2,
        integrations=[
            CeleryIntegration(monitor_beat_tasks=True)
        ]
    )
    logger.info("🛡 Sentry успешно инициализирован.")