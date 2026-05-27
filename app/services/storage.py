"""
Storage module for database operations related to products, search tasks, and found items.
"""

import logging
from typing import List, Optional
from datetime import datetime, timedelta

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

# Оставляем async_session_maker только для воркера (Celery)
from app.db.database import async_session_maker
from app.db.models import Product, SearchTask, FoundItem, User
from app.services.parsers.base import ItemData

logger = logging.getLogger(__name__)


# ============================================================================
# USER & BILLING FUNCTIONS (Bot)
# ============================================================================

async def get_user_tier(session: AsyncSession, telegram_id: int) -> str:
    """Возвращает текущий тариф пользователя (создает его, если он новый)."""
    user = await session.get(User, telegram_id)
    if not user:
        user = User(telegram_id=telegram_id, tier="free")
        session.add(user)
        await session.commit()
        return "free"
        
    # Проверяем, не истекла ли подписка
    if user.tier == "pro" and user.pro_expires_at and user.pro_expires_at < datetime.utcnow():
        user.tier = "free"
        await session.commit()
        
    return user.tier

async def count_user_tasks(session: AsyncSession, telegram_id: int) -> int:
    """Считает активные задачи пользователя."""
    query = select(func.count(SearchTask.id)).where(
        SearchTask.user_id == telegram_id, 
        SearchTask.is_active == True
    )
    return await session.scalar(query) or 0

async def upgrade_user_to_pro(session: AsyncSession, telegram_id: int, days: int = 30):
    """Активирует PRO-тариф."""
    user = await session.get(User, telegram_id)
    if user:
        user.tier = "pro"
        user.pro_expires_at = datetime.utcnow() + timedelta(days=days)
        await session.commit()


# ============================================================================
# SYSTEM STATISTICS FUNCTIONS (Bot Admin)
# ============================================================================

async def get_system_stats(session: AsyncSession) -> dict:
    """Collects system statistics."""
    active_tasks_query = select(func.count(SearchTask.id)).where(SearchTask.is_active == True)
    active_tasks = await session.scalar(active_tasks_query)

    found_items_query = select(func.count(FoundItem.id))
    total_items = await session.scalar(found_items_query)

    return {
        "active_tasks": active_tasks or 0,
        "total_found_items": total_items or 0
    }


# ============================================================================
# SEARCH TASK MANAGEMENT FUNCTIONS (Bot)
# ============================================================================

async def add_search_task(
        session: AsyncSession,
        user_id: int,
        keyword: str,
        platforms: list[str], # Изменили тип на list[str], так как в БД теперь ARRAY
        min_price: Optional[int] = None,
        max_price: Optional[int] = None
) -> bool:
    """Adds a new search task to the database for a user."""
    # Защита от дублей
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


async def get_user_tasks(session: AsyncSession, user_id: int) -> List[SearchTask]:
    """Fetches all active search tasks for a specific user."""
    # ИСПРАВЛЕН БАГ: Добавлен фильтр SearchTask.user_id == user_id
    query = select(SearchTask).where(
        SearchTask.is_active == True,
        SearchTask.user_id == user_id
    )
    result = await session.execute(query)
    return list(result.scalars().all())


async def delete_search_task(session: AsyncSession, task_id: int, user_id: int) -> bool:
    """Deletes a search task from the database."""
    try:
        stmt = delete(SearchTask).where(
            SearchTask.id == task_id,
            SearchTask.user_id == user_id
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount > 0 
    except Exception as e:
        logger.error(f"Error deleting task: {e}")
        await session.rollback()
        return False


# ============================================================================
# BACKGROUND WORKER FUNCTIONS (Celery / Parsers)
# ============================================================================
# Здесь мы ОСТАВЛЯЕМ локальные сессии, потому что воркер работает 
# вне хендлеров Aiogram и у него нет Middleware.

async def get_all_active_tasks() -> List[SearchTask]:
    """Fetches all active search tasks from the database for the worker."""
    async with async_session_maker() as session:
        result = await session.execute(select(SearchTask).where(SearchTask.is_active == True))
        return list(result.scalars().all())


async def save_new_items(items: List[ItemData]) -> List[ItemData]:
    """Saves new products to the database and returns only those that were newly created."""
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