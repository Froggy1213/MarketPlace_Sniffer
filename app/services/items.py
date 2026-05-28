import logging
from typing import List
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.db.database import worker_session_maker as async_session_maker
from app.db.models import Product, FoundItem
from app.services.parsers.base import ItemData

logger = logging.getLogger(__name__)

# === ВЫЗЫВАЮТСЯ ТОЛЬКО CELERY (БЕЗ MIDDLEWARE) ===
async def check_and_mark_item_sent(user_id: int, task_id: int, market_id: str) -> bool:
    async with async_session_maker() as session:
        try:
            found_item = FoundItem(user_id=user_id, task_id=task_id, market_id=market_id)
            session.add(found_item)
            await session.commit()
            return True
        except IntegrityError:
            await session.rollback()
            return False

async def save_new_items(items: List[ItemData]) -> List[ItemData]:
    if not items:
        return []

    async with async_session_maker() as session:
        market_ids = [item.market_id for item in items]
        query = select(Product.market_id).where(Product.market_id.in_(market_ids))
        result = await session.execute(query)
        existing_ids = set(row[0] for row in result.all())

        new_items_data = []
        new_products_to_insert = []

        for item in items:
            if item.market_id not in existing_ids:
                new_items_data.append(item)
                product_model = Product(market_id=item.market_id, platform=item.platform, title=item.title, price=item.price, url=item.url)
                new_products_to_insert.append(product_model)
                existing_ids.add(item.market_id)

        if new_products_to_insert:
            try:
                session.add_all(new_products_to_insert)
                await session.commit()
                logger.info(f"💾 New products saved to DB: {len(new_products_to_insert)}")
            except Exception as e:
                logger.error(f"Error saving products: {e}")
                await session.rollback()

        return new_items_data