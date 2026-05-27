import asyncio
import logging
from urllib.parse import quote
from typing import List, Dict, Set
from collections import defaultdict

from app.worker.celery_app import celery_app
from app.services.storage import get_all_active_tasks, save_new_items
from app.services.parsers.engine import parse_multiple_urls
from app.services.notification import send_new_item_notification

logger = logging.getLogger(__name__)


def build_broad_url(platform: str, keyword: str) -> str:
    """
    Генерирует ШИРОКИЙ URL только по ключевому слову (без цен).
    Это позволяет 1 раз открыть страницу, даже если 100 юзеров ищут это слово с разными ценами.
    """
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


async def async_run_all_searches():
    """
    Core asynchronous logic with Multi-Tenant Routing & In-Memory Filtering.
    """
    logger.info("⏰ Celery Beat: Starting scheduled search cycle...")

    tasks = await get_all_active_tasks()
    if not tasks:
        logger.info("📭 No active search tasks found in DB. Skipping cycle.")
        return

    # 1. Группируем ЗАДАЧИ по широкому URL
    url_to_tasks = defaultdict(list)
    for task in tasks:
        platforms = task.platforms.split(",")
        for p in platforms:
            url = build_broad_url(p, task.keyword)
            if url:
                url_to_tasks[url].append(task)

    urls_to_parse = list(url_to_tasks.keys())
    if not urls_to_parse:
        return

    # 2. Собираем топ-30 свежих товаров по каждому широкому запросу
    logger.info(f"🚦 Dispatching {len(urls_to_parse)} BATCHED URLs to Playwright...")
    # Берем больше товаров (30), так как мы игнорируем фильтры площадок
    results_dict = await parse_multiple_urls(urls_to_parse, max_items=30)

    all_valid_items = []
    item_to_users: Dict[str, Set[int]] = defaultdict(set)

    # 3. In-Memory фильтрация (Магия SaaS)
    for url, scraped_items in results_dict.items():
        tasks_for_url = url_to_tasks[url]

        for item in scraped_items:
            for task in tasks_for_url:
                # Применяем ценовые фильтры конкретного пользователя в RAM (мгновенно)
                if task.min_price and item.price < task.min_price:
                    continue
                if task.max_price and item.price > task.max_price:
                    continue

                # Если товар прошел фильтры этого юзера, добавляем его в список рассылки
                all_valid_items.append(item)
                item_to_users[item.market_id].add(task.user_id)

    # Если после фильтрации ничего не осталось
    if not all_valid_items:
        logger.info("💤 No items passed user price filters this cycle.")
        return

    # 4. Filter duplicates via DB
    new_items = await save_new_items(all_valid_items)

    if not new_items:
        logger.info("💤 All found items were already in the DB.")
        return

    # 5. Route notifications to the correct users
    logger.info(f"🚀 {len(new_items)} NEW items found! Routing notifications...")
    for item in new_items:
        target_users = item_to_users.get(item.market_id, set())
        for user_id in target_users:
            await send_new_item_notification(item, user_id)
            await asyncio.sleep(0.5)  # Throttling limits (max 30 msgs/sec per TG rules)


@celery_app.task(name="app.worker.tasks.run_all_searches")
def run_all_searches():
    try:
        asyncio.run(async_run_all_searches())
    except Exception as e:
        logger.error(f"❌ Critical error in background worker: {e}", exc_info=True)