import logging
from typing import List, Optional
from sqlalchemy import select, delete
from app.db.database import async_session_maker
from app.db.models import Product, SearchTask
from app.services.parsers.base import ItemData
logger = logging.getLogger(__name__)


# --- PRODUCTS ---

async def save_new_items(items: List[ItemData]) -> List[ItemData]:
    """Saves new products and returns only those that didn't exist in the DB yet"""
    if not items:
        return []

    async with async_session_maker() as session:
        market_ids = [item.market_id for item in items]

        # Check for duplicates
        query = select(Product.market_id).where(Product.market_id.in_(market_ids))
        result = await session.execute(query)
        existing_ids = set(row[0] for row in result.all())

        new_items_data = []
        new_products_to_insert = []

        for item in items:
            if item.market_id not in existing_ids:
                new_items_data.append(item)
                product_model = Product(
                    market_id=item.market_id,
                    platform=item.platform,
                    title=item.title,
                    price=item.price,
                    url=item.url
                )
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


# --- SEARCH TASKS ---

async def add_search_task(
        user_id: int,
        keyword: str,
        platforms: str,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None
) -> bool:
    """Adds a new search task to the database"""
    async with async_session_maker() as session:
        # Duplicate guard: check if the user is already searching for the same thing
        query = select(SearchTask).where(
            SearchTask.user_id == user_id,
            SearchTask.keyword == keyword,
            SearchTask.platforms == platforms
        )
        result = await session.execute(query)
        if result.scalar_one_or_none():
            return False

        try:
            new_task = SearchTask(
                user_id=user_id,
                keyword=keyword,
                platforms=platforms,
                min_price=min_price,
                max_price=max_price
            )
            session.add(new_task)
            await session.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding task: {e}")
            await session.rollback()
            return False


async def get_all_active_tasks() -> List[SearchTask]:
    """For the worker: fetch all active tasks across all users"""
    async with async_session_maker() as session:
        result = await session.execute(select(SearchTask).where(SearchTask.is_active))
        return list(result.scalars().all())


async def get_user_tasks(user_id: int) -> List[SearchTask]:
    """For the Telegram bot: show the task list for a specific user (/list)"""
    async with async_session_maker() as session:
        result = await session.execute(select(SearchTask).where(SearchTask.is_active.is_(True)))
        return list(result.scalars().all())


async def delete_search_task(task_id: int, user_id: int) -> bool:
    """Deletes a task. Important: user_id is checked so users can't delete each other's searches"""
    async with async_session_maker() as session:
        try:
            stmt = delete(SearchTask).where(
                SearchTask.id == task_id,
                SearchTask.user_id == user_id
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0 # type: ignore
        except Exception as e:
            logger.error(f"Error deleting task: {e}")
            await session.rollback()
            return False