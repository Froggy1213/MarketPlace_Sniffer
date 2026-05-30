import os
from celery import Celery # type: ignore
from app.core.sentry import setup_sentry
from celery.schedules import crontab # type: ignore


setup_sentry()  # Инициализация до того, как воркер начнет брать задачи
celery_app = Celery("marketplace_sniffer")

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Initialize Celery application
celery_app = Celery(
    "marketplace_sniffer",
    broker=redis_url,
    backend=redis_url,
    include=["app.worker.tasks"]
)

# Celery Configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Tokyo",
    enable_utc=True,
    
    # Prevent infinite task hanging
    task_soft_time_limit=300, # 5 minutes
    task_time_limit=360,      # 6 minutes

    # =========================================================
    # МИКРОСЕРВИСНАЯ МАРШРУТИЗАЦИЯ ОЧЕРЕДЕЙ
    # =========================================================
    task_default_queue="celery", # Дефолтная очередь (сюда падает парсинг)
    task_routes={
        # Все задачи на отправку сообщений жестко направляем в очередь 'notifications'
        "app.worker.tasks.send_notification": {"queue": "notifications"}
    }
)


celery_app.conf.beat_schedule = {
    'parse-marketplaces-every-3-minutes': {
        'task': 'app.worker.tasks.parse_marketplaces',
        'schedule': crontab(minute='*/3'),
    },
    'check-subscriptions-daily': {
        'task': 'app.worker.tasks.check_subscriptions',
        'schedule': crontab(hour=0, minute=0),  
    }
}