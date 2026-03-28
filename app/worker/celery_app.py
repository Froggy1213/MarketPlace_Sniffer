import os
from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Initialize Celery application
celery_app = Celery(
    "marketplace_sniffer",
    broker=redis_url,
    backend=redis_url,
    include=["app.worker.tasks"] # We will create this file next
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
)

# Configure Celery Beat (Task Scheduler)
# This entirely replaces the old APScheduler from main.py
celery_app.conf.beat_schedule = {
    "run-sniffing-every-45-minutes": {
        "task": "app.worker.tasks.run_all_searches",
        # Execute every 45 minutes
        "schedule": crontab(minute="*/45"),
    },
}