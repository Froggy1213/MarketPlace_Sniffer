import logging
from urllib.parse import quote
from typing import Dict, Set, Tuple, List
from collections import defaultdict

from app.services.tasks import get_all_active_tasks
from app.services.items import save_new_items
from app.services.parsers.engine import parse_multiple_urls

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
    elif platform == "paypay":
        return f"https://paypayfleamarket.yahoo.co.jp/search/{safe_keyword}"
    return ""

async def fetch_and_prepare_notifications() -> List[dict]:
    """Выполняет цикл поиска и возвращает список товаров, готовых к отправке в очередь."""
    logger.info("🤖 [PARSER] Starting scheduled search cycle...")

    tasks = await get_all_active_tasks()
    if not tasks:
        return []

    url_to_tasks = defaultdict(list)
    for task in tasks:
        for p in task.platforms:
            url = build_broad_url(p, task.keyword)
            if url:
                url_to_tasks[url].append(task)

    urls_to_parse = list(url_to_tasks.keys())
    if not urls_to_parse:
        return []

    results_dict = await parse_multiple_urls(urls_to_parse, max_items=30)

    all_valid_items = []
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
        return []

    await save_new_items(all_valid_items)

    unique_items = {item.market_id: item for item in all_valid_items}.values()
    
    notifications_to_send = []
    for item in unique_items:
        target_users = item_to_users.get(item.market_id, set())
        for user_id, task_id in target_users:
            notifications_to_send.append({
                "user_id": user_id,
                "task_id": task_id,
                "market_id": item.market_id,
                "platform": item.platform or "unknown",
                "title": item.title,
                "price": item.price,
                "url": item.url,
                "image_url": item.image_url
            })

    return notifications_to_send