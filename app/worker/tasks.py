import asyncio
import logging
from urllib.parse import quote
from typing import List, Dict, Set

from app.worker.celery_app import celery_app
from app.services.storage import get_all_active_tasks, save_new_items
from app.services.parsers.engine import parse_multiple_urls
from app.services.notification import send_new_item_notification

logger = logging.getLogger(__name__)


def build_urls_from_task(task) -> List[str]:
    """
    Generates target URLs based on task parameters and selected platforms.
    This replaces the old hardcoded URLs with dynamic query building.
    """
    urls = []
    # URL-encode the keyword (e.g., "Nintendo Switch" -> "Nintendo%20Switch")
    safe_keyword = quote(task.keyword)

    # Task platforms are stored as a comma-separated string: "mercari,yahoo"
    platforms = task.platforms.split(",")

    if "mercari" in platforms:
        url = f"https://jp.mercari.com/search?keyword={safe_keyword}&status=on_sale"
        if task.min_price:
            url += f"&price_min={task.min_price}"
        if task.max_price:
            url += f"&price_max={task.max_price}"
        urls.append(url)

    if "yahoo" in platforms:
        url = f"https://auctions.yahoo.co.jp/search/search?p={safe_keyword}"
        if task.min_price:
            url += f"&aucminprice={task.min_price}"
        if task.max_price:
            url += f"&aucmaxprice={task.max_price}"
        urls.append(url)

    if "rakuma" in platforms:
        # У Rakuma домен fril.jp, параметры передаются через ?min= & max=
        url = f"https://fril.jp/search/{safe_keyword}"
        params = []
        if task.min_price:
            params.append(f"min={task.min_price}")
        if task.max_price:
            params.append(f"max={task.max_price}")

        if params:
            url += "?" + "&".join(params)
        urls.append(url)

    if "rakuten" in platforms:
        url = f"https://search.rakuten.co.jp/search/mall/{safe_keyword}/"
        params = []
        if task.min_price:
            params.append(f"min={task.min_price}")
        if task.max_price:
            params.append(f"max={task.max_price}")
        if params:
            url += "?" + "&".join(params)
        urls.append(url)

    if "paypay" in platforms:
        url = f"https://paypayfleamarket.yahoo.co.jp/search/{safe_keyword}"
        params = []
        if task.min_price:
            params.append(f"minPrice={task.min_price}")
        if task.max_price:
            params.append(f"maxPrice={task.max_price}")
        if params:
            url += "?" + "&".join(params)
        urls.append(url)

    return urls




async def async_run_all_searches():
    """
    Core asynchronous logic with Multi-Tenant Routing (Query Batching).
    """
    logger.info("⏰ Celery Beat: Starting scheduled search cycle...")

    tasks = await get_all_active_tasks()
    if not tasks:
        logger.info("📭 No active search tasks found in DB. Skipping cycle.")
        return

    # 1. Map URLs to a set of User IDs to avoid duplicate browser launches
    url_to_users: Dict[str, Set[int]] = {}
    for task in tasks:
        urls = build_urls_from_task(task)
        for url in urls:
            if url not in url_to_users:
                url_to_users[url] = set()
            url_to_users[url].add(task.user_id) # Связываем URL с пользователем

    urls_to_parse = list(url_to_users.keys())
    if not urls_to_parse:
        return

    # 2. Parse URLs using the anti-ban system
    logger.info(f"🚦 Dispatching {len(urls_to_parse)} unique URLs to Playwright...")
    results_dict = await parse_multiple_urls(urls_to_parse, max_items=10)

    # 3. Associate found items with their target users
    all_found_items = []
    item_to_users: Dict[str, Set[int]] = {} # market_id -> set of user_ids

    for url, items in results_dict.items():
        users_for_url = url_to_users[url]
        for item in items:
            all_found_items.append(item)
            if item.market_id not in item_to_users:
                item_to_users[item.market_id] = set()
            item_to_users[item.market_id].update(users_for_url)

    # 4. Filter duplicates via DB
    new_items = await save_new_items(all_found_items)

    if not new_items:
        logger.info("💤 No new items found this cycle.")
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
    """
    Synchronous wrapper for Celery to execute the async pipeline.
    Because our tech stack (SQLAlchemy, Playwright, Aiogram) is async,
    we must run the event loop manually inside the sync Celery worker.
    """
    try:
        asyncio.run(async_run_all_searches())
    except Exception as e:
        logger.error(f"❌ Critical error in background worker: {e}", exc_info=True)