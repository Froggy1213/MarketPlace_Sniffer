import logging
from typing import List, Optional
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import worker_session_maker as async_session_maker
from app.db.models import SearchTask

logger = logging.getLogger(__name__)

async def count_user_tasks(session: AsyncSession, telegram_id: int) -> int:
    query = select(func.count(SearchTask.id)).where(
        SearchTask.user_id == telegram_id, 
        SearchTask.is_active == True
    )
    return await session.scalar(query) or 0


async def add_search_task(
        session: AsyncSession,
        user_id: int,
        keyword: str,
        platforms: list[str], 
        min_price: Optional[int] = None,
        max_price: Optional[int] = None
) -> bool:
    """Adds a new search task to the database for a user."""
    # Проверяем дубликаты только по юзеру и ключевому слову
    query = select(SearchTask).where(
        SearchTask.user_id == user_id,
        SearchTask.keyword == keyword
    )
    result = await session.execute(query)
    if result.scalar_one_or_none():
        return False

    # Блок создания задачи с конвертацией списка в строку
    try:
        platforms_str = ",".join(platforms) if isinstance(platforms, list) else platforms

        new_task = SearchTask(
            user_id=user_id,
            keyword=keyword,
            platforms=platforms_str,
            min_price=min_price,
            max_price=max_price
        )
        session.add(new_task)
        await session.commit()
        return True
    except Exception as e:
        logger.error(f"🗄 Ошибка БД при добавлении задачи (user_id={user_id}, keyword='{keyword}'). Детали: {e}")
        await session.rollback()
        return False

async def get_user_tasks(session: AsyncSession, user_id: int) -> List[SearchTask]:
    query = select(SearchTask).where(SearchTask.is_active == True, SearchTask.user_id == user_id)
    result = await session.execute(query)
    return list(result.scalars().all())

async def delete_search_task(session: AsyncSession, task_id: int, user_id: int) -> bool:
    try:
        stmt = delete(SearchTask).where(SearchTask.id == task_id, SearchTask.user_id == user_id)
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount > 0 
    except Exception as e:
        logger.error(f"🗄 Ошибка БД при удалении задачи (user_id={user_id}, task_id={task_id}). Детали: {e}")
        await session.rollback()
        return False

# === ВЫЗЫВАЕТСЯ ТОЛЬКО CELERY (БЕЗ MIDDLEWARE) ===
async def get_all_active_tasks() -> List[SearchTask]:
    async with async_session_maker() as session:
        result = await session.execute(select(SearchTask).where(SearchTask.is_active == True))
        return list(result.scalars().all())