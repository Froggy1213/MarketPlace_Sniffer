import asyncio
import logging
from urllib.parse import quote
from typing import List, Dict, Set, Tuple
from collections import defaultdict

from app.worker.celery_app import celery_app
from app.services.storage import get_all_active_tasks, save_new_items, check_and_mark_item_sent
from app.services.parsers.engine import parse_multiple_urls
from app.services.parsers.base import ItemData
from app.services.notification import send_new_item_notification

logger = logging.getLogger(__name__)


def build_broad_url(platform: str, keyword: str) -> str:
    safe_keyword = quote(keyword.strip())
    platform = platform.strip()

    if platform == "mercari":
        return f"https://jp.mercari.com/search?keyword={safe_keyword}&status=on_sale"
    elif platform == "yahoo":
        return f"https://auctions.yahoo.co.jp/search/search?p={safe_keyword}"
    elif platform == "rakuma":
        return f"https://fril.jp/search/{safe_keyword}"
    elif platform == "rakuten":
        return f"https://search.rakuten.co.jp/search/mall/{safe_keyword}/"
    elif platform == "paypay":
        return f"https://paypayfleamarket.yahoo.co.jp/search/{safe_keyword}"
    return ""


# ============================================================================
# МИКРОСЕРВИС 1: ПАРСЕР (Слушает дефолтную очередь)
# ============================================================================

async def async_parse_marketplaces():
    logger.info("🤖 [PARSER] Starting scheduled search cycle...")

    tasks = await get_all_active_tasks()
    if not tasks:
        return

    url_to_tasks = defaultdict(list)
    for task in tasks:
        # Поскольку platforms теперь ARRAY(String), это уже list, split не нужен
        platforms = task.platforms if isinstance(task.platforms, list) else task.platforms.split(",")
        for p in platforms:
            url = build_broad_url(p, task.keyword)
            if url:
                url_to_tasks[url].append(task)

    urls_to_parse = list(url_to_tasks.keys())
    if not urls_to_parse:
        return

    results_dict = await parse_multiple_urls(urls_to_parse, max_items=30)

    all_valid_items = []
    # Теперь храним кортеж (user_id, task_id), чтобы писать историю отправок
    item_to_users: Dict[str, Set[Tuple[int, int]]] = defaultdict(set)

    for url, scraped_items in results_dict.items():
        tasks_for_url = url_to_tasks[url]

        for item in scraped_items:
            for task in tasks_for_url:
                if task.min_price and item.price < task.min_price:
                    continue
                if task.max_price and item.price > task.max_price:
                    continue

                all_valid_items.append(item)
                item_to_users[item.market_id].add((task.user_id, task.id))

    if not all_valid_items:
        return

    # Сохраняем все товары для общей аналитики. Нам неважно, что вернет эта функция.
    await save_new_items(all_valid_items)

    # Дедубликация массива товаров для итерации
    unique_items = {item.market_id: item for item in all_valid_items}.values()
    
    dispatched_count = 0
    # ПЕРЕДАЕМ ЭСТАФЕТУ: Пушим каждого юзера и товар в очередь уведомлений
    for item in unique_items:
        target_users = item_to_users.get(item.market_id, set())
        for user_id, task_id in target_users:
            task_send_notification.apply_async(
                kwargs={
                    "user_id": user_id,
                    "task_id": task_id,
                    "market_id": item.market_id,
                    "platform": item.platform,
                    "title": item.title,
                    "price": item.price,
                    "url": item.url
                },
                queue='notifications'
            )
            dispatched_count += 1

    logger.info(f"📤 [PARSER] Dispatched {dispatched_count} notifications to the queue.")


@celery_app.task(name="app.worker.tasks.parse_marketplaces")
def task_parse_marketplaces():
    """Точка входа для планировщика (Celery Beat)"""
    asyncio.run(async_parse_marketplaces())


# ============================================================================
# МИКРОСЕРВИС 2: НОТИФИКАТОР (Слушает очередь 'notifications')
# ============================================================================

async def async_send_notification(user_id: int, task_id: int, market_id: str, platform: str, title: str, price: int, url: str):
    # 1. Защита от дублей. Атомарно проверяем и пишем в БД
    is_new_for_user = await check_and_mark_item_sent(user_id, task_id, market_id)
    if not is_new_for_user:
        return  # Товар уже отправлялся этому пользователю

    # 2. Восстанавливаем модель данных для отправки
    item = ItemData(market_id=market_id, platform=platform, title=title, price=price, url=url)

    # 3. Отправка в Telegram
    try:
        await send_new_item_notification(item, user_id)
        logger.info(f"📨 [NOTIFIER] Sent {market_id} to user {user_id}")
    except Exception as e:
        logger.error(f"❌ Failed to send {market_id} to {user_id}: {e}")
        # Если API Telegram отвалилось, можно сделать raise, чтобы Celery повторил попытку (Retry)


@celery_app.task(name="app.worker.tasks.send_notification", rate_limit="20/m")
def task_send_notification(**kwargs):
    """
    Воркер берет задачу из очереди 'notifications'.
    rate_limit="20/m" заставит Celery притормаживать выполнение, 
    если прилетела пачка из 100 товаров. Бот не упадет от лимитов Telegram.
    """
    asyncio.run(async_send_notification(**kwargs))