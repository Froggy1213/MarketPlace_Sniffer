import asyncio
import logging
from urllib.parse import quote
from typing import List

from app.worker.celery_app import celery_app
from app.services.storage import get_all_active_tasks, save_new_items
from app.services.parsers.engine import parse_multiple_urls
from app.services.parsers.base import ItemData
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
        if task.min_price: params.append(f"min={task.min_price}")
        if task.max_price: params.append(f"max={task.max_price}")
        if params: url += "?" + "&".join(params)
        urls.append(url)

    if "paypay" in platforms:
        url = f"https://paypayfleamarket.yahoo.co.jp/search/{safe_keyword}"
        params = []
        if task.min_price: params.append(f"minPrice={task.min_price}")
        if task.max_price: params.append(f"maxPrice={task.max_price}")
        if params: url += "?" + "&".join(params)
        urls.append(url)

    return urls


async def async_run_all_searches():
    """
    Core asynchronous logic for the background worker.
    """
    logger.info("⏰ Celery Beat: Starting scheduled search cycle...")

    # 1. Fetch all user intentions from the database
    tasks = await get_all_active_tasks()
    if not tasks:
        logger.info("📭 No active search tasks found in DB. Skipping cycle.")
        return

    # 2. Build exactly which URLs to scrape
    all_urls_to_parse = []
    for task in tasks:
        all_urls_to_parse.extend(build_urls_from_task(task))

    if not all_urls_to_parse:
        return

    # 3. Parse URLs using the anti-ban system
    logger.info(f"🚦 Dispatching {len(all_urls_to_parse)} URLs to Playwright...")
    results_dict = await parse_multiple_urls(all_urls_to_parse, max_items=10)

    # Flatten the dictionary into a single list of ItemData objects
    all_found_items = []
    for url, items in results_dict.items():
        all_found_items.extend(items)

    logger.info(f"🔎 Found {len(all_found_items)} total items. Filtering duplicates...")

    # 4. Check against DB history to prevent spam
    new_items = await save_new_items(all_found_items)

    if not new_items:
        logger.info("💤 No new items found this cycle.")
        return

    # 5. Send notifications to Telegram
    logger.info(f"🚀 {len(new_items)} NEW items found! Sending Telegram notifications.")
    for item in new_items:
        await send_new_item_notification(item)
        await asyncio.sleep(1)  # Prevent Telegram API rate limit errors (429 Too Many Requests)


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